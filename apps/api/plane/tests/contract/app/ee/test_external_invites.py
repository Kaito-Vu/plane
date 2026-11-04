import uuid
from unittest import mock

import pytest
from django.apps import apps as real_apps
from django.utils import timezone
from importlib import import_module
from rest_framework import status
from rest_framework.test import APIClient

from plane.authentication.utils.workspace_project_join import process_workspace_project_invitations
from plane.db.models import Project, ProjectMember, ProjectMemberInvite, WorkspaceMember, WorkspaceMemberInvite
from plane.ee.project_members.invites import KEY, external_invites_enabled
from plane.license.models import Instance, InstanceAdmin, InstanceConfiguration

migration = import_module("plane.ee.migrations.0004_delete_pending_invites")


def set_flag(value):
    InstanceConfiguration.objects.update_or_create(key=KEY, defaults={"value": value, "category": "INVITES"})


@pytest.fixture
def project(workspace, create_user):
    p = Project.objects.create(name="P", identifier="P", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=p, member=create_user, workspace=workspace, role=20)
    return p


@pytest.mark.contract
@pytest.mark.django_db
def test_flag_default_off():
    assert external_invites_enabled() is False
    set_flag("1")
    assert external_invites_enabled() is True


@pytest.mark.contract
@pytest.mark.django_db
@pytest.mark.parametrize("value", ["True", "", "0", None, "absent"])
def test_malformed_values_are_off(value):
    if value != "absent":
        set_flag(value)
    assert external_invites_enabled() is False


def _endpoints(workspace, project):
    s, pk = workspace.slug, uuid.uuid4()
    body = {"emails": [{"email": "x@plane.so", "role": 5}]}
    return [
        ("session", f"/api/workspaces/{s}/invitations/", body),
        ("session", f"/api/workspaces/{s}/invitations/{pk}/join/", {"token": "t"}),
        ("session", "/api/users/me/workspaces/invitations/", {"invitations": [str(pk)]}),
        ("session", f"/api/workspaces/{s}/projects/{project.id}/invitations/", body),
        ("session", f"/api/workspaces/{s}/projects/{project.id}/join/{pk}/", {"token": "t"}),
        ("key", f"/api/v1/workspaces/{s}/invitations/", {"email": "x@plane.so", "role": 5}),
    ]


@pytest.mark.contract
@pytest.mark.django_db
@pytest.mark.parametrize("idx", range(6))
def test_each_shadowed_endpoint_410_when_off_and_creates_no_workspace_member(
    session_client, api_key_client, workspace, project, idx
):
    kind, url, body = _endpoints(workspace, project)[idx]
    client = session_client if kind == "session" else api_key_client
    before = WorkspaceMember.objects.count()
    before_pm = ProjectMember.objects.count()
    r = client.post(url, body, format="json")
    assert r.status_code == status.HTTP_410_GONE, r.content
    assert r.json()["code"] == "INVITES_DISABLED" and r.json()["error"]
    assert WorkspaceMember.objects.count() == before
    assert not WorkspaceMemberInvite.objects.exists()
    assert not ProjectMemberInvite.objects.exists()
    assert ProjectMember.objects.count() == before_pm


@pytest.mark.contract
@pytest.mark.django_db
def test_forwards_to_core_when_on(session_client, workspace):
    set_flag("1")
    with mock.patch("plane.app.views.workspace.invite.workspace_invitation"):
        r = session_client.post(
            f"/api/workspaces/{workspace.slug}/invitations/",
            {"emails": [{"email": "new@plane.so", "role": 5}]},
            format="json",
        )
    assert r.status_code == status.HTTP_200_OK, r.content
    assert WorkspaceMemberInvite.objects.filter(email="new@plane.so").exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_list_routes_still_work_when_off(session_client, api_key_client, workspace, project):
    WorkspaceMemberInvite.objects.create(workspace=workspace, email="a@plane.so", token="t", role=5)
    assert session_client.get(f"/api/workspaces/{workspace.slug}/invitations/").status_code == 200
    assert session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/invitations/").status_code == 200
    assert session_client.get("/api/users/me/workspaces/invitations/").status_code == 200
    r = api_key_client.get(f"/api/v1/workspaces/{workspace.slug}/invitations/")
    assert r.status_code == 200 and len(r.json()) == 1


@pytest.mark.contract
@pytest.mark.django_db
def test_status_endpoint_any_authenticated_user(session_client):
    assert APIClient().get("/api/external-invites/").status_code in (401, 403)
    assert session_client.get("/api/external-invites/").json() == {"enabled": False}
    set_flag("1")
    assert session_client.get("/api/external-invites/").json() == {"enabled": True}


@pytest.mark.contract
@pytest.mark.django_db
def test_toggle_god_mode_only(session_client, create_user, workspace):
    url = "/api/instances/external-invites/"
    assert session_client.patch(url, {"enabled": True}, format="json").status_code == 403  # ws Admin
    assert not InstanceConfiguration.objects.filter(key=KEY).exists()

    instance = Instance.objects.create(
        instance_name="t", instance_id="t", current_version="1", last_checked_at=timezone.now()
    )
    InstanceAdmin.objects.create(instance=instance, user=create_user, role=20)
    create_user.refresh_from_db()  # signal flips is_superuser in the DB
    assert session_client.patch(url, {"enabled": "yes"}, format="json").status_code == 400
    assert session_client.patch(url, {"enabled": 1}, format="json").status_code == 400
    assert session_client.patch(url, {"enabled": True}, format="json").json() == {"enabled": True}
    assert InstanceConfiguration.objects.get(key=KEY).value == "1"
    assert session_client.get(url).json() == {"enabled": True}
    assert session_client.patch(url, {"enabled": False}, format="json").status_code == 200
    assert InstanceConfiguration.objects.get(key=KEY).value == "0"


def _seed_invites(workspace, project, create_user):
    wi = WorkspaceMemberInvite.objects.create(
        workspace=workspace, email=create_user.email, token="a", role=15, accepted=True
    )
    pi = ProjectMemberInvite.objects.create(
        workspace=workspace, project=project, email=create_user.email, token="b", role=15, accepted=True
    )
    gone = WorkspaceMemberInvite.objects.create(workspace=workspace, email="old@plane.so", token="c", role=5)
    gone.delete()  # soft
    return wi, pi, gone


@pytest.mark.contract
@pytest.mark.django_db
def test_migration_hard_deletes_invites(workspace, project, create_user):
    _seed_invites(workspace, project, create_user)
    assert WorkspaceMemberInvite.all_objects.count() == 2
    migration.delete_all_invites(real_apps, mock.Mock(connection=mock.Mock(alias="default")))
    assert WorkspaceMemberInvite.all_objects.count() == 0
    assert ProjectMemberInvite.all_objects.count() == 0


@pytest.mark.contract
@pytest.mark.django_db
def test_login_with_old_accepted_invite_creates_no_row(workspace, project, create_user):
    # Direct test of the sign-in hook (it is what the auth flow calls) after the migration ran.
    _seed_invites(workspace, project, create_user)
    WorkspaceMember.objects.filter(member=create_user).delete(soft=False)
    ProjectMember.objects.filter(member=create_user).delete(soft=False)
    migration.delete_all_invites(real_apps, mock.Mock(connection=mock.Mock(alias="default")))
    process_workspace_project_invitations(create_user)
    assert not WorkspaceMember.objects.filter(member=create_user).exists()
    assert not ProjectMember.objects.filter(member=create_user).exists()
