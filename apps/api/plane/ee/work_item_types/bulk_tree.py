"""Create a whole work item tree in one transaction (spec §7 "Bulk tạo cả cây")."""

import json
from collections import deque
from typing import TypedDict

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from plane.db.models import IssueType, Project

from .constants import AGILE_SOURCE

_META = ("ref", "type", "parent_ref", "parent_id")


class RowError(TypedDict):
    ref: str
    code: str
    message: str


class BulkTreeResult(TypedDict):
    created: dict[str, str]
    errors: list[RowError]


class _Rollback(Exception):
    pass


def _order(items: list[dict], errors: list[RowError]) -> list[dict]:
    """Kahn's algorithm root -> leaf over parent_ref. Bad/unknown/cyclic refs go to `errors`."""
    by_ref: dict[str, dict] = {}
    for item in items:
        ref = item.get("ref")
        if not isinstance(ref, str) or not ref or ref in by_ref:
            errors.append({"ref": str(ref), "code": "ref_invalid", "message": "ref must be a unique non-empty string"})
        else:
            by_ref[ref] = item
    children: dict[str, list[str]] = {}
    pending: dict[str, int] = {}
    queue: deque[str] = deque()
    for ref, item in by_ref.items():
        parent_ref = item.get("parent_ref")
        if parent_ref is None:
            queue.append(ref)
        elif parent_ref not in by_ref:
            message = f"parent_ref '{parent_ref}' not in batch"
            errors.append({"ref": ref, "code": "parent_ref_unknown", "message": message})
        else:
            children.setdefault(parent_ref, []).append(ref)
            pending[ref] = 1
    ordered = []
    while queue:
        ref = queue.popleft()
        ordered.append(by_ref[ref])
        for child in children.get(ref, []):
            pending[child] -= 1
            if not pending[child]:
                queue.append(child)
    for ref, n in pending.items():
        if n:  # never reached from a root: on (or hanging below) a cycle
            errors.append({"ref": ref, "code": "parent_ref_cycle", "message": "parent_ref chain forms a cycle"})
    return ordered


def _error(ref: str, exc: ValidationError) -> RowError:
    detail = exc.detail
    if isinstance(detail, dict) and "error_code" in detail:
        return {"ref": ref, "code": str(detail["error_code"]), "message": str(detail["message"])}
    return {"ref": ref, "code": "invalid", "message": str(detail)}


def _log_created(project: Project, created: dict[str, str], items: list[dict], actor) -> None:
    from plane.bgtasks.issue_activities_task import issue_activity

    by_ref = {item["ref"]: item for item in items}
    for ref, issue_id in created.items():
        issue_activity.delay(
            type="issue.activity.created",
            requested_data=json.dumps(by_ref[ref], cls=DjangoJSONEncoder),
            actor_id=str(actor.id),
            issue_id=issue_id,
            project_id=str(project.id),
            current_instance=None,
            epoch=int(timezone.now().timestamp()),
            notification=True,
        )


def apply_bulk_tree(project: Project, items: list[dict], *, dry_run: bool, actor) -> BulkTreeResult:
    """All rows or none. dry_run always rolls back but reports what would be created / fail.

    Rows go through IssueCreateSerializer, the same path as the app create endpoint, so the EE gate,
    attribute values, sequence_id advisory lock and state defaults all apply."""
    from plane.app.serializers import IssueCreateSerializer  # app serializers import EE validators

    errors: list[RowError] = []
    ordered = _order(items, errors)
    types = {
        t.external_id: t.id
        for t in IssueType.objects.filter(workspace_id=project.workspace_id, external_source=AGILE_SOURCE)
    }
    created: dict[str, str] = {}
    context = {
        "project_id": project.id,
        "workspace_id": project.workspace_id,
        "default_assignee_id": project.default_assignee_id,
    }
    try:
        with transaction.atomic():
            for item in ordered:
                ref, parent_ref = item["ref"], item.get("parent_ref")
                if parent_ref is not None and parent_ref not in created:
                    errors.append({"ref": ref, "code": "parent_failed", "message": "parent row was not created"})
                    continue
                if item.get("type") not in types:
                    errors.append({"ref": ref, "code": "type_invalid", "message": "Unknown work item type"})
                    continue
                data = {k: v for k, v in item.items() if k not in _META}
                data["type_id"] = types[item["type"]]
                data["parent_id"] = created[parent_ref] if parent_ref is not None else item.get("parent_id")
                serializer = IssueCreateSerializer(data=data, context=context)
                try:
                    with transaction.atomic():  # savepoint: keep validating later rows after one fails
                        serializer.is_valid(raise_exception=True)
                        created[ref] = str(serializer.save().id)
                except ValidationError as exc:
                    errors.append(_error(ref, exc))
            if errors or dry_run:
                raise _Rollback
            transaction.on_commit(lambda: _log_created(project, created, items, actor))
    except _Rollback:
        pass
    return {"created": created if dry_run or not errors else {}, "errors": errors}
