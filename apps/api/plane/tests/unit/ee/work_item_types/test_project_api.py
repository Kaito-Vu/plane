# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import uuid

import pytest

from plane.db.models import Issue, IssueType, ProjectMember, State, User, Workspace, WorkspaceMember
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.seed import apply_process


def url(ws, p, tail=""):
    return f"/api/workspaces/{ws.slug}/projects/{p.id}/work-item-types/{tail}"


def member(workspace, project, email, role=15, in_project=True):
    m = User.objects.create(email=email, username=email.split("@")[0])
    WorkspaceMember.objects.create(workspace=workspace, member=m, role=role)
    if in_project:
        ProjectMember.objects.create(project=project, member=m, workspace=workspace, role=role)
    return m


@pytest.mark.contract
def test_apply_process_then_get(session_client, workspace, project):
    r = session_client.post(url(workspace, project), {"process": "agile"}, format="json")
    assert r.status_code == 200, r.content
    body = session_client.get(url(workspace, project)).json()
    assert body["process"] == "agile" and body["enabled"] is True
    assert "User Story" in {t["name"] for t in body["types"]}


@pytest.mark.contract
def test_invalid_process(session_client, workspace, project):
    assert session_client.post(url(workspace, project), {"process": "kanban"}, format="json").status_code == 400


@pytest.mark.contract
def test_switch_blocked_returns_409(session_client, workspace, project, create_user):
    apply_process(project, "scrum")
    pbi = IssueType.objects.get(workspace=workspace, external_id="product_backlog_item")
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=pbi, created_by=create_user)
    assert session_client.post(url(workspace, project), {"process": "agile"}, format="json").status_code == 409


@pytest.mark.contract
def test_non_admin_cannot_apply(api_client, workspace, project):
    m = member(workspace, project, "m@plane.so")
    api_client.force_authenticate(user=m)
    assert api_client.post(url(workspace, project), {"process": "scrum"}, format="json").status_code == 403
    assert api_client.get(url(workspace, project)).status_code == 200


@pytest.mark.contract
def test_non_admin_cannot_assign_unassign_default(api_client, workspace, project):
    apply_process(project, "scrum")
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    ProjectIssueType.objects.create(project=project, issue_type=custom, level=1)
    m = member(workspace, project, "m2@plane.so")
    api_client.force_authenticate(user=m)
    body = {"type_id": str(custom.id)}
    assert api_client.post(url(workspace, project, "assign/"), body, format="json").status_code == 403
    assert api_client.delete(url(workspace, project, f"assign/{custom.id}/")).status_code == 403
    assert api_client.post(url(workspace, project, "default/"), body, format="json").status_code == 403


@pytest.mark.contract
def test_non_project_member_cannot_read(api_client, workspace, project):
    m = member(workspace, project, "m3@plane.so", in_project=False)
    api_client.force_authenticate(user=m)
    assert api_client.get(url(workspace, project)).status_code == 403


@pytest.mark.contract
def test_assign_and_unassign_custom_type(session_client, workspace, project):
    apply_process(project, "scrum")
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    assert session_client.post(url(workspace, project, "assign/"), {"type_id": str(custom.id)}, format="json").status_code == 200
    assert ProjectIssueType.objects.filter(project=project, issue_type=custom).exists()
    assert session_client.delete(url(workspace, project, f"assign/{custom.id}/")).status_code == 204


@pytest.mark.contract
def test_assign_foreign_type_rejected_generic(session_client, workspace, project, create_user):
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=1)
    r = session_client.post(url(workspace, project, "assign/"), {"type_id": str(foreign.id)}, format="json")
    assert r.status_code == 400 and r.json() == {"error": "Invalid work item type"}


@pytest.mark.contract
def test_assign_inactive_type_rejected(session_client, workspace, project):
    t = IssueType.objects.create(workspace=workspace, name="Old", level=1, is_active=False)
    r = session_client.post(url(workspace, project, "assign/"), {"type_id": str(t.id)}, format="json")
    assert r.status_code == 400 and r.json() == {"error": "Invalid work item type"}


@pytest.mark.contract
@pytest.mark.parametrize("bad", ["not-a-uuid", None, 123, ""])
def test_invalid_uuid_body_is_400(session_client, workspace, project, bad):
    for tail in ("assign/", "default/"):
        r = session_client.post(url(workspace, project, tail), {"type_id": bad}, format="json")
        assert r.status_code == 400, (tail, bad, r.content)


@pytest.mark.contract
def test_invalid_uuid_in_url_is_400_or_404(session_client, workspace, project):
    assert session_client.delete(url(workspace, project, "assign/not-a-uuid/")).status_code in (400, 404)


@pytest.mark.contract
def test_unassign_not_assigned_is_404(session_client, workspace, project):
    t = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    assert session_client.delete(url(workspace, project, f"assign/{t.id}/")).status_code == 404
    assert session_client.delete(url(workspace, project, f"assign/{uuid.uuid4()}/")).status_code == 404


@pytest.mark.contract
def test_cannot_unassign_default_or_in_use(session_client, workspace, project, create_user):
    apply_process(project, "scrum")
    types = {t.external_id: t for t in IssueType.objects.filter(workspace=workspace)}
    assert session_client.delete(url(workspace, project, f"assign/{types['product_backlog_item'].id}/")).status_code == 409
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=types["task"], created_by=create_user)
    assert session_client.delete(url(workspace, project, f"assign/{types['task'].id}/")).status_code == 409


@pytest.mark.contract
def test_set_default(session_client, workspace, project):
    apply_process(project, "scrum")
    task = IssueType.objects.get(workspace=workspace, external_id="task")
    assert session_client.post(url(workspace, project, "default/"), {"type_id": str(task.id)}, format="json").status_code == 200
    assert ProjectIssueType.objects.get(project=project, is_default=True).issue_type_id == task.id


@pytest.mark.contract
def test_set_default_unassigned_keeps_old(session_client, workspace, project):
    apply_process(project, "scrum")
    old = ProjectIssueType.objects.get(project=project, is_default=True).issue_type_id
    t = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    r = session_client.post(url(workspace, project, "default/"), {"type_id": str(t.id)}, format="json")
    assert r.status_code == 400
    assert ProjectIssueType.objects.get(project=project, is_default=True).issue_type_id == old
