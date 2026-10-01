# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.utils import timezone

from plane.db.models import Issue, IssueType, State, User, Workspace, WorkspaceMember
from plane.db.models.issue_type import ProjectIssueType
from plane.ee.work_item_types.seed import seed_types


def base(ws):
    return f"/api/workspaces/{ws.slug}/work-item-types/"


@pytest.fixture
def seeded(workspace):
    return seed_types(workspace)


@pytest.mark.contract
def test_list(session_client, workspace, seeded):
    r = session_client.get(base(workspace))
    assert r.status_code == 200
    assert {x["name"] for x in r.json()} >= {"Epic", "Feature", "Task"}


@pytest.mark.contract
def test_create_custom_type(session_client, workspace, seeded):
    body = {"name": "Spike", "level": 1, "logo_props": {"in_use": "icon", "icon": {"name": "Zap", "color": "#fff000", "background_color": "#123456"}}}
    r = session_client.post(base(workspace), body, format="json")
    assert r.status_code == 201, r.content
    assert IssueType.objects.filter(workspace=workspace, name="Spike").exists()


@pytest.mark.contract
@pytest.mark.parametrize(
    "logo",
    [
        {"in_use": "icon", "icon": {"name": "<script>", "color": "#fff000"}},
        {"in_use": "icon", "icon": {"name": "Zap", "color": "red"}},
        {"in_use": "icon", "evil": 1},
    ],
)
def test_bad_logo_props_rejected(session_client, workspace, seeded, logo):
    r = session_client.post(base(workspace), {"name": "X", "level": 1, "logo_props": logo}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_duplicate_name_case_insensitive(session_client, workspace, seeded):
    r = session_client.post(base(workspace), {"name": "task", "level": 1}, format="json")
    assert r.status_code == 400


@pytest.mark.contract
def test_member_cannot_write_but_can_read(api_client, workspace, seeded):
    member = User.objects.create(email="m@plane.so", username="m-user")
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    api_client.force_authenticate(user=member)
    assert api_client.get(base(workspace)).status_code == 200
    assert api_client.post(base(workspace), {"name": "Z", "level": 1}, format="json").status_code == 403


@pytest.mark.contract
def test_cannot_touch_other_workspace(session_client, workspace, seeded, create_user):
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=1)
    assert session_client.patch(f"{base(workspace)}{foreign.id}/", {"name": "hack"}, format="json").status_code == 404


@pytest.mark.contract
def test_preset_level_is_locked_and_not_deletable(session_client, workspace, seeded):
    url = f"{base(workspace)}{seeded['task'].id}/"
    assert session_client.patch(url, {"level": 3}, format="json").status_code == 409
    assert session_client.delete(url).status_code == 409


@pytest.mark.contract
def test_delete_in_use_requires_migrate_to(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    issue = Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=custom, created_by=create_user)
    ProjectIssueType.objects.create(project=project, issue_type=seeded["task"], level=1)
    url = f"{base(workspace)}{custom.id}/"
    r = session_client.delete(url)
    assert r.status_code == 409 and r.json()["count"] == 1
    r = session_client.delete(f"{url}?migrate_to={seeded['task'].id}")
    assert r.status_code == 204
    issue.refresh_from_db()
    assert issue.type_id == seeded["task"].id
    assert not IssueType.objects.filter(pk=custom.pk).exists()


@pytest.mark.contract
def test_type_cap(session_client, workspace, seeded, settings):
    settings.WORK_ITEM_TYPES_MAX = IssueType.objects.filter(workspace=workspace).count()
    assert session_client.post(base(workspace), {"name": "One more", "level": 1}, format="json").status_code == 400


@pytest.mark.contract
def test_migrate_to_must_match_level(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=custom, created_by=create_user)
    r = session_client.delete(f"{base(workspace)}{custom.id}/?migrate_to={seeded['epic'].id}")
    assert r.status_code == 400


def _issue(workspace, project, create_user, t, **kw):
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    return Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=t, created_by=create_user, **kw)


