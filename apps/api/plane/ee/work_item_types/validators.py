from uuid import UUID

from crum import get_current_user
from rest_framework.exceptions import PermissionDenied

from plane.db.models import Issue, IssueType, Project, ProjectMember
from plane.db.models.issue_type import ProjectIssueType
from plane.db.models.state import StateGroup
from plane.ee.models import AttributeValue

from .constants import TypeKey
from .exceptions import WorkItemValidationError
from .hierarchy import assert_no_cycle, validate_parent
from .registry import type_key_of
from .scrum_rules import assert_can_complete
from .value_codec import missing_required

INTAKE_TYPES = frozenset({TypeKey.BUG, TypeKey.USER_STORY})


def check_hierarchy(
    issue_type: IssueType, parent: Issue | None, issue_id: UUID | None, project_id: UUID, *, triage: bool
) -> None:
    """Parent-child rules shared by the serializer gate and the pre_save signal."""
    type_key = type_key_of(issue_type)
    if type_key is None:
        raise WorkItemValidationError("type_invalid", "Work item type is not a known agile type")
    parent_key = None
    if parent is not None:
        if str(parent.project_id) != str(project_id):
            raise WorkItemValidationError("parent_invalid", "Parent must be a work item in the same project")
        parent_key = type_key_of(parent.type)
        if parent_key is None:
            raise WorkItemValidationError("parent_type_invalid", "Parent has no valid work item type")
    validate_parent(type_key, parent_key, triage=triage)
    assert_no_cycle(issue_id, parent)


def _is_triage(state) -> bool:
    return state is not None and state.group == StateGroup.TRIAGE.value


def validate_issue_payload(serializer, attrs: dict) -> None:
    """EE gate for IssueCreateSerializer. Called from run_validation (after DRF validate()),
    so WorkItemValidationError reaches the response un-wrapped: {"error_code", "message", "details"}.
    Triage mode only while the issue stays in a triage state; leaving triage (intake accept, or a
    PATCH of state) re-validates fully, including stored required attributes."""
    instance, ctx = serializer.instance, serializer.context
    if "attribute_values" in attrs:
        request = ctx.get("request")
        check_can_write_values(ctx["project_id"], request.user if request is not None else get_current_user())
    state = attrs.get("state", getattr(instance, "state", None))
    triage = ctx.get("allow_triage_state", False) and _is_triage(state)
    leaving_triage = instance is not None and _is_triage(instance.state) and not _is_triage(state)
    if instance is not None and "state" in attrs:
        assert_can_complete(instance, attrs["state"])
    if instance is None or leaving_triage or "type" in attrs or "parent" in attrs or "attribute_values" in attrs:
        issue_type = attrs.get("type", getattr(instance, "type", None))
        parent = attrs.get("parent", getattr(instance, "parent", None))
        validate_work_item(
            project=ctx["project_id"],
            issue_type_id=issue_type.id if issue_type else None,
            parent_id=parent.id if parent else None,
            attribute_values=attrs.get("attribute_values"),
            instance=instance,
            triage=triage,
            full=leaving_triage,
        )


def validate_existing(issue: Issue) -> None:
    """Full (non-triage) check of a stored issue, e.g. when intake accepts it out of triage."""
    validate_work_item(
        project=issue.project_id,
        issue_type_id=issue.type_id,
        parent_id=issue.parent_id,
        attribute_values=None,
        instance=issue,
        full=True,
    )


def check_can_write_values(project_id: UUID, user) -> None:
    """Attribute values need project role >= member (guests are read-only)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return  # deliberate: no request user = internal caller (task/script), trusted
    if not ProjectMember.objects.filter(
        project_id=project_id, member_id=getattr(user, "id", None), role__gte=15, is_active=True
    ).exists():
        raise PermissionDenied("Only project members can write attribute values")


def validate_work_item(
    *,
    project: Project | UUID,
    issue_type_id: UUID | None,
    parent_id: UUID | None,
    attribute_values: dict | None,
    instance: Issue | None = None,
    triage: bool = False,
    full: bool = False,
) -> None:
    """triage: skip parent + required attributes (intake pending/snoozed; new ones must be Bug/User Story).
    full: on an existing instance, also check required attributes against the stored values."""
    project_id = getattr(project, "id", project)
    if issue_type_id is None:
        raise WorkItemValidationError("type_required", "Work item type is required")
    if instance is not None and instance.type_id is not None and instance.type_id != issue_type_id:
        raise WorkItemValidationError("type_immutable", "Work item type cannot be changed")
    link = (
        ProjectIssueType.objects.filter(project_id=project_id, issue_type_id=issue_type_id)
        .select_related("issue_type")
        .first()
    )
    if link is None:
        raise WorkItemValidationError("type_invalid", "Work item type is not enabled for this project")
    if triage and instance is None and type_key_of(link.issue_type) not in INTAKE_TYPES:
        raise WorkItemValidationError("type_invalid", "Intake accepts only Bug or User Story")
    parent = None
    if parent_id is not None:
        parent = Issue.objects.filter(pk=parent_id).select_related("type").first()
        if parent is None:
            raise WorkItemValidationError("parent_invalid", "Parent must be a work item in the same project")
    check_hierarchy(link.issue_type, parent, instance.id if instance else None, project_id, triage=triage)
    if triage or (instance is not None and attribute_values is None and not full):
        return
    values = attribute_values or {}
    if instance is not None and full:  # stored values, overridden by what this request writes
        stored = AttributeValue.objects.filter(issue_id=instance.id).values_list("attribute_id", flat=True)
        values = {**{str(a): True for a in stored}, **{str(k).lower(): v for k, v in values.items()}}
    missing = missing_required(project_id, issue_type_id, values)
    if instance is not None and not full:  # PATCH: only fields being written may not be blanked
        sent = {str(k) for k in values}
        missing = [m for m in missing if str(m) in sent]
    if missing:
        raise WorkItemValidationError(
            "attribute_required", "Required attributes are missing", {"missing": [str(m) for m in missing]}
        )
