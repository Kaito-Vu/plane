# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import Issue, IssueType, State
from plane.ee.work_item_types.seed import apply_process


@pytest.fixture
def env(db, workspace, project, create_user):
    apply_process(project, "scrum")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    types = {t.external_id: t for t in IssueType.objects.filter(workspace=workspace)}
    return state, types


def issues_url(ws, p, tail=""):
    return f"/api/workspaces/{ws.slug}/projects/{p.id}/issues/{tail}"


@pytest.mark.contract
def test_create_with_type_id_and_default(session_client, workspace, project, env):
    state, t = env
    r = session_client.post(issues_url(workspace, project), {"name": "a", "type_id": str(t["bug"].id)}, format="json")
    assert r.status_code == 201, r.content
    assert Issue.objects.get(pk=r.json()["id"]).type_id == t["bug"].id
    r = session_client.post(issues_url(workspace, project), {"name": "b"}, format="json")
    assert Issue.objects.get(pk=r.json()["id"]).type_id == t["product_backlog_item"].id


@pytest.mark.contract
def test_create_invalid_hierarchy_is_400(session_client, workspace, project, env):
    state, t = env
    epic = session_client.post(issues_url(workspace, project), {"name": "e", "type_id": str(t["epic"].id)}, format="json").json()
    r = session_client.post(
        issues_url(workspace, project), {"name": "s", "type_id": str(t["sub_task"].id), "parent_id": epic["id"]}, format="json"
    )
    assert r.status_code == 400


@pytest.mark.contract
def test_patch_change_type_validated(session_client, workspace, project, env):
    state, t = env
    pbi = session_client.post(issues_url(workspace, project), {"name": "p"}, format="json").json()
    session_client.post(
        issues_url(workspace, project), {"name": "t", "type_id": str(t["task"].id), "parent_id": pbi["id"]}, format="json"
    )
    r = session_client.patch(issues_url(workspace, project, f"{pbi['id']}/"), {"type_id": str(t["task"].id)}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_foreign_type_id_rejected(session_client, workspace, project, env, create_user):
    from plane.db.models import Workspace

    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=2)
    r = session_client.post(issues_url(workspace, project), {"name": "x", "type_id": str(foreign.id)}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_issue_list_and_detail_return_type_id(session_client, workspace, project, env):
    state, t = env
    created = session_client.post(issues_url(workspace, project), {"name": "a", "type_id": str(t["bug"].id)}, format="json").json()
    detail = session_client.get(issues_url(workspace, project, f"{created['id']}/")).json()
    assert detail["type_id"] == str(t["bug"].id)
    listed = session_client.get(issues_url(workspace, project) + "?per_page=50").json()
    rows = listed["results"] if isinstance(listed, dict) and "results" in listed else listed
    flat = rows if isinstance(rows, list) else [i for g in rows.values() for i in (g if isinstance(g, list) else [])]
    assert any(i.get("type_id") == str(t["bug"].id) for i in flat)
    assert "is_epic" not in detail


@pytest.mark.contract
def test_sub_issue_bulk_assign_validated(session_client, workspace, project, env, create_user):
    state, t = env
    epic = Issue.objects.create(name="e", workspace=workspace, project=project, state=state, type=t["epic"], created_by=create_user)
    task = Issue.objects.create(name="t", workspace=workspace, project=project, state=state, type=t["task"], created_by=create_user)
    r = session_client.post(
        issues_url(workspace, project, f"{task.id}/sub-issues/"), {"sub_issue_ids": [str(epic.id)]}, format="json"
    )
    assert r.status_code == 400  # an epic cannot become a child
    epic.refresh_from_db()
    assert epic.parent_id is None


@pytest.mark.contract
def test_public_api_rejects_type_not_in_project(db, workspace, project, env):
    from plane.api.serializers.issue import IssueSerializer

    state, t = env
    ok = IssueSerializer(data={"name": "x", "type_id": str(t["bug"].id)}, context={"project_id": project.id})
    assert ok.is_valid(), ok.errors
    other_ws_type = IssueType.objects.create(workspace=workspace, name="Loose", level=0)
    bad = IssueSerializer(data={"name": "x", "type_id": str(other_ws_type.id)}, context={"project_id": project.id})
    assert not bad.is_valid()
