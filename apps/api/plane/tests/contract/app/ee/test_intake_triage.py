import pytest
from rest_framework import status

from plane.db.models import Intake, IntakeIssue, Issue
from plane.ee.models import Attribute
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.registry import get_type

T = TypeKey


@pytest.fixture
def intake(project, states):
    return Intake.objects.create(name="Intake", project=project, workspace=project.workspace, is_default=True)


def _url(workspace, project, suffix=""):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/intake-issues/{suffix}"


def _submit(client, workspace, project, key=T.BUG):
    r = client.post(
        _url(workspace, project),
        {"issue": {"name": "crash", "type_id": str(get_type(workspace.id, key).id)}},
        format="json",
    )
    return r


def _bug_values(project, workspace):
    def a(k):
        return str(Attribute.objects.get(project=project, issue_type=get_type(workspace.id, T.BUG), system_key=k).id)

    sev = Attribute.objects.get(project=project, issue_type=get_type(workspace.id, T.BUG), system_key="severity")
    return {a("severity"): str(sev.options.first().id), a("steps_to_reproduce"): "1.", a("actual_result"): "boom"}


@pytest.mark.contract
@pytest.mark.django_db
def test_intake_pending_bug_without_parent_or_severity_ok(session_client, workspace, project, intake):
    r = _submit(session_client, workspace, project)
    assert r.status_code == status.HTTP_200_OK, r.data
    assert IntakeIssue.objects.get(intake=intake).status == -2


@pytest.mark.contract
@pytest.mark.django_db
def test_intake_create_without_type_defaults_to_bug(session_client, workspace, project, intake):
    r = session_client.post(_url(workspace, project), {"issue": {"name": "no type"}}, format="json")
    assert r.status_code == status.HTTP_200_OK, r.data
    assert Issue.all_objects.get(pk=r.data["issue"]["id"]).type_id == get_type(workspace.id, T.BUG).id


@pytest.mark.contract
@pytest.mark.django_db
def test_intake_rejects_types_other_than_bug_or_story(session_client, workspace, project, intake):
    assert _submit(session_client, workspace, project, T.USER_STORY).status_code == status.HTTP_200_OK
    r = _submit(session_client, workspace, project, T.TASK)
    assert r.status_code == status.HTTP_400_BAD_REQUEST and "type_invalid" in str(r.data)


@pytest.mark.contract
@pytest.mark.django_db
def test_intake_accept_without_parent_400(session_client, workspace, project, intake, states):
    issue_id = _submit(session_client, workspace, project).data["issue"]["id"]
    r = session_client.patch(_url(workspace, project, f"{issue_id}/"), {"status": 1}, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert IntakeIssue.objects.get(issue_id=issue_id).status == -2
    # rejected accept keeps no issue edits (atomic)
    body = {"status": 1, "issue": {"name": "renamed"}}
    r = session_client.patch(_url(workspace, project, f"{issue_id}/"), body, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert Issue.all_objects.get(pk=issue_id).name == "crash"
    assert Issue.all_objects.get(pk=issue_id).state.group == "triage"


@pytest.mark.contract
@pytest.mark.django_db
def test_intake_reject_without_parent_ok(session_client, workspace, project, intake):
    issue_id = _submit(session_client, workspace, project).data["issue"]["id"]
    for st in (-1, 2):
        r = session_client.patch(_url(workspace, project, f"{issue_id}/"), {"status": st}, format="json")
        assert r.status_code == status.HTTP_200_OK, r.data


@pytest.mark.contract
@pytest.mark.django_db
def test_intake_accept_with_valid_parent_and_attributes_ok(session_client, workspace, project, intake, story, states):
    issue_id = _submit(session_client, workspace, project).data["issue"]["id"]
    # parent alone is not enough: Bug required attributes are checked on accept
    r = session_client.patch(
        _url(workspace, project, f"{issue_id}/"), {"issue": {"parent_id": str(story.id)}, "status": 1}, format="json"
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST and "attribute_required" in str(r.data)
    r = session_client.patch(
        _url(workspace, project, f"{issue_id}/"),
        {"issue": {"parent_id": str(story.id), "attribute_values": _bug_values(project, workspace)}, "status": 1},
        format="json",
    )
    assert r.status_code == status.HTTP_200_OK, r.data
    issue = Issue.objects.get(pk=issue_id)
    assert issue.parent_id == story.id and issue.state_id == states["todo"].id


@pytest.mark.contract
@pytest.mark.django_db
def test_intake_state_patch_cannot_leave_triage_without_accept(session_client, workspace, project, intake, states):
    """The core issue endpoint 404s for triage issues and the intake PATCH only takes triage states,
    so accept (status=1, full validation, see test_intake_accept_*) is the only way out of triage."""
    issue_id = _submit(session_client, workspace, project).data["issue"]["id"]
    r = session_client.patch(
        _url(workspace, project, f"{issue_id}/"), {"issue": {"state_id": str(states["todo"].id)}}, format="json"
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert Issue.all_objects.get(pk=issue_id).state.group == "triage"
