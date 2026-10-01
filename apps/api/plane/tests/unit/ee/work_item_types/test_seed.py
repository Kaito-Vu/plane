# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import Issue, IssueType, State
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.seed import ProcessChangeBlocked, apply_process, project_process, seed_types


def names(project):
    return {pit.issue_type.name for pit in ProjectIssueType.objects.filter(project=project)}


@pytest.mark.unit
def test_seed_is_idempotent(workspace):
    first = seed_types(workspace)
    second = seed_types(workspace)
    assert {k: v.id for k, v in first.items()} == {k: v.id for k, v in second.items()}
    assert IssueType.objects.filter(workspace=workspace).count() == len(first)
    assert first["epic"].is_epic and first["epic"].level == 4
    assert first["sub_task"].level == 0


@pytest.mark.unit
def test_apply_scrum_and_agile(workspace, project):
    apply_process(project, "scrum")
    assert names(project) == {"Epic", "Feature", "Bug", "Task", "Sub-task", "Product Backlog Item"}
    assert project_process(project) == "scrum"
    default = ProjectIssueType.objects.get(project=project, is_default=True)
    assert default.issue_type.name == "Product Backlog Item"
    project.refresh_from_db()
    assert project.is_issue_type_enabled is True

    apply_process(project, "agile")  # no issue uses PBI -> switch allowed
    assert "Product Backlog Item" not in names(project) and "User Story" in names(project)
    assert project_process(project) == "agile"


@pytest.mark.unit
def test_switch_blocked_when_exclusive_type_in_use(workspace, project, create_user):
    apply_process(project, "scrum")
    pbi = IssueType.objects.get(workspace=workspace, external_id="product_backlog_item")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="I", workspace=workspace, project=project, state=state, type=pbi, created_by=create_user)
    with pytest.raises(ProcessChangeBlocked):
        apply_process(project, "agile")


@pytest.mark.unit
def test_project_process_none_when_unset(project):
    assert project_process(project) is None
