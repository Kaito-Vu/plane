import pytest
from rest_framework import status

from plane.db.models import Issue, Project, ProjectMember
from plane.ee.models import Attribute, ImportBatch, ImportRow
from plane.ee.work_item_types.constants import TypeKey as T
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    seed_project(project)
    return project


def _url(workspace, project, suffix=""):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/imports/{suffix}"


def _batch(client, workspace, project, rows=None):
    r = client.post(_url(workspace, project), {}, format="json")
    assert r.status_code == status.HTTP_201_CREATED, r.data
    bid = r.data["id"]
    if rows is not None:
        r = client.post(_url(workspace, project, f"{bid}/rows/"), {"rows": rows}, format="json")
        assert r.status_code == status.HTTP_201_CREATED, r.data
    return bid


GOOD = [
    {"ref": "e", "type": "epic", "name": "E"},
    {"ref": "f", "type": "feature", "name": "F", "parent_ref": "e"},
]


@pytest.mark.contract
@pytest.mark.django_db
def test_staging_rows_are_not_issues(session_client, workspace, project):
    _batch(session_client, workspace, project, GOOD)
    assert ImportRow.objects.count() == 2
    assert not Issue.objects.filter(project=project).exists()
    r = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/")
    assert r.status_code == status.HTTP_200_OK
    assert "E" not in str(r.data)


@pytest.mark.contract
@pytest.mark.django_db
def test_validate_reports_missing_parent_and_wrong_parent_type_per_row(session_client, workspace, project):
    rows = [
        {"ref": "e", "type": "epic", "name": "E"},
        {"ref": "t1", "type": "task", "name": "no parent"},
        {"ref": "t2", "type": "task", "name": "under epic", "parent_ref": "e"},
    ]
    bid = _batch(session_client, workspace, project, rows)
    r = session_client.post(_url(workspace, project, f"{bid}/validate/"))
    assert r.status_code == status.HTTP_200_OK
    assert r.data["valid"] is False
    by_ref = {e["ref"]: e["code"] for e in r.data["errors"]}
    assert by_ref["t1"] == "parent_required"
    assert "t2" in by_ref and "e" not in by_ref
    assert {row.ref: bool(row.errors) for row in ImportRow.objects.filter(batch_id=bid)} == {
        "e": False,
        "t1": True,
        "t2": True,
    }
    assert not Issue.objects.filter(project=project).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_assign_parent_then_commit_creates_tree_atomically(session_client, workspace, project):
    ac = Attribute.objects.get(
        project=project, issue_type=get_type(project.workspace_id, T.USER_STORY), system_key="acceptance_criteria"
    )
    story_row = {"ref": "s", "type": "user_story", "name": "S", "attribute_values": {str(ac.id): "Given"}}
    rows = GOOD + [story_row]
    bid = _batch(session_client, workspace, project, rows)
    story = ImportRow.objects.get(batch_id=bid, ref="s")
    r = session_client.patch(_url(workspace, project, f"{bid}/rows/{story.id}/"), {"parent_ref": "f"}, format="json")
    assert r.status_code == status.HTTP_200_OK, r.data
    r = session_client.post(_url(workspace, project, f"{bid}/commit/"))
    assert r.status_code == status.HTTP_201_CREATED, r.data
    created = r.data["created"]
    assert Issue.objects.filter(project=project).count() == 3
    assert str(Issue.objects.get(pk=created["s"]).parent_id) == created["f"]
    assert str(Issue.objects.get(pk=created["f"]).parent_id) == created["e"]


@pytest.mark.contract
@pytest.mark.django_db
def test_commit_blocked_while_any_row_invalid(session_client, workspace, project):
    bid = _batch(session_client, workspace, project, GOOD + [{"ref": "s", "type": "user_story", "name": "S"}])
    r = session_client.post(_url(workspace, project, f"{bid}/commit/"))
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert r.data["error_code"] == "batch_invalid"
    assert {e["ref"] for e in r.data["details"]["errors"]} == {"s"}
    assert not Issue.objects.filter(project=project).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_commit_twice_rejected(session_client, workspace, project):
    bid = _batch(session_client, workspace, project, GOOD)
    assert session_client.post(_url(workspace, project, f"{bid}/commit/")).status_code == 201
    r = session_client.post(_url(workspace, project, f"{bid}/commit/"))
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert r.data["error_code"] == "batch_already_committed"
    assert Issue.objects.filter(project=project).count() == 2


