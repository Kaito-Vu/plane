# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from rest_framework.exceptions import ValidationError

from plane.db.models import DraftIssue, Issue, IssueType, State, User, Workspace, WorkspaceMember
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.seed import apply_process


def ws_url(ws, tail=""):
    return f"/api/workspaces/{ws.slug}/work-item-types/{tail}"


def p_url(ws, p, tail=""):
    return f"/api/workspaces/{ws.slug}/projects/{p.id}/work-item-types/{tail}"


def issues_url(ws, p, tail=""):
    return f"/api/workspaces/{ws.slug}/projects/{p.id}/issues/{tail}"


@pytest.fixture
def env(db, workspace, project, create_user):
    apply_process(project, "scrum")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    t = {x.external_id: x for x in IssueType.objects.filter(workspace=workspace)}

    def make(name, key=None, parent=None, legacy=False):
        i = Issue.objects.create(
            name=name,
            workspace=workspace,
            project=project,
            state=state,
            parent=parent,
            type=t[key] if key else None,
            created_by=create_user,
        )
        if legacy:
            Issue.objects.filter(pk=i.pk).update(type=None)
            i.refresh_from_db()
        return i

    return make, t


def draft(workspace, project, create_user, t):
    return DraftIssue.objects.create(name="d", workspace=workspace, project=project, type=t, created_by=create_user)


# 1
@pytest.mark.contract
def test_search_issues_returns_type_id(session_client, workspace, project, env):
    make, t = env
    make("findme", "bug")
    r = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/search-issues/?search=findme")
    assert r.status_code == 200
    assert r.json()[0]["type_id"] == str(t["bug"].id)


# 2
@pytest.mark.unit
def test_legacy_reparent_allowed(env):
    make, t = env
    a, b = make("a", legacy=True), make("b", legacy=True)
    a.parent = b
    a.save()
    assert Issue.objects.get(pk=a.pk).parent_id == b.pk


@pytest.mark.unit
def test_legacy_under_typed_and_typed_under_legacy_allowed(env):
    make, t = env
    legacy, typed = make("l", legacy=True), make("t", "task")
    legacy.parent = typed
    legacy.save()
    typed2 = make("t2", "task")
    legacy2 = make("l2", legacy=True)
    typed2.parent = legacy2
    typed2.save()


@pytest.mark.unit
def test_typed_task_under_task_still_fails_and_legacy_cycle_rejected(env):
    make, t = env
    a, b = make("a", "task"), make("b", "task")
    a.parent = b
    with pytest.raises(ValidationError):
        a.save()
    x, y = make("x", legacy=True), make("y", legacy=True)
    y.parent = x
    y.save()
    x.parent = y
    with pytest.raises(ValidationError):
        x.save()


@pytest.mark.unit
def test_type_change_ignores_legacy_children(env):
    make, t = env
    parent = make("p", "bug")
    make("c", "task", parent=parent, legacy=True)
    parent.type = t["task"]
    parent.save()


@pytest.mark.contract
def test_bulk_sub_issues_legacy_ok(session_client, workspace, project, env):
    make, t = env
    a, b = make("a", legacy=True), make("b", legacy=True)
    r = session_client.post(
        issues_url(workspace, project, f"{a.id}/sub-issues/"), {"sub_issue_ids": [str(b.id)]}, format="json"
    )
    assert r.status_code == 200, r.content
    assert Issue.objects.get(pk=b.pk).parent_id == a.pk


# 3
@pytest.mark.unit
def test_apply_process_blocked_carries_count_and_state_unchanged(env, project, workspace, create_user):
    from plane.ee.work_item_types.seed import ProcessChangeBlocked, project_process

    make, t = env
    make("i")
    draft(workspace, project, create_user, t["product_backlog_item"])
    with pytest.raises(ProcessChangeBlocked) as e:
        apply_process(project, "agile")
    assert e.value.count == 2
    assert project_process(project) == "scrum"


@pytest.mark.contract
def test_switch_migrate_true_retypes(session_client, workspace, project, env, create_user):
    make, t = env
    i = make("i")
    d = draft(workspace, project, create_user, t["product_backlog_item"])
    r = session_client.post(p_url(workspace, project), {"process": "agile", "migrate": True}, format="json")
    assert r.status_code == 200, r.content
    i.refresh_from_db()
    d.refresh_from_db()
    assert i.type_id == d.type_id == t["user_story"].id
    assert session_client.get(p_url(workspace, project)).json()["process"] == "agile"


