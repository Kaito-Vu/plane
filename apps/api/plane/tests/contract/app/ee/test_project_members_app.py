import inspect
from unittest import mock
from uuid import uuid4

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from plane.app.views.project.member import ProjectMemberViewSet
from plane.db.models import Project, ProjectMember, User, WorkspaceMember
from plane.ee.project_members.views import EeProjectMemberViewSet


@pytest.fixture(autouse=True)
def _no_celery(db):
    with (
        mock.patch("plane.app.views.project.member.project_add_user_email"),
        mock.patch("plane.app.views.project.member.base_host", return_value="http://testserver"),
    ):
        yield


def mk_user(prefix="u", **kw):
    n = uuid4().hex[:8]
    return User.objects.create(email=f"{prefix}-{n}@plane.so", username=f"{prefix}_{n}", **kw)


def url(workspace, project, pk=None):
    base = f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/"
    return base + (f"{pk}/" if pk else "")


def add(client, workspace, project, members):
    return client.post(url(workspace, project), {"members": members}, format="json")


@pytest.mark.contract
@pytest.mark.django_db
class TestEeProjectMembers:
    def test_route_resolves_to_ee_view(self, workspace, project):
        assert resolve(url(workspace, project)).func.cls is EeProjectMemberViewSet
        assert resolve(url(workspace, project, uuid4())).func.cls is EeProjectMemberViewSet
        assert resolve(url(workspace, project) + "leave/").func.cls is EeProjectMemberViewSet

    def test_core_create_signature_unchanged(self):
        sig = inspect.signature(ProjectMemberViewSet.create.__wrapped__)
        assert list(sig.parameters) == ["self", "request", "slug", "project_id"]

    def test_add_existing_user_without_ws_membership_creates_both_rows(self, session_client, workspace, project):
        user = mk_user()
        r = add(session_client, workspace, project, [{"member_id": str(user.id), "role": 15}])
        assert r.status_code == 201
        assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 15
        assert ProjectMember.objects.get(project=project, member=user).is_active
        c = APIClient()
        c.force_authenticate(user=user)
        r = c.get("/api/users/me/workspaces/")
        assert r.status_code == 200
        assert workspace.slug in [w["slug"] for w in r.json()]

    def test_add_unknown_user_400_user_not_eligible_and_no_rows(self, session_client, workspace, project):
        good = mk_user()
        r = add(session_client, workspace, project, [{"member_id": str(good.id)}, {"member_id": str(uuid4())}])
        assert r.status_code == 400
        assert r.json()["code"] == "USER_NOT_ELIGIBLE"
        assert not WorkspaceMember.objects.filter(member=good).exists()
        assert not ProjectMember.objects.filter(member=good).exists()

    def test_add_inactive_and_bot_user_same_error_shape(self, session_client, workspace, project):
        bodies = []
        for u in (mk_user(is_active=False), mk_user(is_bot=True)):
            r = add(session_client, workspace, project, [{"member_id": str(u.id)}])
            assert r.status_code == 400
            bodies.append(r.json())
            assert not WorkspaceMember.objects.filter(member=u).exists()
        assert bodies[0] == bodies[1]
        assert bodies[0]["code"] == "USER_NOT_ELIGIBLE"

    def test_malformed_member_id_400(self, session_client, workspace, project):
        for mid in ("not-a-uuid", None):
            r = add(session_client, workspace, project, [{"member_id": mid}])
            assert r.status_code == 400
            assert r.json()["code"] == "USER_NOT_ELIGIBLE"

    @pytest.mark.parametrize("members", [[], None, "x", {"member_id": "a"}])
    def test_empty_members_400(self, session_client, workspace, project, members):
        r = session_client.post(url(workspace, project), {"members": members}, format="json")
        assert r.status_code == 400
        assert r.json()["error"] == "At least one member is required"

    def test_project_admin_of_other_project_403(self, workspace, project):
        other = Project.objects.create(name="O", identifier="OTH", workspace=workspace)
        admin = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=admin, role=15)
        ProjectMember.objects.create(project=other, member=admin, workspace=workspace, role=20)
        target = mk_user()
        c = APIClient()
        c.force_authenticate(user=admin)
        r = add(c, workspace, project, [{"member_id": str(target.id), "role": 5}])
        assert r.status_code == 403
        assert not WorkspaceMember.objects.filter(member=target).exists()

    def test_guest_role_gets_ws_guest(self, session_client, workspace, project):
        user = mk_user()
        assert add(session_client, workspace, project, [{"member_id": str(user.id), "role": 5}]).status_code == 201
        assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 5

    def test_already_active_member_no_duplicate(self, session_client, workspace, project):
        user = mk_user()
        for _ in range(2):
            r = add(session_client, workspace, project, [{"member_id": str(user.id), "role": 15}])
            assert r.status_code == 201
        assert WorkspaceMember.objects.filter(workspace=workspace, member=user).count() == 1
        assert ProjectMember.objects.filter(project=project, member=user).count() == 1

    def test_patch_role_to_member_raises_ws_guest_to_15(self, session_client, workspace, project):
        user = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=5)
        pm = ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=5)
        r = session_client.patch(url(workspace, project, pm.id), {"role": 15}, format="json")
        assert r.status_code == 200
        pm.refresh_from_db()
        assert pm.role == 15
        assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 15

    def test_patch_role_20_by_non_ws_admin_keeps_core_403(self, workspace, project):
        admin = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=admin, role=15)
        ProjectMember.objects.create(project=project, member=admin, workspace=workspace, role=20)
        user = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=5)
        pm = ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=5)
        c = APIClient()
        c.force_authenticate(user=admin)
        r = c.patch(url(workspace, project, pm.id), {"role": 20}, format="json")
        assert r.status_code == 403
        assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 5  # rolled back

    def test_add_ws_admin_target_as_member_returns_core_400(self, session_client, workspace, project):
        wsadmin = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=wsadmin, role=20)
        r = add(session_client, workspace, project, [{"member_id": str(wsadmin.id), "role": 15}])
        assert r.status_code == 400
        assert WorkspaceMember.objects.get(workspace=workspace, member=wsadmin).role == 20
        assert not ProjectMember.objects.filter(project=project, member=wsadmin).exists()

    def test_hyphenless_member_id_adds_user_201(self, session_client, workspace, project):
        user = mk_user()
        r = add(session_client, workspace, project, [{"member_id": user.id.hex, "role": 15}])
        assert r.status_code == 201
        assert ProjectMember.objects.get(project=project, member=user).is_active

    def test_uppercase_member_id_readd_inactive_member_no_500(self, session_client, workspace, project):
        user = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=15)
        ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=5, is_active=False)
        r = add(session_client, workspace, project, [{"member_id": str(user.id).upper(), "role": 15}])
        assert r.status_code == 201
        pm = ProjectMember.objects.get(project=project, member=user)
        assert pm.is_active and pm.role == 15

    def test_duplicate_ids_different_spelling_single_project_member_row(self, session_client, workspace, project):
        user = mk_user()
        r = add(
            session_client,
            workspace,
            project,
            [{"member_id": str(user.id), "role": 5}, {"member_id": user.id.hex, "role": 15}],
        )
        assert r.status_code == 201
        assert ProjectMember.objects.filter(project=project, member=user).count() == 1
        assert ProjectMember.objects.get(project=project, member=user).role == 15  # last wins

    @pytest.mark.parametrize("role", [[15], {"a": 1}])
    def test_unhashable_role_400(self, session_client, workspace, project, role):
        user = mk_user()
        r = add(session_client, workspace, project, [{"member_id": str(user.id), "role": role}])
        assert r.status_code == 400
        assert not WorkspaceMember.objects.filter(member=user).exists()
