import pathlib
import re

import pytest
from rest_framework import status

import plane
from plane.db.models import Issue, Project, ProjectMember
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.exceptions import WorkItemValidationError
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project

T = TypeKey


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    seed_project(project)
    return project


@pytest.fixture
def story(workspace, project):
    epic = Issue.objects.create(name="E", project=project, type=get_type(workspace.id, T.EPIC))
    feature = Issue.objects.create(name="F", project=project, type=get_type(workspace.id, T.FEATURE), parent=epic)
    return Issue.objects.create(name="S", project=project, type=get_type(workspace.id, T.USER_STORY), parent=feature)


def _post(client, workspace, project, data):
    return client.post(f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/", data, format="json")


@pytest.mark.contract
@pytest.mark.django_db
def test_create_without_type_rejected(session_client, workspace, project):
    r = _post(session_client, workspace, project, {"name": "x"})
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert set(r.data) == {"error_code", "message", "details"} and r.data["error_code"] == "type_required"


@pytest.mark.contract
@pytest.mark.django_db
def test_task_without_parent_rejected(session_client, workspace, project):
    r = _post(session_client, workspace, project, {"name": "x", "type_id": str(get_type(workspace.id, T.TASK).id)})
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert set(r.data) == {"error_code", "message", "details"} and r.data["error_code"] == "parent_required"


@pytest.mark.contract
@pytest.mark.django_db
def test_task_under_story_created(session_client, workspace, project, story):
    r = _post(
        session_client,
        workspace,
        project,
        {"name": "x", "type_id": str(get_type(workspace.id, T.TASK).id), "parent_id": str(story.id)},
    )
    assert r.status_code == status.HTTP_201_CREATED, r.data
    assert Issue.objects.get(pk=r.data["id"]).type.external_id == "task"


@pytest.mark.contract
@pytest.mark.django_db
def test_patch_cannot_change_type(session_client, workspace, project, story):
    r = session_client.patch(
        f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{story.id}/",
        {"type_id": str(get_type(workspace.id, T.TASK).id)},
        format="json",
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST
    assert set(r.data) == {"error_code", "message", "details"} and r.data["error_code"] == "type_immutable"


@pytest.mark.contract
@pytest.mark.django_db
def test_write_paths_cannot_bypass(workspace, project, story):
    with pytest.raises(WorkItemValidationError):
        Issue.objects.create(name="orphan", project=project, type=get_type(workspace.id, T.TASK))
    task = Issue.objects.create(name="t", project=project, type=get_type(workspace.id, T.TASK), parent=story)
    task.parent = None
    with pytest.raises(WorkItemValidationError):
        task.save()


@pytest.mark.contract
@pytest.mark.django_db
@pytest.mark.xfail(
    strict=True,
    reason="Known ceiling (spec §13.16): QuerySet.update/bulk_create/bulk_update bypass the pre_save signal",
)
def test_queryset_update_bypass_is_known_ceiling(workspace, project, story):
    task = Issue.objects.create(name="t", project=project, type=get_type(workspace.id, T.TASK), parent=story)
    with pytest.raises(WorkItemValidationError):
        Issue.objects.filter(pk=task.pk).update(parent=None)


# Core views writing Issue rows/parents via direct ORM without routing through validate_work_item.
# Each entry is a known gap owned by a later task; this set may only shrink.
PENDING_BYPASS = {
    "app/views/issue/sub_issue.py": "Task 7 (sub-issue bulk_update parent)",
    "api/views/intake.py": "Task 8 (public API intake)",
    "space/views/intake.py": "Task 7 (space intake)",
    "space/serializer/issue.py": "Task 7 (space issue create)",
    "api/serializers/issue.py": "Task 8 (public API create)",
    # dev-only dummy data generator; untyped issues are skipped by the signal anyway
    "bgtasks/dummy_data_task.py": "exempt (dev dummy data bulk_update parent)",
}
WRITE = re.compile(
    r"\bIssue\.objects\.(create|bulk_create)\(|\bIssue\.objects\.bulk_update\([^)]*parent|\.update\(parent"
)


@pytest.mark.contract
def test_core_issue_writers_call_validate_work_item():
    root = pathlib.Path(plane.__file__).parent
    assert "validate_issue_payload(" in (root / "app/serializers/issue.py").read_text(encoding="utf-8")
    offenders = set()
    for sub in (
        "app/views",
        "api/views",
        "space/views",
        "app/serializers",
        "api/serializers",
        "space/serializer",
        "bgtasks",
    ):
        for path in (root / sub).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if path.match("app/views/page/base.py"):  # `.update(parent=None)` there is Page.parent
                continue
            if WRITE.search(text) and "validate_work_item" not in text and "validate_issue_payload" not in text:
                offenders.add(path.relative_to(root).as_posix())
    assert offenders == set(PENDING_BYPASS)


@pytest.mark.contract
@pytest.mark.django_db
def test_signal_rejects_parent_from_other_project(workspace, create_user, project):
    other = Project.objects.create(name="Q", identifier="Q", workspace=workspace, created_by=create_user)
    seed_project(other)
    epic = Issue.objects.create(name="E", project=other, type=get_type(workspace.id, T.EPIC))
    with pytest.raises(WorkItemValidationError) as e:
        Issue.objects.create(name="F", project=project, type=get_type(workspace.id, T.FEATURE), parent=epic)
    assert e.value.error_code == "parent_invalid"
