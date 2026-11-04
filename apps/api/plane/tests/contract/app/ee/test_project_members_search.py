from uuid import uuid4

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember, User, WorkspaceMember


def mk_user(email, **kw):
    n = uuid4().hex[:8]
    return User.objects.create(email=email, username=f"u_{n}", **kw)


def search(client, workspace, project, q):
    return client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/members/search/", {"q": q})


@pytest.fixture(autouse=True)
def _clear_throttle(create_user):
    cache.delete(f"throttle_ee_member_search_{create_user.pk}")
    yield
    cache.delete(f"throttle_ee_member_search_{create_user.pk}")


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectMemberSearch:
    def test_short_query_400(self, session_client, workspace, project):
        assert search(session_client, workspace, project, "ab").status_code == 400
        assert search(session_client, workspace, project, " ab ").status_code == 400
        assert search(session_client, workspace, project, "").status_code == 400

    def test_non_admin_403(self, workspace, project):
        member = mk_user("mem@x.com")
        WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
        ProjectMember.objects.create(project=project, member=member, workspace=workspace, role=15)
        c = APIClient()
        c.force_authenticate(user=member)
        assert search(c, workspace, project, "alice").status_code == 403

    def test_other_project_admin_403(self, workspace, project):
        other = Project.objects.create(name="O", identifier="OTH", workspace=workspace)
        admin = mk_user("adm@x.com")
        WorkspaceMember.objects.create(workspace=workspace, member=admin, role=15)
        ProjectMember.objects.create(project=other, member=admin, workspace=workspace, role=20)
        c = APIClient()
        c.force_authenticate(user=admin)
        assert search(c, workspace, project, "alice").status_code == 403

    def test_returns_whitelisted_keys_only(self, session_client, workspace, project):
        mk_user("alice@x.com", display_name="alice")
        r = search(session_client, workspace, project, "alice")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert set(r.json()[0]) == {"id", "display_name", "avatar_url", "email"}

    def test_email_masked(self, session_client, workspace, project):
        mk_user("alice@x.com")
        assert search(session_client, workspace, project, "alice").json()[0]["email"] == "a***@x.com"

    def test_excludes_bot_inactive_and_existing_members(self, session_client, workspace, project):
        ok = mk_user("zzq-ok@x.com")
        mk_user("zzq-bot@x.com", is_bot=True)
        mk_user("zzq-off@x.com", is_active=False)
        active = mk_user("zzq-in@x.com")
        ProjectMember.objects.create(project=project, member=active, workspace=workspace, role=15)
        left = mk_user("zzq-left@x.com")
        ProjectMember.objects.create(project=project, member=left, workspace=workspace, role=15, is_active=False)
        ids = {i["id"] for i in search(session_client, workspace, project, "zzq-").json()}
        assert ids == {str(ok.id), str(left.id)}

    def test_cap_10(self, session_client, workspace, project):
        for i in range(12):
            mk_user(f"cap{i:02d}@x.com")
        assert len(search(session_client, workspace, project, "cap").json()) == 10

    def test_wildcards_are_literal(self, session_client, workspace, project):
        mk_user("alice@x.com")
        assert search(session_client, workspace, project, "%%%").json() == []
        assert search(session_client, workspace, project, "___").json() == []

    def test_case_insensitive_trimmed(self, session_client, workspace, project):
        u = mk_user("alice@x.com")
        r = search(session_client, workspace, project, "  ALICE@X.COM ")
        assert [i["id"] for i in r.json()] == [str(u.id)]

    def test_31st_call_429(self, session_client, workspace, project):
        for _ in range(30):
            assert search(session_client, workspace, project, "alice").status_code == 200
        assert search(session_client, workspace, project, "alice").status_code == 429
