from plane.db.models import Cycle, CycleIssue, Issue, IssueType, State
from plane.db.models.state import StateGroup

from .constants import SPRINT_TYPES, TypeKey
from .exceptions import WorkItemValidationError
from .registry import type_key_of
from .tree_ops import DONE_GROUPS


def assert_type_can_enter_cycle(issue_type: IssueType | None) -> None:
    key = type_key_of(issue_type)
    if key is not None and key not in SPRINT_TYPES:  # untyped legacy issues keep core behaviour
        raise WorkItemValidationError(
            "cycle_type_not_allowed", f"{key.value} cannot be added to a cycle", {"type": key.value}
        )


def assert_can_enter_cycle(issue: Issue, cycle: Cycle) -> list[str]:
    """Raise for Epic/Feature; return warnings when a Task/Sub-task lands in another cycle than its Story."""
    assert_type_can_enter_cycle(issue.type)
    if type_key_of(issue.type) not in (TypeKey.TASK, TypeKey.SUB_TASK):
        return []
    story = issue.parent  # depth is capped by MAX_DEPTH, so this walk is bounded
    while story is not None and type_key_of(story.type) != TypeKey.USER_STORY:
        story = story.parent
    if story is None:
        return []
    story_cycle = CycleIssue.objects.filter(issue=story).values_list("cycle_id", flat=True).first()
    if story_cycle is None or story_cycle == cycle.id:
        return []
    return [f"Work item {issue.id} is in a different cycle than its parent story {story.id}"]


def cycle_warnings(issue_ids, cycle: Cycle) -> list[str]:
    """Run assert_can_enter_cycle for every issue id before core writes CycleIssue rows."""
    issues = Issue.issue_objects.filter(id__in=issue_ids, project_id=cycle.project_id).select_related(
        "type", "parent__type"
    )
    return [w for issue in issues for w in assert_can_enter_cycle(issue, cycle)]


def assert_can_complete(issue: Issue, new_state: State | None) -> None:
    if new_state is None or new_state.group != StateGroup.COMPLETED.value:
        return
    open_children = list(
        Issue.issue_objects.filter(parent_id=issue.id)
        .exclude(state__group__in=DONE_GROUPS)
        .order_by("sequence_id")
        .values_list("id", flat=True)
    )
    if open_children:
        raise WorkItemValidationError(
            "open_children",
            "Complete or cancel all child work items first",
            {"children": [str(c) for c in open_children]},
        )