@pytest.mark.contract
def test_switch_blocked_body(session_client, workspace, project, env):
    make, t = env
    make("i")
    r = session_client.post(p_url(workspace, project), {"process": "agile", "migrate": False}, format="json")
    assert r.status_code == 409
    assert r.json()["code"] == "process_change_blocked" and r.json()["count"] == 1 and r.json()["error"]
    assert session_client.get(p_url(workspace, project)).json()["process"] == "scrum"


# 4
@pytest.mark.contract
def test_assign_other_process_exclusive_conflicts(session_client, workspace, project, env):
    make, t = env
    r = session_client.post(p_url(workspace, project, "assign/"), {"type_id": str(t["user_story"].id)}, format="json")
    assert r.status_code == 409 and r.json()["code"] == "process_conflict"
    assert not ProjectIssueType.objects.filter(project=project, issue_type=t["user_story"]).exists()


@pytest.mark.contract
def test_unassign_current_exclusive_refused(session_client, workspace, project, env):
    make, t = env
    r = session_client.delete(p_url(workspace, project, f"assign/{t['product_backlog_item'].id}/"))
    assert r.status_code == 409


# 5
@pytest.mark.contract
def test_epic_needs_level_one_or_more(session_client, workspace, project, env):
    r = session_client.post(ws_url(workspace), {"name": "E0", "level": 0, "is_epic": True}, format="json")
    assert r.status_code == 400 and "is_epic" in r.json()
    ok = session_client.post(ws_url(workspace), {"name": "E1", "level": 1, "is_epic": True}, format="json")
    assert ok.status_code == 201
    plain = IssueType.objects.create(workspace=workspace, name="Z", level=0)
    r = session_client.patch(ws_url(workspace, f"{plain.id}/"), {"is_epic": True}, format="json")
    assert r.status_code == 400 and "is_epic" in r.json()


# 6
@pytest.mark.contract
def test_draft_blocks_unassign(session_client, workspace, project, env, create_user):
    make, t = env
    draft(workspace, project, create_user, t["task"])
    r = session_client.delete(p_url(workspace, project, f"assign/{t['task'].id}/"))
    assert r.status_code == 409 and r.json()["count"] == 1


@pytest.mark.contract
def test_soft_deleted_issue_blocks_workspace_delete(session_client, workspace, project, env):
    make, t = env
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    i = make("i", "task")
    Issue.objects.filter(pk=i.pk).update(type=custom)
    Issue.objects.get(pk=i.pk).delete()
    assert not Issue.objects.filter(pk=i.pk).exists()
    r = session_client.delete(ws_url(workspace, f"{custom.id}/"))
    assert r.status_code == 409 and r.json()["count"] == 1


# 7
@pytest.mark.contract
def test_bulk_error_body_is_detail(session_client, workspace, project, env):
    make, t = env
    task, epic = make("t", "task"), make("e", "epic")
    r = session_client.post(
        issues_url(workspace, project, f"{task.id}/sub-issues/"), {"sub_issue_ids": [str(epic.id)]}, format="json"
    )
    assert r.status_code == 400
    assert "parent_id" in r.json() and "error" not in r.json()


# 8
@pytest.mark.contract
def test_seed_endpoint(session_client, api_client, workspace):
    r = session_client.post(ws_url(workspace, "seed/"), "x", content_type="application/json")
    assert r.status_code == 200
    assert {x["name"] for x in r.json()} >= {"Epic", "Task"}
    assert session_client.post(ws_url(workspace, "seed/"), {}, format="json").status_code == 200
    assert IssueType.objects.filter(workspace=workspace, external_id="epic").count() == 1
    member = User.objects.create(email="m8@plane.so", username="m8")
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    api_client.force_authenticate(user=member)
    assert api_client.post(ws_url(workspace, "seed/"), {}, format="json").status_code == 403


