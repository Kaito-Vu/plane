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

    def test_workspace_member_project_admin_lists_templates(self, workspace, project):
        c = _member_client(workspace, project, MEMBER, ADMIN)
        assert c.get(f"/api/workspaces/{workspace.slug}/attribute-templates/").status_code == status.HTTP_200_OK


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

    def test_apply_template_to_other_type_400(self, session_client, workspace, project, task_type):
        t = session_client.post(
            f"/api/workspaces/{workspace.slug}/attribute-templates/",
            {"issue_type": str(task_type.id), "name": "X", "field_type": "text"},
            format="json",
        ).data
        bug = get_type(workspace.id, TypeKey.BUG)
        r = session_client.post(
            _base(workspace, project) + "apply-template/",
            {"template_id": t["id"], "issue_type_id": str(bug.id)},
            format="json",
        )
        assert r.status_code == 400 and r.data["error_code"] == "template_type_mismatch"

    def test_apply_template_remaps_select_default(self, session_client, workspace, project, task_type):
        base = f"/api/workspaces/{workspace.slug}/attribute-templates/"
        t = session_client.post(
            base, {"issue_type": str(task_type.id), "name": "Sel2", "field_type": "select"}, format="json"
        ).data
        o = session_client.post(base + f"{t['id']}/options/", {"name": "A"}, format="json").data
        AttributeTemplate.objects.filter(pk=t["id"]).update(default_value=o["id"])
        r = session_client.post(
            _base(workspace, project) + "apply-template/",
            {"template_id": t["id"], "issue_type_id": str(task_type.id)},
            format="json",
        )
        assert r.status_code == 201, r.data
        copy = Attribute.objects.get(pk=r.data["id"])
        assert copy.default_value == str(copy.options.get().id) != o["id"]

    def test_system_attribute_locked(self, session_client, workspace, project, task_type):
        a = Attribute.objects.get(project=project, issue_type=task_type, system_key="acceptance_criteria")
        url = _base(workspace, project) + f"{a.id}/"
        for body in ({"name": "X"}, {"field_type": "text"}):
            r = session_client.patch(url, body, format="json")
            assert (
                r.status_code == 400
                and set(r.data) == {"error_code", "message", "details"}
                and r.data["error_code"] == "system_attribute_locked"
            )
        r = session_client.delete(url)
        assert (
            r.status_code == 400
            and set(r.data) == {"error_code", "message", "details"}
            and r.data["error_code"] == "system_attribute_locked"
        )
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
        assert (
            r.status_code == 400
            and set(r.data) == {"error_code", "message", "details"}
            and r.data["error_code"] == "type_change_blocked"
        )

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


def _tmpl_url(workspace, suffix=""):
    return f"/api/workspaces/{workspace.slug}/attribute-templates/{suffix}"


