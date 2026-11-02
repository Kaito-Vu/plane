import json
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.bgtasks.issue_activities_task import issue_activity
from plane.db.models import Issue, IssueActivity, Project, State
from plane.ee.models import Attribute, AttributeValue
from plane.ee.work_item_types.constants import TypeKey
from plane.ee.work_item_types.registry import get_type
from plane.ee.work_item_types.seed import seed_project
from plane.app.serializers import IssueCreateSerializer
from plane.tests.factories import (
    ProjectFactory,
    ProjectMemberFactory,
    UserFactory,
    WorkspaceFactory,
    WorkspaceMemberFactory,
)

T = TypeKey
ADMIN, GUEST = 20, 5


@pytest.fixture
def project(workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMemberFactory(project=p, member=create_user, workspace=workspace, role=ADMIN)
    seed_project(p)
    return p


@pytest.fixture
def feature(workspace, project):
    epic = Issue.objects.create(name="E", project=project, type=get_type(workspace.id, T.EPIC))
    return Issue.objects.create(name="F", project=project, type=get_type(workspace.id, T.FEATURE), parent=epic)


@pytest.fixture
def story(workspace, project, feature):
    return Issue.objects.create(name="S", project=project, type=get_type(workspace.id, T.USER_STORY), parent=feature)


def _attr(project, type_key, system_key):
    return Attribute.objects.get(
        project=project, issue_type=get_type(project.workspace_id, type_key), system_key=system_key
    )


def _issues(workspace, project):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"


def _assert_flat(r, code):
    assert set(r.data) == {"error_code", "message", "details"}, r.data
    assert r.data["error_code"] == code


def _values_url(workspace, project, issue):
    return f"{_issues(workspace, project)}{issue.id}/attribute-values/"


@pytest.mark.contract
@pytest.mark.django_db
def test_create_bug_missing_severity_400_lists_ids(session_client, workspace, project, story):
    steps = _attr(project, T.BUG, "steps_to_reproduce")
    body = {
        "name": "bug",
        "type_id": str(get_type(workspace.id, T.BUG).id),
        "parent_id": str(story.id),
        "attribute_values": {str(steps.id): "1. click"},
    }
    r = session_client.post(_issues(workspace, project), body, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert set(r.data) == {"error_code", "message", "details"} and r.data["error_code"] == "attribute_required"
    assert set(r.data["details"]["missing"]) == {
        str(_attr(project, T.BUG, "severity").id),
        str(_attr(project, T.BUG, "actual_result").id),
    }


@pytest.mark.contract
@pytest.mark.django_db
def test_create_story_with_values_persists_atomically(session_client, workspace, project, feature):
    ac = _attr(project, T.USER_STORY, "acceptance_criteria")
    sp = _attr(project, T.USER_STORY, "story_points")
    body = {"name": "s", "type_id": str(get_type(workspace.id, T.USER_STORY).id), "parent_id": str(feature.id)}
    before = Issue.objects.count()
    bad = {**body, "attribute_values": {str(ac.id): "Given", str(sp.id): "abc"}}
    r = session_client.post(_issues(workspace, project), bad, format="json")
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    _assert_flat(r, "invalid_value")
    assert Issue.objects.count() == before
    assert not AttributeValue.objects.exists()

    good = {**body, "attribute_values": {str(ac.id): "Given", str(sp.id): 5}}
    r = session_client.post(_issues(workspace, project), good, format="json")
    assert r.status_code == status.HTTP_201_CREATED, r.data
    issue = Issue.objects.get(pk=r.data["id"])
    got = session_client.get(_values_url(workspace, project, issue)).data
    assert got[str(ac.id)] == "Given"
    assert float(got[str(sp.id)]) == 5


@pytest.mark.contract
@pytest.mark.django_db
def test_patch_cannot_blank_required(session_client, workspace, project, story):
    ac = _attr(project, T.USER_STORY, "acceptance_criteria")
    r = session_client.patch(
        f"{_issues(workspace, project)}{story.id}/", {"attribute_values": {str(ac.id): ""}}, format="json"
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    assert set(r.data) == {"error_code", "message", "details"} and r.data["error_code"] == "attribute_required"


@pytest.mark.contract
@pytest.mark.django_db
def test_member_value_must_be_project_member(session_client, workspace, project, story):
    a = Attribute.objects.create(
        project=project, workspace=workspace, issue_type=story.type, name="Owner", field_type="member"
    )
    r = session_client.patch(
        f"{_issues(workspace, project)}{story.id}/",
        {"attribute_values": {str(a.id): str(UserFactory().id)}},
        format="json",
    )
    assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
    _assert_flat(r, "invalid_value")


@pytest.mark.contract
@pytest.mark.django_db
def test_foreign_project_and_workspace_attribute_ids_rejected(session_client, workspace, project, story, create_user):
    p2 = Project.objects.create(name="P2", identifier="P2", workspace=workspace, created_by=create_user)
    seed_project(p2)
    ws2 = WorkspaceFactory(owner=create_user)
    p3 = ProjectFactory(workspace=ws2)
    seed_project(p3)
    for other in (p2, p3):
        foreign = _attr(other, T.USER_STORY, "story_points")
        r = session_client.patch(
            f"{_issues(workspace, project)}{story.id}/", {"attribute_values": {str(foreign.id): 3}}, format="json"
        )
        assert r.status_code == status.HTTP_400_BAD_REQUEST, r.data
        _assert_flat(r, "invalid_value")
    assert not AttributeValue.objects.filter(issue=story).exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_get_values_foreign_issue_404(session_client, workspace, project, create_user):
    p2 = Project.objects.create(name="P2", identifier="P2", workspace=workspace, created_by=create_user)
    ProjectMemberFactory(project=p2, member=create_user, workspace=workspace, role=ADMIN)
    seed_project(p2)
    foreign = Issue.objects.create(name="E", project=p2, type=get_type(workspace.id, T.EPIC))
    assert session_client.get(_values_url(workspace, project, foreign)).status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.contract
@pytest.mark.django_db
def test_create_with_values_records_activity(session_client, workspace, project, feature):
    ac = _attr(project, T.USER_STORY, "acceptance_criteria")
    body = {
        "name": "s",
        "type_id": str(get_type(workspace.id, T.USER_STORY).id),
        "parent_id": str(feature.id),
        "attribute_values": {str(ac.id).upper(): "Given"},  # non-canonical key is normalized
    }
    with (
        mock.patch("plane.app.views.issue.base.issue_activity") as task,
        mock.patch("plane.app.views.issue.base.model_activity"),
    ):
        r = session_client.post(_issues(workspace, project), body, format="json")
    assert r.status_code == status.HTTP_201_CREATED, r.data
    kwargs = {**task.delay.call_args.kwargs, "origin": None, "notification": False}
    issue_activity(**kwargs)
    act = IssueActivity.objects.get(issue_id=r.data["id"], field="attribute")
    assert act.new_identifier == ac.id and act.new_value == "Given"


@pytest.mark.contract
@pytest.mark.django_db
def test_triage_create_with_values_skips_required(workspace, project, story):
    steps = _attr(project, T.BUG, "steps_to_reproduce")
    triage = State.objects.create(name="Triage", group="triage", project=project, workspace=workspace)
    s = IssueCreateSerializer(
        data={
            "name": "b",
            "type_id": str(get_type(workspace.id, T.BUG).id),
            "parent_id": str(story.id),
            "attribute_values": {str(steps.id): "x"},
            "state_id": str(triage.id),  # triage mode = triage state + intake context
        },
        context={
            "project_id": project.id,
            "workspace_id": workspace.id,
            "default_assignee_id": None,
            "allow_triage_state": True,
        },
    )
    assert s.is_valid(), s.errors
    issue = s.save()
    assert AttributeValue.objects.get(issue=issue).value_text == "x"


@pytest.mark.contract
@pytest.mark.django_db
def test_guest_cannot_write_values(workspace, project, story):
    guest = UserFactory()
    WorkspaceMemberFactory(workspace=workspace, member=guest, role=GUEST)
    ProjectMemberFactory(project=project, member=guest, workspace=workspace, role=GUEST)
    Issue.objects.filter(pk=story.pk).update(created_by=guest)
    c = APIClient()
    c.force_authenticate(user=guest)
    sp = _attr(project, T.USER_STORY, "story_points")
    r = c.patch(f"{_issues(workspace, project)}{story.id}/", {"attribute_values": {str(sp.id): 3}}, format="json")
    assert r.status_code == status.HTTP_403_FORBIDDEN, r.data
    assert not AttributeValue.objects.filter(issue=story).exists()
    assert c.get(_values_url(workspace, project, story)).status_code == status.HTTP_200_OK


@pytest.mark.contract
@pytest.mark.django_db
def test_hidden_attribute_value_kept_not_returned(session_client, workspace, project, story):
    sp = _attr(project, T.USER_STORY, "story_points")
    ac = _attr(project, T.USER_STORY, "acceptance_criteria")
    r = session_client.patch(
        f"{_issues(workspace, project)}{story.id}/",
        {"attribute_values": {str(sp.id): 8, str(ac.id): "x"}},
        format="json",
    )
    assert r.status_code == status.HTTP_204_NO_CONTENT, getattr(r, "data", None)
    Attribute.objects.filter(pk=sp.pk).update(is_active=False)
    Attribute.objects.filter(pk=ac.pk).update(deleted_at=timezone.now())  # soft delete
    got = session_client.get(_values_url(workspace, project, story)).data
    assert got == {}
    assert AttributeValue.all_objects.filter(issue=story).count() == 2


@pytest.mark.contract
@pytest.mark.django_db
def test_activity_recorded_for_value_and_parent_change(session_client, workspace, project, story, feature):
    other = Issue.objects.create(name="F2", project=project, type=feature.type, parent=feature.parent)
    sp = _attr(project, T.USER_STORY, "story_points")
    with (
        mock.patch("plane.app.views.issue.base.issue_activity") as task,
        mock.patch("plane.app.views.issue.base.model_activity"),
    ):
        r = session_client.patch(
            f"{_issues(workspace, project)}{story.id}/",
            {"parent_id": str(other.id), "attribute_values": {str(sp.id): 3}},
            format="json",
        )
    assert r.status_code == status.HTTP_204_NO_CONTENT, getattr(r, "data", None)
    kwargs = {**task.delay.call_args.kwargs, "origin": None, "notification": False}
    assert "attribute_values" in json.loads(kwargs["requested_data"])
    issue_activity(**kwargs)
    acts = IssueActivity.objects.filter(issue=story)
    assert acts.filter(field="parent", new_identifier=other.id).exists()
    attr_act = acts.get(field="attribute")
    assert attr_act.new_identifier == sp.id and attr_act.new_value == "3"


@pytest.mark.contract
@pytest.mark.django_db
def test_value_write_check_uses_request_user_and_trusts_no_user(workspace, project):
    from django.contrib.auth.models import AnonymousUser
    from rest_framework.exceptions import PermissionDenied

    from plane.ee.work_item_types.validators import check_can_write_values

    check_can_write_values(project.id, None)  # internal caller: trusted, no 403
    check_can_write_values(project.id, AnonymousUser())
    outsider = UserFactory()
    with pytest.raises(PermissionDenied) as e:
        check_can_write_values(project.id, outsider)
    assert e.value.detail["error_code"] == "permission_denied"


@pytest.mark.contract
@pytest.mark.django_db
def test_restricted_guest_cannot_read_values_of_others_issues(workspace, project, story):
    project.guest_view_all_features = False
    project.save()
    guest = UserFactory()
    WorkspaceMemberFactory(workspace=workspace, member=guest, role=GUEST)
    ProjectMemberFactory(project=project, member=guest, workspace=workspace, role=GUEST)
    c = APIClient()
    c.force_authenticate(user=guest)
    r = c.get(_issues(workspace, project) + f"{story.id}/attribute-values/")
    assert r.status_code == status.HTTP_404_NOT_FOUND
