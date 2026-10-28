import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Project
from plane.ee.models import Attribute, AttributeTemplate, AttributeValue
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project
from plane.tests.factories import ProjectMemberFactory, UserFactory, WorkspaceMemberFactory

ADMIN, MEMBER = 20, 15


@pytest.fixture
def project(workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMemberFactory(project=p, member=create_user, workspace=workspace, role=ADMIN)
    seed_project(p)
    return p


@pytest.fixture
def task_type(workspace, project):
    return get_type(workspace.id, TypeKey.TASK)


def _member_client(workspace, project, ws_role, project_role):
    user = UserFactory()
    WorkspaceMemberFactory(workspace=workspace, member=user, role=ws_role)
    ProjectMemberFactory(project=project, member=user, workspace=workspace, role=project_role)
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def _base(workspace, project):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/attributes/"


def _create(client, workspace, project, task_type, **kw):
    data = {"issue_type": str(task_type.id), "name": "Custom", "field_type": "text", **kw}
    return client.post(_base(workspace, project), data, format="json")


@pytest.mark.contract
@pytest.mark.django_db
class TestPermissions:
    def test_member_cannot_create_attribute(self, workspace, project, task_type):
        c = _member_client(workspace, project, MEMBER, MEMBER)
        assert _create(c, workspace, project, task_type).status_code == status.HTTP_403_FORBIDDEN

    def test_member_can_read(self, workspace, project, task_type):
        c = _member_client(workspace, project, MEMBER, MEMBER)
        r = c.get(_base(workspace, project) + f"?issue_type_id={task_type.id}")
        assert r.status_code == 200 and r.data

    def test_project_admin_creates_attribute(self, session_client, workspace, project, task_type):
        r = _create(session_client, workspace, project, task_type)
        assert r.status_code == status.HTTP_201_CREATED, r.data
        assert r.data["is_system"] is False

    def test_only_workspace_admin_creates_template(self, session_client, workspace, project, task_type):
        url = f"/api/workspaces/{workspace.slug}/attribute-templates/"
        body = {"issue_type": str(task_type.id), "name": "T", "field_type": "text"}
        c = _member_client(workspace, project, MEMBER, ADMIN)
        assert c.post(url, body, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert session_client.post(url, body, format="json").status_code == status.HTTP_201_CREATED


@pytest.mark.contract
@pytest.mark.django_db
class TestBehavior:
    def test_apply_template_copies_independently(self, session_client, workspace, project, task_type):
        t = session_client.post(
            f"/api/workspaces/{workspace.slug}/attribute-templates/",
            {"issue_type": str(task_type.id), "name": "Sel", "field_type": "select"},
            format="json",
        ).data
        o = session_client.post(
            f"/api/workspaces/{workspace.slug}/attribute-templates/{t['id']}/options/", {"name": "A"}, format="json"
        )
        assert o.status_code == 201
        r = session_client.post(
            _base(workspace, project) + "apply-template/",
            {"template_id": t["id"], "issue_type_id": str(task_type.id)},
            format="json",
        )
        assert r.status_code == 201, r.data
        assert [x["name"] for x in r.data["options"]] == ["A"]
        session_client.patch(
            f"/api/workspaces/{workspace.slug}/attribute-templates/{t['id']}/",
            {"name": "Renamed", "is_required": True},
            format="json",
        )
        session_client.post(
            f"/api/workspaces/{workspace.slug}/attribute-templates/{t['id']}/options/", {"name": "B"}, format="json"
        )
        copy = Attribute.objects.get(pk=r.data["id"])
        assert (copy.name, copy.is_required, copy.options.count()) == ("Sel", False, 1)
        assert copy.source_template_id == AttributeTemplate.objects.get(pk=t["id"]).id

    def test_system_attribute_locked(self, session_client, workspace, project, task_type):
        a = Attribute.objects.get(project=project, issue_type=task_type, system_key="acceptance_criteria")
        url = _base(workspace, project) + f"{a.id}/"
        for body in ({"name": "X"}, {"field_type": "text"}):
            r = session_client.patch(url, body, format="json")
            assert r.status_code == 400 and r.data["error_code"] == "system_attribute_locked"
        r = session_client.delete(url)
        assert r.status_code == 400 and r.data["error_code"] == "system_attribute_locked"
        assert session_client.patch(url, {"is_required": True}, format="json").status_code == 200

    def test_project_phase_options_editable(self, session_client, workspace, project):
        a = Attribute.objects.filter(project=project, system_key="project_phase").first()
        r = session_client.post(_base(workspace, project) + f"{a.id}/options/", {"name": "Review"}, format="json")
        assert r.status_code == 201

    def test_type_change_blocked_when_values_exist(self, session_client, workspace, project, task_type, create_user):
        from plane.db.models import Issue

        a = Attribute.objects.get(pk=_create(session_client, workspace, project, task_type).data["id"])
        issue = Issue.objects.create(name="i", project=project, type=get_type(workspace.id, TypeKey.EPIC))
        AttributeValue.objects.create(attribute=a, issue=issue, project=project, workspace=workspace, value_text="x")
        r = session_client.patch(_base(workspace, project) + f"{a.id}/", {"field_type": "number"}, format="json")
        assert r.status_code == 400 and r.data["error_code"] == "type_change_blocked"

    def test_soft_delete_keeps_values(self, session_client, workspace, project, task_type):
        from plane.db.models import Issue

        a = Attribute.objects.get(pk=_create(session_client, workspace, project, task_type).data["id"])
        issue = Issue.objects.create(name="i", project=project, type=get_type(workspace.id, TypeKey.EPIC))
        AttributeValue.objects.create(attribute=a, issue=issue, project=project, workspace=workspace, value_text="x")
        assert session_client.delete(_base(workspace, project) + f"{a.id}/").status_code == 204
        a = Attribute.all_objects.get(pk=a.pk)
        assert a.deleted_at is not None
        assert AttributeValue.all_objects.filter(attribute=a).exists()
        assert not any(x["id"] == str(a.id) for x in session_client.get(_base(workspace, project)).data)

    def test_reorder(self, session_client, workspace, project, task_type):
        ids = [str(a.id) for a in Attribute.objects.filter(project=project, issue_type=task_type)][::-1]
        r = session_client.post(_base(workspace, project) + "reorder/", {"ids": ids}, format="json")
        assert r.status_code == 204
        got = [
            str(a.id) for a in Attribute.objects.filter(project=project, issue_type=task_type).order_by("sort_order")
        ]
        assert got == ids
