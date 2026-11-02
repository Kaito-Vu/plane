import pytest
from rest_framework.test import APIClient

from plane.db.models import Project
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.seed import seed_project
from plane.tests.factories import ProjectMemberFactory, UserFactory, WorkspaceMemberFactory

ORDER = [k.value for k in TypeKey]


def _url(ws, p):
    return f"/api/workspaces/{ws.slug}/projects/{p.id}/work-item-types/"


def _client(workspace, project, role):
    u = UserFactory()
    WorkspaceMemberFactory(workspace=workspace, member=u, role=role)
    if project is not None:
        ProjectMemberFactory(project=project, member=u, workspace=workspace, role=role)
    c = APIClient()
    c.force_authenticate(user=u)
    return c


@pytest.fixture
def project(workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMemberFactory(project=p, member=create_user, workspace=workspace, role=20)
    seed_project(p)
    return p


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkItemTypesList:
    def test_lists_six_in_order_with_shape(self, session_client, workspace, project):
        r = session_client.get(_url(workspace, project))
        assert r.status_code == 200
        assert [t["key"] for t in r.data] == ORDER
        assert all(set(t) == {"id", "key", "name", "level", "is_epic"} for t in r.data)
        assert [t["is_epic"] for t in r.data] == [True] + [False] * 5

    def test_guest_can_read(self, workspace, project):
        assert _client(workspace, project, 5).get(_url(workspace, project)).status_code == 200

    def test_non_member_forbidden(self, workspace, project):
        assert _client(workspace, None, 15).get(_url(workspace, project)).status_code in (403, 404)

    def test_other_project_types_not_shown(self, session_client, workspace, project, create_user):
        other = Project.objects.create(name="O", identifier="O", workspace=workspace, created_by=create_user)
        ProjectMemberFactory(project=other, member=create_user, workspace=workspace, role=20)
        seed_project(other)
        from plane.db.models.issue_type import ProjectIssueType

        ProjectIssueType.objects.filter(project=other, issue_type__external_id="bug").delete()
        r = session_client.get(_url(workspace, other))
        assert [t["key"] for t in r.data] == [k for k in ORDER if k != "bug"]
        assert len(session_client.get(_url(workspace, project)).data) == 6
