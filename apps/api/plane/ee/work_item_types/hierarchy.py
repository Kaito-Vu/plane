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


def depth_of(issue) -> int:
    """Nodes from issue up to the root (root = 1); stops once past MAX_DEPTH + 1."""
    depth = 0
    while issue is not None and depth <= MAX_DEPTH:
        depth += 1
        issue = issue.parent
    return depth


def assert_no_cycle(issue_id, parent) -> None:
    node, seen = parent, 0
    while node is not None and seen <= MAX_DEPTH:
        if issue_id is not None and node.id == issue_id:
            raise WorkItemValidationError("parent_cycle", "Parent would create a cycle")
        node, seen = node.parent, seen + 1
    if depth_of(parent) + 1 > MAX_DEPTH:
        raise WorkItemValidationError("max_depth_exceeded", f"Hierarchy deeper than {MAX_DEPTH}")
