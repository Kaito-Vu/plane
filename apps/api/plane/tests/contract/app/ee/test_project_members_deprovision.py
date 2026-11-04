from unittest import mock
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from plane.celery import app
from plane.db.models import Project, ProjectMember, User, Workspace, WorkspaceMember
from plane.ee.project_members.tasks import ee_sweep_orphan_workspace_members


@pytest.fixture(autouse=True)
def _no_celery(db):
    with mock.patch("plane.app.views.project.member.project_add_user_email"):
        yield


def mk_user(prefix="u"):
    n = uuid4().hex[:8]
    return User.objects.create(email=f"{prefix}-{n}@plane.so", username=f"{prefix}_{n}")


def ws_row(workspace, user):
    return WorkspaceMember.objects.get(workspace=workspace, member=user)


def mk_project(workspace, owner, ident):
    p = Project.objects.create(name=ident, identifier=ident, workspace=workspace, created_by=owner)
    ProjectMember.objects.create(project=p, member=owner, workspace=workspace, role=20)
    return p


def add_member(workspace, project, user, role=15):
    return ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=role)


def base(workspace, project):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/"


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.contract
@pytest.mark.django_db
class TestDeprovision:
    def test_destroy_last_project_disables_ws_member_and_hides_workspace(self, session_client, workspace, project):
        user = mk_user()
        pm = add_member(workspace, project, user)
        assert ws_row(workspace, user).is_active
        r = session_client.delete(base(workspace, project) + f"{pm.id}/")
        assert r.status_code == 204
        assert not ws_row(workspace, user).is_active
        r = client_for(user).get("/api/users/me/workspaces/")
        assert workspace.slug not in [w["slug"] for w in r.json()]

    def test_destroy_with_other_project_keeps_ws_member(self, session_client, workspace, project, create_user):
        other = mk_project(workspace, create_user, "OTH")
        user = mk_user()
        pm = add_member(workspace, project, user)
        add_member(workspace, other, user)
        assert session_client.delete(base(workspace, project) + f"{pm.id}/").status_code == 204
        assert ws_row(workspace, user).is_active

    def test_leave_last_project_disables(self, workspace, project):
        user = mk_user()
        add_member(workspace, project, user)
        r = client_for(user).post(base(workspace, project) + "leave/")
        assert r.status_code == 204
        assert not ws_row(workspace, user).is_active

    def test_readd_reactivates(self, session_client, workspace, project):
        user = mk_user()
        pm = add_member(workspace, project, user)
        session_client.delete(base(workspace, project) + f"{pm.id}/")
        assert not ws_row(workspace, user).is_active
        r = session_client.post(base(workspace, project), {"members": [{"member_id": str(user.id), "role": 15}]}, format="json")
        assert r.status_code == 201
        assert ws_row(workspace, user).is_active

    def test_ws_admin_and_owner_never_disabled(self, session_client, workspace, project, create_user):
        admin = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=admin, role=20)
        pm = add_member(workspace, project, admin, role=15)
        session_client.delete(base(workspace, project) + f"{pm.id}/")
        assert ws_row(workspace, admin).is_active
        # owner leaving their last project via a second admin
        pm_owner = ProjectMember.objects.get(project=project, member=create_user)
        add_member(workspace, project, mk_user(), role=20)
        pm_owner.is_active = False
        pm_owner.save()
        assert ws_row(workspace, create_user).is_active

    def test_user_in_two_workspaces_only_affected_workspace_disabled(self, session_client, workspace, project, create_user):
        ws2 = Workspace.objects.create(name="W2", owner=create_user, slug="w2-slug")
        WorkspaceMember.objects.create(workspace=ws2, member=create_user, role=20)
        p2 = mk_project(ws2, create_user, "TWO")
        user = mk_user()
        pm = add_member(workspace, project, user)
        add_member(ws2, p2, user)
        session_client.delete(base(workspace, project) + f"{pm.id}/")
        assert not ws_row(workspace, user).is_active
        assert ws_row(ws2, user).is_active

    def test_project_soft_delete_then_sweep_disables(self, workspace, project):
        user = mk_user()
        add_member(workspace, project, user)
        project.delete()  # soft delete; ProjectMember rows stay active
        assert ws_row(workspace, user).is_active
        assert ee_sweep_orphan_workspace_members() >= 1
        assert not ws_row(workspace, user).is_active

    def test_routine_save_of_active_project_member_does_not_reprovision_suspended_ws_member(self, workspace, project):
        user = mk_user()
        pm = add_member(workspace, project, user)
        WorkspaceMember.objects.filter(workspace=workspace, member=user).update(is_active=False)
        pm.sort_order = 99
        pm.save()
        assert not ws_row(workspace, user).is_active

    def test_created_project_member_via_save_gets_ws_row(self, workspace, project):
        user = mk_user()
        assert not WorkspaceMember.objects.filter(workspace=workspace, member=user).exists()
        add_member(workspace, project, user, role=5)
        assert ws_row(workspace, user).is_active
        assert ws_row(workspace, user).role == 5

    def test_beat_entry_registered(self):
        entry = app.conf.beat_schedule["ee-sweep-orphan-workspace-members"]
        assert entry["task"] == "plane.ee.project_members.tasks.ee_sweep_orphan_workspace_members"

    def test_sweep_task_registered(self):
        assert "plane.ee.project_members.tasks.ee_sweep_orphan_workspace_members" in app.tasks
