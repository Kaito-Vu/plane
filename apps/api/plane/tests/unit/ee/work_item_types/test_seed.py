import pytest
from django.core.management import call_command

from plane.db.models import IssueType, Project
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.constants import AGILE_SOURCE
from plane.ee.work_item_types.seed import seed_project, seed_workspace


def _agile_types(workspace):
    return IssueType.objects.filter(workspace=workspace, external_source=AGILE_SOURCE)


@pytest.mark.unit
@pytest.mark.django_db
def test_seed_workspace_idempotent(workspace):
    seed_workspace(workspace)
    seed_workspace(workspace)
    types = _agile_types(workspace)
    assert types.count() == 6
    assert set(types.values_list("name", flat=True)) == {"Epic", "Feature", "User Story", "Task", "Bug", "Sub-task"}
    assert list(types.filter(is_epic=True).values_list("external_id", flat=True)) == ["epic"]


@pytest.mark.unit
@pytest.mark.django_db
def test_seed_project_links_six_types(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    seed_project(project)
    seed_project(project)
    assert ProjectIssueType.objects.filter(project=project).count() == 6
    assert _agile_types(workspace).count() == 6


@pytest.mark.unit
@pytest.mark.django_db
def test_management_command_seeds_existing(workspace, create_user):
    project = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    call_command("seed_work_item_types", "--workspace", workspace.slug)
    call_command("seed_work_item_types")
    assert _agile_types(workspace).count() == 6
    assert ProjectIssueType.objects.filter(project=project).count() == 6
