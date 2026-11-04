from uuid import uuid4

import pytest
from django.urls import resolve
from rest_framework import status

from plane.db.models import Project, ProjectMember, User, WorkspaceMember
from plane.ee.project_members.views import EeProjectMemberListCreateAPIEndpoint


def members_url(slug, project_id):
    return f"/api/v1/workspaces/{slug}/projects/{project_id}/members/"


def make_user(prefix="u"):
    uid = uuid4().hex[:8]
    return User.objects.create(email=f"{prefix}-{uid}@plane.so", username=f"{prefix}_{uid}")


@pytest.fixture
def project(db, workspace, create_user):
    p = Project.objects.create(name="P", identifier="PFM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=p, member=create_user, workspace=workspace, role=20)
    return p


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectMembersV1:
    def test_v1_route_resolves_to_ee_view(self, workspace, project):
        match = resolve(members_url(workspace.slug, project.id))
        assert match.func.view_class is EeProjectMemberListCreateAPIEndpoint

    def test_v1_add_unknown_user_400_user_not_eligible(self, api_key_client, workspace, project):
        r = api_key_client.post(
            members_url(workspace.slug, project.id), {"member": str(uuid4()), "role": 15}, format="json"
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert r.data["code"] == "USER_NOT_ELIGIBLE"

    def test_v1_add_existing_user_provisions_ws_member(self, api_key_client, workspace, project):
        target = make_user()
        assert not WorkspaceMember.objects.filter(workspace=workspace, member=target).exists()
        r = api_key_client.post(
            members_url(workspace.slug, project.id), {"member": str(target.id), "role": 15}, format="json"
        )
        assert r.status_code == status.HTTP_201_CREATED, r.data
        assert WorkspaceMember.objects.get(workspace=workspace, member=target).role == 15
        assert ProjectMember.objects.filter(project=project, member=target, role=15).exists()

    def test_v1_non_admin_403_no_rows_written(self, api_key_client, workspace, project, create_user):
        # workspace admins pass core's ProjectAdminPermission; demote both rows
        ProjectMember.objects.filter(project=project, member=create_user).update(role=15)
        WorkspaceMember.objects.filter(workspace=workspace, member=create_user).update(role=15)
        target = make_user()
        r = api_key_client.post(
            members_url(workspace.slug, project.id), {"member": str(target.id), "role": 15}, format="json"
        )
        assert r.status_code == status.HTTP_403_FORBIDDEN
        assert not WorkspaceMember.objects.filter(workspace=workspace, member=target).exists()
        assert not ProjectMember.objects.filter(project=project, member=target).exists()

    @pytest.mark.parametrize("bad", ["not-a-uuid", 123, None, ["x"], {"a": 1}])
    def test_v1_malformed_user_id_400_not_500(self, api_key_client, workspace, project, bad):
        r = api_key_client.post(members_url(workspace.slug, project.id), {"member": bad, "role": 15}, format="json")
        assert r.status_code == status.HTTP_400_BAD_REQUEST
        assert r.data["code"] == "USER_NOT_ELIGIBLE"

    def test_v1_list_still_works(self, api_key_client, workspace, project, create_user):
        r = api_key_client.get(members_url(workspace.slug, project.id))
        assert r.status_code == status.HTTP_200_OK
        assert str(create_user.id) in {str(row["id"]) for row in r.data}
