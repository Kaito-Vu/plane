# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from dataclasses import dataclass

# Sub-tasks (level 0) may only sit under level-1/2 items (Task/Bug/Story/PBI), never under Epic/Feature.
SUBTASK_PARENT_LEVELS = frozenset({1, 2})


@dataclass(frozen=True)
class TypeInfo:
    id: str
    level: int
    is_epic: bool = False


def hierarchy_error(child: TypeInfo, parent: TypeInfo | None) -> str | None:
    """Return a message when (child type, parent type) is not allowed, else None."""
    if parent is None:
        return "A sub-task needs a parent" if child.level == 0 else None
    if child.is_epic:
        return "An epic cannot have a parent"
    if child.level >= parent.level:
        return "The parent must be a higher level than its child"
    if child.level == 0 and parent.level not in SUBTASK_PARENT_LEVELS:
        return "A sub-task can only sit under a task, bug or story level item"
    return None


def creates_cycle(issue_id, parent_id, parent_of) -> bool:
    """True if making `parent_id` the parent of `issue_id` closes a loop. `parent_of(id)` -> parent id | None."""
    seen = set()
    current = parent_id
    while current is not None and current not in seen:
        if current == issue_id:
            return True
        seen.add(current)
        current = parent_of(current)
    return False
