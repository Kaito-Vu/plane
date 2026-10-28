import pytest
from rest_framework import status

from plane.db.models import Issue, Project, ProjectMember
from plane.ee.work_item_types.constants import TypeKey as T
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    seed_project(project)
    return project


def _url(workspace, project, tail="issues/"):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/{tail}"


def _flat(r, code):
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert set(r.data) == {"error_code", "message", "details"} and r.data["error_code"] == code


@pytest.mark.contract
@pytest.mark.django_db
def test_v1_create_without_type_400(api_key_client, workspace, project):
    _flat(api_key_client.post(_url(workspace, project), {"name": "x"}, format="json"), "type_required")


@pytest.mark.contract
@pytest.mark.django_db
def test_v1_task_without_parent_400(api_key_client, workspace, project):
    body = {"name": "x", "type_id": str(get_type(workspace.id, T.TASK).id)}
    _flat(api_key_client.post(_url(workspace, project), body, format="json"), "parent_required")


@pytest.mark.contract
@pytest.mark.django_db
def test_v1_create_epic_then_patch_type_immutable(api_key_client, workspace, project):
    r = api_key_client.post(
        _url(workspace, project), {"name": "e", "type_id": str(get_type(workspace.id, T.EPIC).id)}, format="json"
    )
    assert r.status_code == status.HTTP_201_CREATED, r.data
    issue_id = r.data["id"]
    assert Issue.objects.get(pk=issue_id).type.external_id == "epic"
    r = api_key_client.patch(
        _url(workspace, project, f"issues/{issue_id}/"),
        {"type_id": str(get_type(workspace.id, T.TASK).id)},
        format="json",
    )
    _flat(r, "type_immutable")


@pytest.mark.contract
@pytest.mark.django_db
def test_v1_bulk_tree(api_key_client, workspace, project):
    items = [
        {"ref": "e", "type": "epic", "name": "E"},
        {"ref": "f", "type": "feature", "name": "F", "parent_ref": "e"},
    ]
    r = api_key_client.post(_url(workspace, project, "issues/bulk-tree/"), {"items": items}, format="json")
    assert r.status_code == status.HTTP_201_CREATED, r.data
    created = r.data["created"]
    assert str(Issue.objects.get(pk=created["f"]).parent_id) == created["e"]


@pytest.mark.contract
@pytest.mark.django_db
def test_v1_intake_defaults_to_bug_and_rejects_other_types(api_key_client, workspace, project):
    from plane.db.models import Intake

    project.intake_view = True
    project.save()
    Intake.objects.create(name="Intake", project=project, workspace=workspace, is_default=True)
    url = _url(workspace, project, "intake-issues/")
    r = api_key_client.post(url, {"issue": {"name": "crash"}}, format="json")
    assert r.status_code == status.HTTP_201_CREATED, r.data
    assert Issue.objects.get(name="crash").type.external_id == "bug"
    body = {"issue": {"name": "e", "type_id": str(get_type(workspace.id, T.EPIC).id)}}
    _flat(api_key_client.post(url, body, format="json"), "type_invalid")


@pytest.mark.contract
@pytest.mark.django_db
def test_v1_bulk_tree_non_member_forbidden(api_key_client, workspace, create_user):
    other = Project.objects.create(name="Q", identifier="Q", workspace=workspace, created_by=create_user)
    seed_project(other)
    items = [{"ref": "e", "type": "epic", "name": "E"}]
    r = api_key_client.post(_url(workspace, other, "issues/bulk-tree/"), {"items": items}, format="json")
    assert r.status_code == status.HTTP_403_FORBIDDEN
    assert not Issue.objects.filter(project=other).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_v1_bulk_tree_bad_refs_are_row_errors(api_key_client, workspace, project):
    epic = Issue.objects.create(name="E0", project=project, type=get_type(workspace.id, T.EPIC))
    items = [
        {"ref": "e", "type": "epic", "name": "E"},
        {"ref": "a", "type": ["epic"], "name": "A"},
        {"ref": "b", "type": "feature", "name": "B", "parent_ref": {"x": 1}},
        {"ref": "c", "type": "feature", "name": "C", "parent_ref": "e", "parent_id": str(epic.id)},
    ]
    r = api_key_client.post(_url(workspace, project, "issues/bulk-tree/"), {"items": items}, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert {(e["ref"], e["code"]) for e in r.data["errors"]} == {
        ("a", "type_invalid"),
        ("b", "parent_ref_invalid"),
        ("c", "ambiguous_parent"),
    }
