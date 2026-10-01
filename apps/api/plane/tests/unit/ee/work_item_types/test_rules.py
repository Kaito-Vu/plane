# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.ee.work_item_types.rules import TypeInfo, creates_cycle, hierarchy_error

EPIC = TypeInfo("epic", 4, is_epic=True)
FEATURE = TypeInfo("feature", 3)
STORY = TypeInfo("story", 2)
BUG = TypeInfo("bug", 2)
TASK = TypeInfo("task", 1)
SUB = TypeInfo("sub", 0)


@pytest.mark.unit
@pytest.mark.parametrize(
    "child,parent",
    [
        (FEATURE, EPIC),
        (STORY, FEATURE),
        (STORY, EPIC),
        (TASK, STORY),
        (TASK, BUG),
        (SUB, TASK),
        (SUB, STORY),
        (EPIC, None),
        (STORY, None),
        (TASK, None),
    ],
)
def test_allowed(child, parent):
    assert hierarchy_error(child, parent) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "child,parent",
    [
        (EPIC, FEATURE),
        (STORY, STORY),
        (STORY, TASK),
        (TASK, TASK),
        (SUB, EPIC),
        (SUB, FEATURE),
        (SUB, SUB),
        (SUB, None),
    ],
)
def test_rejected(child, parent):
    assert hierarchy_error(child, parent) is not None


@pytest.mark.unit
def test_creates_cycle():
    parents = {"a": "b", "b": "c", "c": None}
    assert creates_cycle("c", "a", parents.get)  # c -> a would loop a->b->c->a
    assert not creates_cycle("a", "c", parents.get)
    assert creates_cycle("a", "a", parents.get)
    assert not creates_cycle("a", None, parents.get)


@pytest.mark.unit
def test_creates_cycle_stops_on_existing_loop():
    parents = {"x": "y", "y": "x"}  # corrupt legacy data must not hang
    assert not creates_cycle("z", "x", parents.get)
