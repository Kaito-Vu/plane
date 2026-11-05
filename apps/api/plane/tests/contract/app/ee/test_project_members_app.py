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

    def test_already_active_member_rejected_400_nothing_written(self, session_client, workspace, project):
        user = mk_user()
        assert add(session_client, workspace, project, [{"member_id": str(user.id), "role": 15}]).status_code == 201
        r = add(session_client, workspace, project, [{"member_id": str(user.id), "role": 5}])
        assert r.status_code == 400
        assert r.json()["code"] == "ALREADY_MEMBER"
        assert WorkspaceMember.objects.filter(workspace=workspace, member=user).count() == 1
        pm = ProjectMember.objects.get(project=project, member=user)
        assert pm.role == 15 and pm.is_active

    def test_patch_ws_guest_to_project_member_returns_core_400_no_ws_change(self, session_client, workspace, project):
        user = mk_user()
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=5)
        pm = ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=5)
        r = session_client.patch(url(workspace, project, pm.id), {"role": 15}, format="json")
        assert r.status_code == 400
        pm.refresh_from_db()
        assert pm.role == 5
        assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 5

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


def _project_admin_not_ws_admin(workspace, project):
    admin = mk_user("padm")
    WorkspaceMember.objects.create(workspace=workspace, member=admin, role=15)
    ProjectMember.objects.create(project=project, member=admin, workspace=workspace, role=20)
    c = APIClient()
    c.force_authenticate(user=admin)
    return admin, c


@pytest.mark.contract
@pytest.mark.django_db
class TestMemberCreateHardening:
    def test_peer_demotion_via_post_rejected(self, workspace, project):
        _, c = _project_admin_not_ws_admin(workspace, project)
        peer = mk_user("peer")
        WorkspaceMember.objects.create(workspace=workspace, member=peer, role=15)
        pm = ProjectMember.objects.create(project=project, member=peer, workspace=workspace, role=20)
        r = add(c, workspace, project, [{"member_id": str(peer.id), "role": 5}])
        assert r.status_code == 400 and r.json()["code"] == "ALREADY_MEMBER"
        pm.refresh_from_db()
        assert pm.role == 20

    def test_role_20_by_non_ws_admin_rejected(self, workspace, project):
        _, c = _project_admin_not_ws_admin(workspace, project)
        target = mk_user()
        r = add(c, workspace, project, [{"member_id": str(target.id), "role": 20}])
        assert r.status_code == 400 and r.json()["code"] == "ROLE_NOT_ALLOWED"
        assert not WorkspaceMember.objects.filter(member=target).exists()
        assert not ProjectMember.objects.filter(project=project, member=target).exists()

    def test_role_20_by_ws_admin_allowed(self, session_client, workspace, project):
        target = mk_user()
        r = add(session_client, workspace, project, [{"member_id": str(target.id), "role": 20}])
        assert r.status_code == 201, r.content
        assert ProjectMember.objects.get(project=project, member=target).role == 20

    def test_removed_member_can_be_readded(self, session_client, workspace, project):
        user = mk_user()
        assert add(session_client, workspace, project, [{"member_id": str(user.id), "role": 15}]).status_code == 201
        pm = ProjectMember.objects.get(project=project, member=user)
        assert session_client.delete(url(workspace, project, pm.id)).status_code == 204
        assert add(session_client, workspace, project, [{"member_id": str(user.id), "role": 15}]).status_code == 201
        assert ProjectMember.objects.get(project=project, member=user).is_active

    def test_add_with_allocation_dates_saved_and_listed(self, session_client, workspace, project):
        user = mk_user()
        m = {"member_id": str(user.id), "role": 15, "start_date": "2026-01-01", "end_date": "2026-06-30"}
        assert add(session_client, workspace, project, [m]).status_code == 201
        pm = ProjectMember.objects.get(project=project, member=user)
        assert str(pm.allocation.start_date) == "2026-01-01" and str(pm.allocation.end_date) == "2026-06-30"
        rows = session_client.get(url(workspace, project) + "allocations/").json()
        assert rows[str(pm.id)] == {"start_date": "2026-01-01", "end_date": "2026-06-30"}

    @pytest.mark.parametrize("start,end", [("2026-06-30", "2026-01-01"), ("not-a-date", None), ("2026-13-45", None)])
    def test_add_with_bad_dates_400_nothing_written(self, session_client, workspace, project, start, end):
        user = mk_user()
        m = {"member_id": str(user.id), "role": 15, "start_date": start, "end_date": end}
        assert add(session_client, workspace, project, [m]).status_code == 400
        assert not ProjectMember.objects.filter(project=project, member=user).exists()
        assert not WorkspaceMember.objects.filter(member=user).exists()  # provisioning rolled back too

    def test_patch_end_date_before_start_400(self, session_client, workspace, project):
        user = mk_user()
        m = {"member_id": str(user.id), "role": 15, "start_date": "2026-03-01"}
        assert add(session_client, workspace, project, [m]).status_code == 201
        pm = ProjectMember.objects.get(project=project, member=user)
        r = session_client.patch(url(workspace, project, pm.id), {"end_date": "2026-02-01"}, format="json")
        assert r.status_code == 400
        r = session_client.patch(url(workspace, project, pm.id), {"end_date": "2026-09-01"}, format="json")
        assert r.status_code == 200
        assert str(pm.allocation.end_date) == "2026-09-01" and str(pm.allocation.start_date) == "2026-03-01"

    @pytest.mark.parametrize("body", ["[]", "null", '"x"', "5"])
    def test_non_dict_body_400_not_500(self, session_client, workspace, project, body):
        r = session_client.generic("POST", url(workspace, project), body, content_type="application/json")
        assert r.status_code == 400 and r.json()["code"] == "USER_NOT_ELIGIBLE"

    def test_provisions_in_sorted_id_order(self, session_client, workspace, project):
        users = [mk_user() for _ in range(3)]
        seen = []
        import plane.ee.project_members.views as v

        real = v.provision_workspace_member

        def spy(ws, user, role):
            seen.append(str(user.id))
            return real(ws, user, role)

        ids = sorted(str(u.id) for u in users)
        with mock.patch.object(v, "provision_workspace_member", spy):
            r = add(session_client, workspace, project, [{"member_id": i, "role": 15} for i in reversed(ids)])
        assert r.status_code == 201
        assert seen == ids

    def test_bot_project_lead_gets_no_workspace_row(self, workspace):
        bot = mk_user("bot", is_bot=True)
        p = Project.objects.create(name="B", identifier="BOT", workspace=workspace, project_lead=bot)
        ProjectMember.objects.create(project=p, member=bot, workspace=workspace, role=20)
        assert not WorkspaceMember.objects.filter(workspace=workspace, member=bot).exists()

    def test_inactive_user_project_member_gets_no_workspace_row(self, workspace, project):
        u = mk_user("ina", is_active=False)
        ProjectMember.objects.create(project=project, member=u, workspace=workspace, role=15)
        assert not WorkspaceMember.objects.filter(workspace=workspace, member=u).exists()
