import json
import logging

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from plane.bgtasks.deletion_task import soft_delete_related_objects
from plane.db.models import Issue

from .constants import MAX_DEPTH
from .exceptions import WorkItemValidationError

DONE_GROUPS = ("completed", "cancelled")
logger = logging.getLogger("plane.worker")


def _descendant_ids(root_ids, **filters) -> list:
    """All descendants (not the roots) matching filters, walking parent links level by level."""
    found, level = [], list(root_ids)
    for _ in range(MAX_DEPTH + 1):
        level = list(Issue.all_objects.filter(parent_id__in=level, **filters).values_list("id", flat=True))
        if not level:
            break
        found += level
    return found


def _log_descendants(ids, issue: Issue, actor_id, type_: str, requested: dict, current: dict | None) -> None:
    """One issue_activity per cascaded descendant (after commit), so they show up in history."""
    if actor_id is None or not ids:
        return
    from plane.bgtasks.issue_activities_task import issue_activity  # bgtasks import views; keep lazy

    epoch = int(timezone.now().timestamp())
    for pk in ids:
        transaction.on_commit(
            lambda pk=pk: issue_activity.delay(
                type=type_,
                requested_data=json.dumps(
                    {**requested, "issue_id": str(pk)} if type_.endswith("deleted") else requested
                ),
                actor_id=str(actor_id),
                issue_id=str(pk),
                project_id=str(issue.project_id),
                current_instance=json.dumps(current) if current is not None else None,
                epoch=epoch,
            )
        )


def subtree_count(issue: Issue, for_archive: bool = False) -> int:
    """Live descendants that a delete (or, for_archive, an archive) of issue would take with it.
    The walk stays on live rows; for_archive then drops descendants that are already archived."""
    ids = _descendant_ids([issue.id], deleted_at__isnull=True)
    if not for_archive:
        return len(ids)
    return Issue.all_objects.filter(id__in=ids, archived_at__isnull=True).count()


def soft_delete_subtree(issue: Issue, actor_id=None) -> int:
    """Synchronously soft-delete issue + every live descendant with one shared deleted_at.
    With actor_id, each descendant gets a "deleted" activity (the caller logs the root)."""
    descendants = _descendant_ids([issue.id], deleted_at__isnull=True)
    ids = [issue.id, *descendants]
    now = timezone.now()
    with transaction.atomic():
        count = Issue.all_objects.filter(id__in=ids, deleted_at__isnull=True).update(deleted_at=now)
        for pk in ids:  # cycle/module links etc. follow core's per-issue cascade
            transaction.on_commit(lambda pk=pk: soft_delete_related_objects.delay("db", "issue", pk))
        _log_descendants(descendants, issue, actor_id, "issue.activity.deleted", {}, None)
    issue.deleted_at = now
    return count


def restore_subtree(issue: Issue) -> int:
    """Restore issue and only the descendants deleted in the same batch (same deleted_at)."""
    stamp = issue.deleted_at
    if stamp is None:
        return 0
    ids = [issue.id, *_descendant_ids([issue.id], deleted_at=stamp)]
    count = Issue.all_objects.filter(id__in=ids, deleted_at=stamp).update(deleted_at=None)
    issue.deleted_at = None
    return count


def archive_subtree(issue: Issue, actor_id=None, automation: bool = False) -> int:
    """Archive every live, unarchived descendant with the root's archive date (root saved by the caller).
    With actor_id, each newly archived descendant gets an "archived" activity."""
    archived_at = issue.archived_at or timezone.now().date()
    qs = Issue.all_objects.filter(id__in=_descendant_ids([issue.id], deleted_at__isnull=True), archived_at__isnull=True)
    ids = list(qs.values_list("id", flat=True))
    count = Issue.all_objects.filter(id__in=ids).update(archived_at=archived_at)
    requested = {"archived_at": str(archived_at), "automation": automation}
    _log_descendants(ids, issue, actor_id, "issue.activity.updated", requested, {"archived_at": None})
    return count


def assert_can_unarchive(issue: Issue) -> None:
    """A work item may not come back under an archived or deleted parent (no live child under a dead parent)."""
    if issue.parent_id is None:
        return
    parent = Issue.all_objects.filter(pk=issue.parent_id).values("deleted_at", "archived_at").first()
    if parent is None or parent["deleted_at"] is not None:
        raise WorkItemValidationError("parent_deleted", "The parent work item was deleted; restore it first")
    if parent["archived_at"] is not None:
        raise WorkItemValidationError("parent_archived", "The parent work item is archived; restore it first")


def unarchive_subtree(issue: Issue, archived_at, actor_id=None) -> int:
    """Restore the live descendants archived by the same cascade as the root (same archive date).
    ponytail: archived_at is a date, so items archived separately the same day under it come back too."""
    if archived_at is None:
        return 0
    ids = _descendant_ids([issue.id], deleted_at__isnull=True, archived_at=archived_at)
    count = Issue.all_objects.filter(id__in=ids).update(archived_at=None)
    _log_descendants(
        ids, issue, actor_id, "issue.activity.updated", {"archived_at": None}, {"archived_at": str(archived_at)}
    )
    return count


def auto_archive_candidates(qs: QuerySet) -> QuerySet:
    """Drop issues that still have a descendant outside Completed/Cancelled (auto-archive/close skip them)."""
    rows = list(
        Issue.all_objects.filter(project_id__in=qs.values("project_id"), deleted_at__isnull=True).values_list(
            "id", "parent_id", "state__group"
        )
    )
    parent_of = {i: p for i, p, _ in rows}
    blocked = set()
    for _, parent, group in rows:
        if group in DONE_GROUPS:
            continue
        hops = 0
        while parent is not None and parent not in blocked and hops <= MAX_DEPTH:
            blocked.add(parent)
            parent, hops = parent_of.get(parent), hops + 1
    for skipped in qs.filter(id__in=blocked).values_list("id", flat=True):
        logger.info("auto archive/close: skipped issue %s, it has open descendants", skipped)
    return qs.exclude(id__in=blocked)
