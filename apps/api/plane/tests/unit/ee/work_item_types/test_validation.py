# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from rest_framework.exceptions import ValidationError

from plane.db.models import Issue, IssueType, State
from plane.ee.work_item_types.seed import apply_process


@pytest.fixture
def env(db, workspace, project, create_user):
    apply_process(project, "scrum")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    t = {x.external_id: x for x in IssueType.objects.filter(workspace=workspace)}

    def make(name, key=None, parent=None):
        return Issue.objects.create(
            name=name, workspace=workspace, project=project, state=state, parent=parent,
            type=t[key] if key else None, created_by=create_user,
        )

    return make, t, project


@pytest.mark.unit
def test_default_type_filled_on_create(env):
    make, t, _ = env
    assert make("a").type_id == t["product_backlog_item"].id


@pytest.mark.unit
def test_task_under_pbi_ok_subtask_under_epic_rejected(env):
    make, t, _ = env
    pbi = make("pbi", "product_backlog_item")
    make("task", "task", parent=pbi)
    epic = make("epic", "epic")
    with pytest.raises(ValidationError):
        make("sub", "sub_task", parent=epic)


@pytest.mark.unit
def test_epic_with_parent_and_subtask_without_parent_rejected(env):
    make, t, _ = env
    feature = make("f", "feature")
    with pytest.raises(ValidationError):
        make("e", "epic", parent=feature)
    with pytest.raises(ValidationError):
        make("s", "sub_task")


@pytest.mark.unit
def test_unchanged_type_and_parent_not_revalidated(env):
    make, t, _ = env
    pbi = make("pbi", "product_backlog_item")
    task = make("task", "task", parent=pbi)
    IssueType.objects.filter(pk=t["task"].pk).update(level=5)  # legacy data now violates the rule
    task.name = "renamed"
    task.save()  # must not raise


@pytest.mark.unit
def test_cycle_rejected(env):
    make, t, _ = env
    a = make("a", "feature")
    b = make("b", "product_backlog_item", parent=a)
    a.parent = b
    with pytest.raises(ValidationError):
        a.save()


@pytest.mark.unit
def test_change_type_blocked_by_children(env):
    make, t, _ = env
    pbi = make("pbi", "product_backlog_item")
    make("task", "task", parent=pbi)
    pbi.type = t["task"]  # level 1 can't hold a level-1 child
    with pytest.raises(ValidationError):
        pbi.save()
    pbi.refresh_from_db()
    pbi.type = t["sub_task"]
    with pytest.raises(ValidationError):
        pbi.save()


@pytest.mark.unit
def test_type_from_other_workspace_rejected_with_generic_message(env, create_user):
    from plane.db.models import Workspace

    make, t, project = env
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="X", level=2)
    issue = make("z")
    issue.type = foreign
    with pytest.raises(ValidationError) as exc:
        issue.save()
    assert "Invalid work item type" in str(exc.value.detail)


@pytest.mark.unit
def test_disabled_project_is_untouched(db, workspace, project, create_user):
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    issue = Issue.objects.create(name="x", workspace=workspace, project=project, state=state, created_by=create_user)
    assert issue.type_id is None
