# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import Issue, IssueType, State, User, Workspace, WorkspaceMember
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
    settings.WORK_ITEM_TYPES_MAX = 7  # presets already fill 7
    assert session_client.post(base(workspace), {"name": "One more", "level": 1}, format="json").status_code == 400


@pytest.mark.contract
def test_migrate_to_must_match_level(session_client, workspace, project, seeded, create_user):
    custom = IssueType.objects.create(workspace=workspace, name="Spike", level=1)
    state = State.objects.create(name="Todo", project=project, group="backlog", default=True)
    Issue.objects.create(name="i", workspace=workspace, project=project, state=state, type=custom, created_by=create_user)
    r = session_client.delete(f"{base(workspace)}{custom.id}/?migrate_to={seeded['epic'].id}")
    assert r.status_code == 400
