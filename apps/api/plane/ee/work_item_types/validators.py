from uuid import UUID

from crum import get_current_user
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import PermissionDenied

from plane.db.models import Issue, IssueType, Project, ProjectMember
from plane.db.models.issue_type import ProjectIssueType

from .exceptions import WorkItemValidationError
from .hierarchy import assert_no_cycle, validate_parent
from .constants import TypeKey
from .registry import get_type, type_key_of
from .value_codec import missing_required


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


def validate_issue_payload(serializer, attrs: dict) -> None:
    """EE gate for IssueCreateSerializer. Called from run_validation (after DRF validate()),
    so WorkItemValidationError reaches the response un-wrapped: {"error_code", "message", "details"}."""
    instance, ctx = serializer.instance, serializer.context
    if "attribute_values" in attrs:
        request = ctx.get("request")
        check_can_write_values(ctx["project_id"], request.user if request is not None else get_current_user())
    if instance is None or "type" in attrs or "parent" in attrs or "attribute_values" in attrs:
        issue_type = attrs.get("type", getattr(instance, "type", None))
        parent = attrs.get("parent", getattr(instance, "parent", None))
        validate_work_item(
            project=ctx["project_id"],
            issue_type_id=issue_type.id if issue_type else None,
            parent_id=parent.id if parent else None,
            attribute_values=attrs.get("attribute_values"),
            instance=instance,
            triage=ctx.get("allow_triage_state", False),
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
) -> None:
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
    parent = None
    if parent_id is not None:
        parent = Issue.objects.filter(pk=parent_id).select_related("type").first()
        if parent is None:
            raise WorkItemValidationError("parent_invalid", "Parent must be a work item in the same project")
    check_hierarchy(link.issue_type, parent, instance.id if instance else None, project_id, triage=triage)
    if triage or (instance is not None and attribute_values is None):
        return
    values = attribute_values or {}
    missing = missing_required(project_id, issue_type_id, values)
    if instance is not None:  # PATCH: only fields being written may not be blanked
        sent = {str(k) for k in values}
        missing = [m for m in missing if str(m) in sent]
    if missing:
        raise WorkItemValidationError(
            "attribute_required", "Required attributes are missing", {"missing": [str(m) for m in missing]}
        )


def validate_intake_type(project: Project, type_id: UUID | str | None) -> IssueType:
    """Intake submissions are Bug (default) or User Story, validated in triage mode (spec §7)."""
    try:
        issue_type = IssueType.objects.get(pk=type_id) if type_id else get_type(project.workspace_id, TypeKey.BUG)
    except (IssueType.DoesNotExist, ValueError, DjangoValidationError):
        issue_type = None
    if issue_type is None or type_key_of(issue_type) not in (TypeKey.BUG, TypeKey.USER_STORY):
        raise WorkItemValidationError("type_invalid", "Intake work items must be a Bug or a User Story")
    validate_work_item(project=project, issue_type_id=issue_type.id, parent_id=None, attribute_values=None, triage=True)
    return issue_type
