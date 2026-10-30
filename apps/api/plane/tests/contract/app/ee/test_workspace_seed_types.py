import pytest

from plane.bgtasks.workspace_seed_task import workspace_seed
from plane.db.models import CycleIssue, Issue


@pytest.mark.contract
@pytest.mark.django_db
def test_workspace_seed_keeps_epics_out_of_cycles(workspace):
    workspace_seed(workspace.id)
    assert Issue.objects.filter(workspace=workspace).exists()
    assert not CycleIssue.objects.filter(
        workspace=workspace, issue__type__external_id__in=["epic", "feature"]
    ).exists()
