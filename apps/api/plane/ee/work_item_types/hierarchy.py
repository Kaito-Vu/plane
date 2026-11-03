from uuid import UUID

from plane.db.models import Issue

from .constants import MAX_DEPTH, PARENT_RULES, TypeKey
from .exceptions import WorkItemValidationError


def validate_parent(type_key: TypeKey, parent_type_key: TypeKey | None, *, triage: bool = False) -> None:
    if parent_type_key is None:
        if type_key != TypeKey.EPIC and not triage:
            raise WorkItemValidationError("parent_required", f"{type_key.value} requires a parent")
        return
    if parent_type_key not in PARENT_RULES[type_key]:
        raise WorkItemValidationError(
            "parent_type_invalid",
            f"{type_key.value} cannot have a {parent_type_key.value} parent",
            {"type": type_key.value, "parent_type": parent_type_key.value},
        )


def depth_of(issue: Issue | None) -> int:
    """Nodes from issue up to the root (root = 1); stops once past MAX_DEPTH + 1."""
    depth = 0
    while issue is not None and depth <= MAX_DEPTH:
        depth += 1
        issue = issue.parent
    return depth


def _subtree_height(issue_id: UUID | None) -> int:
    """Levels of descendants below issue_id (0 for a leaf or a not-yet-created issue)."""
    if issue_id is None:
        return 0
    height, level = 0, [issue_id]
    while height <= MAX_DEPTH:
        level = list(Issue.all_objects.filter(parent_id__in=level).values_list("id", flat=True))
        if not level:
            break
        height += 1
    return height


def assert_no_cycle(issue_id: UUID | None, parent: Issue | None) -> None:
    node, seen = parent, 0
    while node is not None and seen <= MAX_DEPTH:
        if issue_id is not None and node.id == issue_id:
            raise WorkItemValidationError("parent_cycle", "Parent would create a cycle")
        node, seen = node.parent, seen + 1
    # moving an existing issue carries its descendants along: count the subtree's height too
    if depth_of(parent) + 1 + _subtree_height(issue_id) > MAX_DEPTH:
        raise WorkItemValidationError("max_depth_exceeded", f"Hierarchy deeper than {MAX_DEPTH}")
