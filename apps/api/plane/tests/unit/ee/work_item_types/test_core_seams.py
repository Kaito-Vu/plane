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
    epic = session_client.post(
        issues_url(workspace, project), {"name": "e", "type_id": str(t["epic"].id)}, format="json"
    ).json()
    r = session_client.post(
        issues_url(workspace, project),
        {"name": "s", "type_id": str(t["sub_task"].id), "parent_id": epic["id"]},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.contract
def test_patch_change_type_validated(session_client, workspace, project, env):
    state, t = env
    pbi = session_client.post(issues_url(workspace, project), {"name": "p"}, format="json").json()
    session_client.post(
        issues_url(workspace, project),
        {"name": "t", "type_id": str(t["task"].id), "parent_id": pbi["id"]},
        format="json",
    )
    r = session_client.patch(
        issues_url(workspace, project, f"{pbi['id']}/"), {"type_id": str(t["task"].id)}, format="json"
    )
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
    created = session_client.post(
        issues_url(workspace, project), {"name": "a", "type_id": str(t["bug"].id)}, format="json"
    ).json()
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
    epic = Issue.objects.create(
        name="e", workspace=workspace, project=project, state=state, type=t["epic"], created_by=create_user
    )
    task = Issue.objects.create(
        name="t", workspace=workspace, project=project, state=state, type=t["task"], created_by=create_user
    )
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


@pytest.mark.contract
def test_sub_issue_bulk_is_all_or_nothing(session_client, workspace, project, env, create_user):
    state, t = env
    mk = lambda n, ty: Issue.objects.create(  # noqa: E731
        name=n, workspace=workspace, project=project, state=state, type=ty, created_by=create_user
    )
    parent, good, epic = mk("p", t["product_backlog_item"]), mk("g", t["task"]), mk("e", t["epic"])
    r = session_client.post(
        issues_url(workspace, project, f"{parent.id}/sub-issues/"),
        {"sub_issue_ids": [str(good.id), str(epic.id)]},
        format="json",
    )
    assert r.status_code == 400
    good.refresh_from_db()
    epic.refresh_from_db()
    assert good.parent_id is None and epic.parent_id is None


@pytest.mark.contract
def test_public_api_error_message_and_null_type(db, workspace, project, env):
    from plane.api.serializers.issue import IssueSerializer

    loose = IssueType.objects.create(workspace=workspace, name="Loose2", level=0)
    bad = IssueSerializer(data={"name": "x", "type_id": str(loose.id)}, context={"project_id": project.id})
    assert not bad.is_valid()
    assert "Invalid work item type" in str(bad.errors)
    none = IssueSerializer(data={"name": "x", "type_id": None}, context={"project_id": project.id})
    assert none.is_valid(), none.errors


@pytest.mark.contract
def test_foreign_and_unknown_type_same_error(session_client, workspace, project, env, create_user):
    import uuid

    from plane.db.models import Workspace

    other = Workspace.objects.create(name="O2", owner=create_user, slug="other2")
    foreign = IssueType.objects.create(workspace=other, name="F", level=2)
    bodies = []
    for tid in (foreign.id, uuid.uuid4()):
        r = session_client.post(issues_url(workspace, project), {"name": "x", "type_id": str(tid)}, format="json")
        assert r.status_code == 400
        bodies.append(r.json())
    assert bodies[0] == bodies[1]


GENERIC = {"type_id": ["Invalid work item type"]}


@pytest.mark.contract
def test_foreign_type_rejected_when_feature_off_issue_and_draft(session_client, workspace, project, create_user):
    from plane.db.models import DraftIssue, Workspace

    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=2)
    assert not project.is_issue_type_enabled
    r = session_client.post(issues_url(workspace, project), {"name": "x", "type_id": str(foreign.id)}, format="json")
    assert r.status_code == 400 and r.json() == GENERIC
    assert not Issue.objects.filter(name="x").exists()
    r = session_client.post(
        f"/api/workspaces/{workspace.slug}/draft-issues/",
        {"name": "d", "project_id": str(project.id), "type_id": str(foreign.id)},
        format="json",
    )
    assert r.status_code == 400 and r.json() == GENERIC
    assert not DraftIssue.objects.filter(name="d").exists()


@pytest.mark.contract
def test_draft_to_issue_carries_type(session_client, workspace, project, env, create_user):
    from plane.db.models import DraftIssue, Workspace

    state, t = env
    draft = DraftIssue.objects.create(name="d", workspace=workspace, project=project, created_by=create_user)
    DraftIssue.objects.filter(pk=draft.pk).update(created_by=create_user)
    url = f"/api/workspaces/{workspace.slug}/draft-to-issue/{draft.id}/"
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=2)
    r = session_client.post(url, {"name": "d", "type_id": str(foreign.id)}, format="json")
    assert r.status_code == 400 and r.json() == GENERIC
    r = session_client.post(url, {"name": "d", "type_id": str(t["bug"].id)}, format="json")
    assert r.status_code == 201, r.content
    assert Issue.objects.get(pk=r.json()["id"]).type_id == t["bug"].id


@pytest.mark.contract
def test_epic_with_children_cannot_become_non_epic(session_client, workspace, project, env):
    state, t = env
    epic = session_client.post(
        issues_url(workspace, project), {"name": "e", "type_id": str(t["epic"].id)}, format="json"
    ).json()
    lone = session_client.post(
        issues_url(workspace, project), {"name": "l", "type_id": str(t["epic"].id)}, format="json"
    ).json()
    r = session_client.post(
        issues_url(workspace, project),
        {"name": "f", "type_id": str(t["feature"].id), "parent_id": epic["id"]},
        format="json",
    )
    assert r.status_code == 201, r.content
    r = session_client.patch(
        issues_url(workspace, project, f"{epic['id']}/"), {"type_id": str(t["bug"].id)}, format="json"
    )
    assert r.status_code == 400
    assert "epic with sub-items" in str(r.json())
    r = session_client.patch(
        issues_url(workspace, project, f"{lone['id']}/"), {"type_id": str(t["bug"].id)}, format="json"
    )
    assert r.status_code == 204, r.content
