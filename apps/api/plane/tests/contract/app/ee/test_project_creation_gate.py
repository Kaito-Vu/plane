import inspect
from uuid import uuid4

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from plane.db.models import User, WorkspaceMember
from plane.ee.project_members import permissions
from plane.ee.project_members.views import EeProjectViewSet


def client_as(workspace, role, v1=False):
    n = uuid4().hex[:8]
    user = User.objects.create(email=f"{n}@x.com", username=f"u_{n}")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    c = APIClient()
    if v1:
        from plane.db.models import APIToken

        c.credentials(HTTP_X_API_KEY=APIToken.objects.create(user=user, token=f"plane_api_{n}").token)
    else:
        c.force_authenticate(user=user)
    return c


def create(c, workspace, v1=False):
    n = uuid4().hex[:5].upper()
    prefix = "/api/v1" if v1 else "/api"
    return c.post(f"{prefix}/workspaces/{workspace.slug}/projects/", {"name": f"P{n}", "identifier": n}, format="json")


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectCreationGate:
    def test_ws_member_cannot_create_project_403(self, workspace):
        r = create(client_as(workspace, 15), workspace)
        assert r.status_code == 403
        assert r.json() == {"error": "Only workspace admins can create projects"}

    def test_guest_cannot_create_project(self, workspace):
        assert create(client_as(workspace, 5), workspace).status_code == 403

    def test_ws_admin_can_create_project(self, workspace):
        assert create(client_as(workspace, 20), workspace).status_code == 201

    def test_v1_ws_member_cannot_create_project(self, workspace):
        assert create(client_as(workspace, 15, v1=True), workspace, v1=True).status_code == 403

    def test_v1_ws_admin_can_create_project(self, workspace):
        assert create(client_as(workspace, 20, v1=True), workspace, v1=True).status_code == 201

    def test_list_route_still_works_for_member(self, workspace):
        assert client_as(workspace, 15).get(f"/api/workspaces/{workspace.slug}/projects/").status_code == 200

    def test_base_permission_signature_unchanged(self):
        assert str(inspect.signature(permissions._original_has_permission)) == "(self, request, view)"

    def test_route_resolves_to_ee_project_view(self, workspace):
        assert resolve(f"/api/workspaces/{workspace.slug}/projects/").func.cls is EeProjectViewSet