@pytest.mark.contract
def test_invalid_migrate_to_uuid(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    _issue(workspace, project, create_user, custom)
    assert session_client.delete(f"{base(workspace)}{custom.id}/?migrate_to=abc").status_code == 400
    assert session_client.delete(f"{base(workspace)}{custom.id}/?migrate_to={custom.id}").status_code == 400


@pytest.mark.contract
def test_migrate_to_other_workspace_404(session_client, workspace, project, seeded, create_user):
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    foreign = IssueType.objects.create(workspace=other, name="F", level=1)
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    _issue(workspace, project, create_user, custom)
    assert session_client.delete(f"{base(workspace)}{custom.id}/?migrate_to={foreign.id}").status_code == 404


@pytest.mark.contract
def test_member_cannot_patch_or_delete(api_client, workspace, seeded):
    member = User.objects.create(email="m2@plane.so", username="m2")
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    api_client.force_authenticate(user=member)
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    url = f"{base(workspace)}{custom.id}/"
    assert api_client.patch(url, {"name": "x"}, format="json").status_code == 403
    assert api_client.delete(url).status_code == 403


@pytest.mark.contract
def test_foreign_admin_cannot_write(api_client, workspace, seeded, create_user):
    other = Workspace.objects.create(name="O", owner=create_user, slug="other")
    admin = User.objects.create(email="a@plane.so", username="a-user")
    WorkspaceMember.objects.create(workspace=other, member=admin, role=20)
    api_client.force_authenticate(user=admin)
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    assert api_client.post(base(workspace), {"name": "Z", "level": 1}, format="json").status_code == 403
    assert api_client.patch(f"{base(workspace)}{custom.id}/", {"name": "x"}, format="json").status_code == 403
    assert api_client.delete(f"{base(workspace)}{custom.id}/").status_code == 403


@pytest.mark.contract
def test_level_locked_on_in_use_custom(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    _issue(workspace, project, create_user, custom)
    assert session_client.patch(f"{base(workspace)}{custom.id}/", {"level": 2}, format="json").status_code == 409


@pytest.mark.contract
def test_resend_same_level_on_preset_ok(session_client, workspace, seeded):
    t = seeded["task"]
    r = session_client.patch(f"{base(workspace)}{t.id}/", {"level": t.level, "is_epic": t.is_epic}, format="json")
    assert r.status_code == 200, r.content


@pytest.mark.contract
def test_rename_self_case_change_ok(session_client, workspace, seeded):
    custom = IssueType.objects.create(workspace=workspace, name="spike", level=1)
    assert session_client.patch(f"{base(workspace)}{custom.id}/", {"name": "SPIKE"}, format="json").status_code == 200


@pytest.mark.contract
def test_archived_issue_counts_as_in_use(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    _issue(workspace, project, create_user, custom, archived_at=timezone.now().date())
    assert session_client.delete(f"{base(workspace)}{custom.id}/").status_code == 409


@pytest.mark.contract
def test_whitespace_name_rejected(session_client, workspace, seeded):
    assert session_client.post(base(workspace), {"name": "   ", "level": 1}, format="json").status_code == 400


@pytest.mark.contract
def test_cannot_deactivate_project_default(session_client, workspace, project, seeded):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    ProjectIssueType.objects.create(project=project, issue_type=custom, level=1, is_default=True)
    url = f"{base(workspace)}{custom.id}/"
    assert session_client.patch(url, {"is_active": False}, format="json").status_code == 409
    other = IssueType.objects.create(workspace=workspace, name="Other", level=1)
    assert session_client.patch(f"{base(workspace)}{other.id}/", {"is_active": False}, format="json").status_code == 200


@pytest.mark.contract
def test_cannot_delete_project_default_type(session_client, workspace, project, seeded):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    ProjectIssueType.objects.create(project=project, issue_type=custom, level=1, is_default=True)
    assert session_client.delete(f"{base(workspace)}{custom.id}/").status_code == 409
    assert IssueType.objects.filter(pk=custom.pk).exists()


@pytest.mark.contract
@pytest.mark.parametrize("body", [[1, 2], "str"])
def test_non_object_body_is_400_not_500(session_client, workspace, seeded, body):
    assert session_client.post(base(workspace), body, format="json").status_code == 400
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    assert session_client.patch(f"{base(workspace)}{custom.id}/", body, format="json").status_code == 400


@pytest.mark.contract
def test_migrate_to_epic_mismatch_400(session_client, workspace, project, seeded, create_user):
    a = IssueType.objects.create(workspace=workspace, name="A", level=1)
    b = IssueType.objects.create(workspace=workspace, name="B", level=1, is_epic=True)
    _issue(workspace, project, create_user, a)
    r = session_client.delete(f"{base(workspace)}{a.id}/?migrate_to={b.id}")
    assert r.status_code == 400 and "epic flag" in r.json()["error"]


@pytest.mark.contract
def test_migrate_to_must_be_assigned_to_using_project(session_client, workspace, project, seeded, create_user):
    a = IssueType.objects.create(workspace=workspace, name="A", level=1)
    b = IssueType.objects.create(workspace=workspace, name="B", level=1)
    _issue(workspace, project, create_user, a)
    url = f"{base(workspace)}{a.id}/?migrate_to={b.id}"
    r = session_client.delete(url)
    assert r.status_code == 409 and "assigned to every project" in r.json()["error"]
    ProjectIssueType.objects.create(project=project, issue_type=b, level=1)
    assert session_client.delete(url).status_code == 204


@pytest.mark.contract
def test_drafts_counted_and_migrated(session_client, workspace, project, seeded, create_user):
    from plane.db.models import DraftIssue

    a = IssueType.objects.create(workspace=workspace, name="A", level=1)
    b = IssueType.objects.create(workspace=workspace, name="B", level=1)
    d = DraftIssue.objects.create(name="d", workspace=workspace, project=project, type=a, created_by=create_user)
    ProjectIssueType.objects.create(project=project, issue_type=b, level=1)
    url = f"{base(workspace)}{a.id}/"
    r = session_client.delete(url)
    assert r.status_code == 409 and r.json()["count"] == 1
    assert session_client.delete(f"{url}?migrate_to={b.id}").status_code == 204
    d.refresh_from_db()
    assert d.type_id == b.id
