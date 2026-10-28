from uuid import UUID

from plane.db.models import Issue, IssueType, Project
from plane.db.models.issue_type import ProjectIssueType

from .exceptions import WorkItemValidationError
from .hierarchy import assert_no_cycle, validate_parent
from .registry import type_key_of


def check_hierarchy(issue_type: IssueType, parent: Issue | None, issue_id: UUID | None, *, triage: bool) -> None:
    """Parent-child rules shared by the serializer gate and the pre_save signal."""
    type_key = type_key_of(issue_type)
    if type_key is None:
        raise WorkItemValidationError("type_invalid", "Work item type is not a known agile type")
    parent_key = None
    if parent is not None:
        parent_key = type_key_of(parent.type)
        if parent_key is None:
            raise WorkItemValidationError("parent_type_invalid", "Parent has no valid work item type")
    validate_parent(type_key, parent_key, triage=triage)
    assert_no_cycle(issue_id, parent)


def validate_work_item(
    *,
    project: Project,
    issue_type_id: UUID | None,
    parent_id: UUID | None,
    attribute_values: dict | None,
    instance: Issue | None = None,
    triage: bool = False,
) -> None:
    if issue_type_id is None:
        raise WorkItemValidationError("type_required", "Work item type is required")
    if instance is not None and instance.type_id is not None and instance.type_id != issue_type_id:
        raise WorkItemValidationError("type_immutable", "Work item type cannot be changed")
    link = (
        ProjectIssueType.objects.filter(project=project, issue_type_id=issue_type_id)
        .select_related("issue_type")
        .first()
    )
    if link is None:
        raise WorkItemValidationError("type_invalid", "Work item type is not enabled for this project")
    parent = None
    if parent_id is not None:
        parent = Issue.objects.filter(pk=parent_id, project=project).select_related("type").first()
        if parent is None:
            raise WorkItemValidationError("parent_invalid", "Parent must be a work item in the same project")
    check_hierarchy(link.issue_type, parent, instance.id if instance else None, triage=triage)
    # attribute_values: required-attribute checks are wired in by Task 6.