@pytest.mark.contract
@pytest.mark.django_db
def test_row_cap(session_client, workspace, project):
    bid = _batch(session_client, workspace, project)
    rows = [{"ref": str(i), "type": "epic", "name": "x"} for i in range(1001)]
    r = session_client.post(_url(workspace, project, f"{bid}/rows/"), {"rows": rows}, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert r.data["error_code"] == "too_many_rows"


@pytest.mark.contract
@pytest.mark.django_db
def test_other_project_ids_are_404_and_non_member_403(session_client, workspace, project, create_user):
    bid = _batch(session_client, workspace, project, GOOD)
    row = ImportRow.objects.filter(batch_id=bid).first()
    other = Project.objects.create(name="Q", identifier="Q", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=other, member=create_user, workspace=workspace, role=20)
    seed_project(other)
    for method, suffix in [
        ("post", f"{bid}/rows/"),
        ("post", f"{bid}/validate/"),
        ("post", f"{bid}/commit/"),
        ("patch", f"{bid}/rows/{row.id}/"),
    ]:
        r = getattr(session_client, method)(_url(workspace, other, suffix), {"rows": GOOD}, format="json")
        assert r.status_code == status.HTTP_404_NOT_FOUND, (method, suffix)
    # row id of another batch in the same project -> 404 too
    bid2 = _batch(session_client, workspace, project, GOOD)
    r = session_client.patch(_url(workspace, project, f"{bid2}/rows/{row.id}/"), {"name": "x"}, format="json")
    assert r.status_code == status.HTTP_404_NOT_FOUND
    outsider = Project.objects.create(name="R", identifier="R", workspace=workspace, created_by=create_user)
    assert session_client.post(_url(workspace, outsider), {}, format="json").status_code == 403


@pytest.mark.contract
@pytest.mark.django_db
def test_guest_cannot_import(session_client, workspace, project, create_user):
    ProjectMember.objects.filter(project=project, member=create_user).update(role=5)
    assert session_client.post(_url(workspace, project), {}, format="json").status_code == 403


@pytest.mark.contract
@pytest.mark.django_db
def test_wrong_parent_type_code(session_client, workspace, project):
    rows = [{"ref": "e", "type": "epic", "name": "E"}, {"ref": "t", "type": "task", "name": "T", "parent_ref": "e"}]
    bid = _batch(session_client, workspace, project, rows)
    r = session_client.post(_url(workspace, project, f"{bid}/validate/"))
    assert [(e["ref"], e["code"]) for e in r.data["errors"]] == [("t", "parent_type_invalid")]


@pytest.mark.contract
@pytest.mark.django_db
def test_parent_id_of_other_project_rejected(session_client, workspace, project, create_user):
    other = Project.objects.create(name="Q", identifier="Q", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=other, member=create_user, workspace=workspace, role=20)
    seed_project(other)
    bid = _batch(session_client, workspace, other, [{"ref": "e", "type": "epic", "name": "E"}])
    session_client.post(_url(workspace, other, f"{bid}/commit/"))
    foreign = Issue.objects.get(project=other)
    rows = [{"ref": "f", "type": "feature", "name": "F", "parent_id": str(foreign.id)}]
    bid = _batch(session_client, workspace, project, rows)
    r = session_client.post(_url(workspace, project, f"{bid}/commit/"))
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert not Issue.objects.filter(project=project).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_committed_batch_rejects_edits(session_client, workspace, project):
    bid = _batch(session_client, workspace, project, GOOD)
    session_client.post(_url(workspace, project, f"{bid}/commit/"))
    row = ImportRow.objects.filter(batch_id=bid).first()
    r = session_client.patch(_url(workspace, project, f"{bid}/rows/{row.id}/"), {"name": "x"}, format="json")
    assert (r.status_code, r.data["error_code"]) == (400, "batch_already_committed")
    r = session_client.post(_url(workspace, project, f"{bid}/rows/"), {"rows": GOOD}, format="json")
    assert (r.status_code, r.data["error_code"]) == (400, "batch_already_committed")


@pytest.mark.contract
@pytest.mark.django_db
def test_failed_batch_can_be_edited_and_retried(session_client, workspace, project, monkeypatch):
    from plane.ee.work_item_types import importer

    real = importer.apply_bulk_tree
    calls = []

    def flaky(project, items, *, dry_run, actor):
        if dry_run:
            return real(project, items, dry_run=True, actor=actor)
        calls.append(1)
        return {"created": {}, "errors": [{"ref": "e", "code": "boom", "message": "boom"}]}

    monkeypatch.setattr(importer, "apply_bulk_tree", flaky)
    bid = _batch(session_client, workspace, project, GOOD)
    r = session_client.post(_url(workspace, project, f"{bid}/commit/"))
    assert (r.status_code, r.data["error_code"]) == (400, "commit_failed")
    assert ImportBatch.objects.get(pk=bid).status == "failed"
    row = ImportRow.objects.filter(batch_id=bid).first()
    r = session_client.patch(_url(workspace, project, f"{bid}/rows/{row.id}/"), {"name": "E2"}, format="json")
    assert r.status_code == 200
    assert (
        session_client.post(
            _url(workspace, project, f"{bid}/rows/"), {"rows": [{"ref": "x"}]}, format="json"
        ).status_code
        == 201
    )
    monkeypatch.setattr(importer, "apply_bulk_tree", real)
    ImportRow.objects.filter(batch_id=bid, ref="x").delete()
    assert session_client.post(_url(workspace, project, f"{bid}/commit/")).status_code == 201
    assert ImportBatch.objects.get(pk=bid).status == "committed"


@pytest.mark.contract
@pytest.mark.django_db
def test_bad_row_input_is_400_not_500(session_client, workspace, project):
    bid = _batch(session_client, workspace, project, GOOD)
    url = _url(workspace, project, f"{bid}/rows/")
    for bad in (["str"], [{"name": "x" * 300}], [{"ref": 5}], [{"parent_id": "nope"}], [{"type": ["a"]}]):
        r = session_client.post(url, {"rows": bad}, format="json")
        assert r.status_code == 400 and r.data["error_code"] == "invalid_rows", bad
    row = ImportRow.objects.filter(batch_id=bid).first()
    r = session_client.patch(url + f"{row.id}/", {"parent_id": "nope"}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
@pytest.mark.django_db
def test_patch_parent_ref_clears_parent_id_and_empty_validate(session_client, workspace, project):
    empty = _batch(session_client, workspace, project)
    r = session_client.post(_url(workspace, project, f"{empty}/validate/"))
    assert (r.status_code, r.data["error_code"]) == (400, "empty_batch")
    bid = _batch(session_client, workspace, project, GOOD)
    f = ImportRow.objects.get(batch_id=bid, ref="f")
    u = str(f.id)  # any uuid
    url = _url(workspace, project, f"{bid}/rows/{f.id}/")
    session_client.patch(url, {"parent_id": u}, format="json")
    f.refresh_from_db()
    assert f.parent_ref is None and str(f.parent_id) == u
    session_client.patch(url, {"parent_ref": "e", "data": {"x": 1}}, format="json")
    f.refresh_from_db()
    assert f.parent_ref == "e" and f.parent_id is None and "data" not in f.data


@pytest.mark.contract
@pytest.mark.django_db
def test_member_role_15_allowed(session_client, workspace, project, create_user):
    ProjectMember.objects.filter(project=project, member=create_user).update(role=15)
    assert session_client.post(_url(workspace, project), {}, format="json").status_code == 201