@pytest.mark.contract
@pytest.mark.django_db
class TestFixRound1:
    def _foreign(self, create_user):
        from plane.db.models import Workspace, WorkspaceMember

        ws = Workspace.objects.create(name="Other", owner=create_user, slug="other-ws")
        WorkspaceMember.objects.create(workspace=ws, member=create_user, role=ADMIN)
        p = Project.objects.create(name="Q", identifier="Q", workspace=ws, created_by=create_user)
        ProjectMemberFactory(project=p, member=create_user, workspace=ws, role=ADMIN)
        seed_project(p)
        return ws, p

    def test_cross_workspace_and_project_ids_404(self, session_client, workspace, project, task_type, create_user):
        ws2, p2 = self._foreign(create_user)
        foreign = Attribute.objects.filter(project=p2).first()
        r = session_client.patch(_base(workspace, project) + f"{foreign.id}/", {"is_required": True}, format="json")
        assert r.status_code == 404
        assert session_client.delete(_base(workspace, project) + f"{foreign.id}/").status_code == 404
        t = AttributeTemplate.objects.create(workspace=ws2, issue_type=foreign.issue_type, name="F", field_type="text")
        assert session_client.patch(_tmpl_url(workspace, f"{t.id}/"), {"name": "z"}, format="json").status_code == 404
        r = session_client.post(
            _base(workspace, project) + "apply-template/",
            {"template_id": str(t.id), "issue_type_id": str(task_type.id)},
            format="json",
        )
        assert r.status_code == 404

    def test_member_and_guest_forbidden(self, workspace, project, task_type):
        m = _member_client(workspace, project, MEMBER, MEMBER)
        assert m.get(_tmpl_url(workspace)).status_code == 403
        assert m.post(_tmpl_url(workspace), {}, format="json").status_code == 403
        g = _member_client(workspace, project, 5, 5)
        assert _create(g, workspace, project, task_type).status_code == 403

    def test_system_option_locked_except_phase(self, session_client, workspace, project):
        sev = Attribute.objects.filter(project=project, system_key="severity").first()
        opt = sev.options.first()
        url = _base(workspace, project) + f"{sev.id}/options/"
        assert session_client.delete(url + f"{opt.id}/").status_code == 400
        assert session_client.post(url, {"name": "X"}, format="json").status_code == 400
        assert session_client.patch(url + f"{opt.id}/", {"name": "X"}, format="json").status_code == 400
        ph = Attribute.objects.filter(project=project, system_key="project_phase").first()
        o = ph.options.first()
        r = session_client.delete(_base(workspace, project) + f"{ph.id}/options/{o.id}/")
        assert r.status_code == 204
        o.refresh_from_db()
        assert o.is_active is False

    def test_reorder_foreign_ids_400(self, session_client, workspace, project, create_user):
        _, p2 = self._foreign(create_user)
        foreign = Attribute.objects.filter(project=p2).first()
        r = session_client.post(_base(workspace, project) + "reorder/", {"ids": [str(foreign.id)]}, format="json")
        assert (
            r.status_code == 400
            and set(r.data) == {"error_code", "message", "details"}
            and r.data["error_code"] == "invalid_reorder_ids"
        )

    def test_duplicate_name_400(self, session_client, workspace, project, task_type):
        assert _create(session_client, workspace, project, task_type).status_code == 201
        r = _create(session_client, workspace, project, task_type)
        assert (
            r.status_code == 400
            and set(r.data) == {"error_code", "message", "details"}
            and r.data["error_code"] == "duplicate_name"
        )

    def test_system_description_patch_400(self, session_client, workspace, project, task_type):
        a = Attribute.objects.get(project=project, issue_type=task_type, system_key="acceptance_criteria")
        url = _base(workspace, project) + f"{a.id}/"
        r = session_client.patch(url, {"description": "x"}, format="json")
        assert (
            r.status_code == 400
            and set(r.data) == {"error_code", "message", "details"}
            and r.data["error_code"] == "system_attribute_locked"
        )
        same = {"name": a.name, "issue_type": str(task_type.id), "is_required": True}
        assert session_client.patch(url, same, format="json").status_code == 200

    def test_issue_type_not_in_project(self, session_client, workspace, project, create_user):
        from plane.db.models import IssueType
        from plane.db.models.issue_type import ProjectIssueType

        it = IssueType.objects.create(workspace=workspace, name="Loose")
        r = session_client.post(
            _base(workspace, project), {"issue_type": str(it.id), "name": "A", "field_type": "text"}, format="json"
        )
        assert (
            r.status_code == 400
            and set(r.data) == {"error_code", "message", "details"}
            and r.data["error_code"] == "issue_type_not_in_project"
        )
        assert not ProjectIssueType.objects.filter(project=project, issue_type=it).exists()

    def test_options_only_for_select_and_template_option_ops(self, session_client, workspace, project, task_type):
        t = session_client.post(
            _tmpl_url(workspace), {"issue_type": str(task_type.id), "name": "T", "field_type": "text"}, format="json"
        ).data
        assert (
            session_client.post(_tmpl_url(workspace, f"{t['id']}/options/"), {"name": "a"}, format="json").status_code
            == 400
        )
        t2 = session_client.post(
            _tmpl_url(workspace), {"issue_type": str(task_type.id), "name": "S", "field_type": "select"}, format="json"
        ).data
        o = session_client.post(_tmpl_url(workspace, f"{t2['id']}/options/"), {"name": "a"}, format="json").data
        ou = _tmpl_url(workspace, f"{t2['id']}/options/{o['id']}/")
        assert session_client.patch(ou, {"name": "b"}, format="json").data["name"] == "b"
        assert session_client.delete(ou).status_code == 204
        r = session_client.post(_tmpl_url(workspace, "reorder/"), {"ids": [t["id"], t2["id"]]}, format="json")
        assert r.status_code == 204
        assert AttributeTemplate.objects.get(pk=t2["id"]).sort_order == 20000
