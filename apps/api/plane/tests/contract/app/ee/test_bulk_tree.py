import pytest
from rest_framework import status

from plane.db.models import Issue, Project, ProjectMember
from plane.ee.models import Attribute
from plane.ee.work_item_types.constants import TypeKey as T
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    seed_project(project)
    return project


def _post(client, workspace, project, items, dry_run=False):
    url = f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/bulk-tree/"
    return client.post(url + ("?dry_run=true" if dry_run else ""), {"items": items}, format="json")


def _attr(project, type_key, system_key):
    return Attribute.objects.get(
        project=project, issue_type=get_type(project.workspace_id, type_key), system_key=system_key
    )


@pytest.fixture
def tree(project):
    """Children listed before parents on purpose: server must sort root -> leaf."""
    ac = _attr(project, T.USER_STORY, "acceptance_criteria")
    return [
        {"ref": "t", "type": "task", "name": "T", "parent_ref": "s"},
        {"ref": "s", "type": "user_story", "name": "S", "parent_ref": "f", "attribute_values": {str(ac.id): "Given"}},
        {"ref": "f", "type": "feature", "name": "F", "parent_ref": "e"},
        {"ref": "e", "type": "epic", "name": "E"},
    ]


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_tree_epic_to_task(session_client, workspace, project, tree):
    r = _post(session_client, workspace, project, tree)
    assert r.status_code == status.HTTP_201_CREATED, r.data
    assert r.data["errors"] == []
    c = r.data["created"]
    task = Issue.objects.get(pk=c["t"])
    assert str(task.parent_id) == c["s"] and str(task.parent.parent.parent_id) == c["e"]
    assert task.sequence_id and Issue.objects.filter(project=project).count() == 4


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_rolls_back_on_one_bad_row(session_client, workspace, project, tree):
    items = tree + [{"ref": "bad", "type": "task", "name": "orphan"}]
    r = _post(session_client, workspace, project, items)
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert r.data["created"] == {}
    assert [(e["ref"], e["code"]) for e in r.data["errors"]] == [("bad", "parent_required")]
    assert not Issue.objects.filter(project=project).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_cycle_in_refs_rejected(session_client, workspace, project):
    items = [
        {"ref": "a", "type": "feature", "name": "A", "parent_ref": "b"},
        {"ref": "b", "type": "feature", "name": "B", "parent_ref": "a"},
    ]
    r = _post(session_client, workspace, project, items)
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert {(e["ref"], e["code"]) for e in r.data["errors"]} == {("a", "parent_ref_cycle"), ("b", "parent_ref_cycle")}
    assert not Issue.objects.filter(project=project).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_unknown_parent_ref(session_client, workspace, project):
    r = _post(session_client, workspace, project, [{"ref": "f", "type": "feature", "name": "F", "parent_ref": "x"}])
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert [(e["ref"], e["code"]) for e in r.data["errors"]] == [("f", "parent_ref_unknown")]


@pytest.mark.contract
@pytest.mark.django_db
def test_dry_run_creates_nothing_but_reports_errors(session_client, workspace, project, tree):
    r = _post(session_client, workspace, project, tree, dry_run=True)
    assert r.status_code == status.HTTP_200_OK, r.data
    assert set(r.data["created"]) == {"e", "f", "s", "t"} and r.data["errors"] == []
    r = _post(session_client, workspace, project, tree + [{"ref": "bad", "type": "nope", "name": "x"}], dry_run=True)
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert [(e["ref"], e["code"]) for e in r.data["errors"]] == [("bad", "type_invalid")]
    assert not Issue.objects.filter(project=project).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_missing_required_attribute_reports_row_ref(session_client, workspace, project, tree):
    steps = _attr(project, T.BUG, "steps_to_reproduce")
    items = tree + [
        {"ref": "bug", "type": "bug", "name": "B", "parent_ref": "s", "attribute_values": {str(steps.id): "1"}}
    ]
    r = _post(session_client, workspace, project, items)
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert [(e["ref"], e["code"]) for e in r.data["errors"]] == [("bug", "attribute_required")]
    assert not Issue.objects.filter(project=project).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_bulk_existing_parent_id_ok_and_non_member_forbidden(session_client, workspace, project, create_user, tree):
    epic = Issue.objects.create(name="E", project=project, type=get_type(workspace.id, T.EPIC))
    r = _post(
        session_client, workspace, project, [{"ref": "f", "type": "feature", "name": "F", "parent_id": str(epic.id)}]
    )
    assert r.status_code == status.HTTP_201_CREATED, r.data
    other = Project.objects.create(name="Q", identifier="Q", workspace=workspace, created_by=create_user)
    seed_project(other)
    r = _post(session_client, workspace, other, tree)
    assert r.status_code == status.HTTP_403_FORBIDDEN
