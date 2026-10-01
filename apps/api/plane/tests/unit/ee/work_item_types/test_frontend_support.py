# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import Issue, IssueType, State
from plane.ee.work_item_types.seed import apply_process
from plane.ee.work_item_types.serializers import IssueTypeSerializer
from plane.utils.filters.filterset import IssueFilterSet


@pytest.fixture
def env(db, workspace, project, create_user):
    apply_process(project, "scrum")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    types = {t.external_id: t for t in IssueType.objects.filter(workspace=workspace)}
    return state, types


@pytest.mark.unit
def test_external_id_is_exposed_and_read_only(env):
    _, t = env
    data = IssueTypeSerializer(t["epic"]).data
    assert data["external_id"] == "epic"
    assert "external_id" in IssueTypeSerializer.Meta.read_only_fields


@pytest.mark.unit
def test_filter_by_type_id(env, workspace, project, create_user):
    state, t = env
    mk = lambda n, ty: Issue.objects.create(  # noqa: E731
        name=n, workspace=workspace, project=project, state=state, type=ty, created_by=create_user
    )
    epic, task, bug = mk("e", t["epic"]), mk("t", t["task"]), mk("b", t["bug"])
    base = Issue.issue_objects.filter(project=project)
    one = IssueFilterSet(data={"type_id": str(t["epic"].id)}, queryset=base).qs
    assert set(one.values_list("id", flat=True)) == {epic.id}
    many = IssueFilterSet(data={"type_id__in": f"{t['task'].id},{t['bug'].id}"}, queryset=base).qs
    assert set(many.values_list("id", flat=True)) == {task.id, bug.id}