@pytest.mark.contract
def test_seed_endpoint_other_workspace_admin_forbidden(api_client, workspace):
    other_admin = User.objects.create(email="o8@plane.so", username="o8")
    other = Workspace.objects.create(name="O", owner=other_admin, slug="other8")
    WorkspaceMember.objects.create(workspace=other, member=other_admin, role=20)
    api_client.force_authenticate(user=other_admin)
    assert api_client.post(ws_url(workspace, "seed/"), {}, format="json").status_code == 403


# 9
@pytest.mark.contract
def test_usage_endpoint(session_client, workspace, project, env, create_user):
    make, t = env
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    a, gone = make("a", "task"), make("g", "task")
    Issue.objects.filter(pk__in=[a.pk, gone.pk]).update(type=custom)
    Issue.objects.get(pk=gone.pk).delete()
    draft(workspace, project, create_user, custom)
    r = session_client.get(ws_url(workspace, f"{custom.id}/usage/"))
    assert r.status_code == 200
    assert r.json() == {"issues": 2, "drafts": 1, "count": 3, "projects": [str(project.id)]}


@pytest.mark.contract
def test_usage_other_workspace_404(session_client, workspace, create_user):
    other = Workspace.objects.create(name="O", owner=create_user, slug="other9")
    foreign = IssueType.objects.create(workspace=other, name="F", level=1)
    assert session_client.get(ws_url(workspace, f"{foreign.id}/usage/")).status_code == 404


# 10
@pytest.mark.contract
def test_contract_type_id_and_no_is_epic(session_client, workspace, project, env):
    make, t = env
    parent = make("p", "product_backlog_item")
    child = make("c", "task", parent=parent)
    detail = session_client.get(issues_url(workspace, project, f"{child.id}/")).json()
    assert detail["type_id"] == str(t["task"].id) and "is_epic" not in detail
    listed = session_client.get(issues_url(workspace, project) + "?per_page=50").json()
    rows = listed["results"]
    flat = rows if isinstance(rows, list) else [i for g in rows.values() for i in g]
    assert flat and all("type_id" in i and "is_epic" not in i for i in flat)
    subs = session_client.get(issues_url(workspace, project, f"{parent.id}/sub-issues/")).json()
    assert subs["sub_issues"] and all("type_id" in i and "is_epic" not in i for i in subs["sub_issues"])


@pytest.mark.unit
def test_switch_counts_and_migrates_soft_deleted_old_exclusive(env, project, workspace):
    from plane.ee.work_item_types.seed import ProcessChangeBlocked

    make, t = env
    i = make("i")
    Issue.all_objects.filter(pk=i.pk).update(type=t["product_backlog_item"], deleted_at="2026-01-01T00:00:00Z")
    with pytest.raises(ProcessChangeBlocked) as e:
        apply_process(project, "agile")
    assert e.value.count == 1
    apply_process(project, "agile", migrate=True)
    assert Issue.all_objects.get(pk=i.pk).type.external_id == "user_story"


@pytest.mark.contract
def test_patch_level_refused_for_draft_only_and_soft_deleted_only(
    session_client, workspace, project, env, create_user
):
    make, t = env
    d_type = IssueType.objects.create(workspace=workspace, name="DraftOnly", level=1)
    s_type = IssueType.objects.create(workspace=workspace, name="SoftOnly", level=1)
    draft(workspace, project, create_user, d_type)
    i = make("s")
    Issue.all_objects.filter(pk=i.pk).update(type=s_type, deleted_at="2026-01-01T00:00:00Z")
    for ty in (d_type, s_type):
        r = session_client.patch(ws_url(workspace, f"{ty.id}/"), {"level": 0}, format="json")
        assert r.status_code == 409


@pytest.mark.contract
def test_usage_projects_only_for_admins(session_client, api_client, workspace, project, env, create_user):
    make, t = env
    custom = IssueType.objects.create(workspace=workspace, name="Spike2", level=1)
    draft(workspace, project, create_user, custom)
    url = ws_url(workspace, f"{custom.id}/usage/")
    assert session_client.get(url).json()["projects"] == [str(project.id)]
    member = User.objects.create(email="m3@plane.so", username="m3")
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    api_client.force_authenticate(user=member)
    body = api_client.get(url).json()
    assert body["projects"] == [] and body["count"] == 1
