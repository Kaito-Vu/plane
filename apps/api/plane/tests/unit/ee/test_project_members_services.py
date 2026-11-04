import uuid

import pytest

from plane.db.models import Project, ProjectMember, User, Workspace, WorkspaceMember
from plane.ee.project_members.services import (
    UserNotEligible,
    deprovision_if_orphan,
    eligible_users,
    provision_workspace_member,
    sweep_orphan_workspace_members,
)


def _user(email, **kw):
    return User.objects.create(email=email, username=email, **kw)


@pytest.fixture
def other_user(db):
    return _user(email="other@plane.so", first_name="O", last_name="U")


@pytest.fixture
def project(workspace, create_user):
    return Project.objects.create(name="P1", identifier="P1", workspace=workspace, created_by=create_user)


def _wm(workspace, user):
    return WorkspaceMember.objects.get(workspace=workspace, member=user)


def _add_pm(project, user, role=15, active=True):
    return ProjectMember.objects.create(project=project, member=user, role=role, is_active=active)


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_creates_member_role_15_for_project_admin(workspace, other_user):
    wm = provision_workspace_member(workspace, other_user, 20)
    assert wm.role == 15 and wm.is_active
    assert WorkspaceMember.objects.filter(workspace=workspace, member=other_user).count() == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_guest_maps_to_5(workspace, other_user):
    assert provision_workspace_member(workspace, other_user, 5).role == 5


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_never_downgrades_active_ws_admin(workspace, create_user):
    wm = provision_workspace_member(workspace, create_user, 5)
    assert wm.role == 20
    assert _wm(workspace, create_user).role == 20


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_never_downgrades_active_member_to_guest(workspace, other_user):
    provision_workspace_member(workspace, other_user, 15)
    assert provision_workspace_member(workspace, other_user, 5).role == 15


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_never_raises_active_guest(workspace, other_user):
    WorkspaceMember.objects.create(workspace=workspace, member=other_user, role=5)
    assert provision_workspace_member(workspace, other_user, 20).role == 5
    assert _wm(workspace, other_user).role == 5


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_reactivates_inactive_row_with_mapped_role(workspace, other_user):
    WorkspaceMember.objects.create(workspace=workspace, member=other_user, role=20, is_active=False)
    wm = provision_workspace_member(workspace, other_user, 5)
    assert wm.is_active and wm.role == 5
    assert _wm(workspace, other_user).role == 5


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_is_idempotent(workspace, other_user):
    provision_workspace_member(workspace, other_user, 15)
    provision_workspace_member(workspace, other_user, 15)
    assert WorkspaceMember.objects.filter(workspace=workspace, member=other_user).count() == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_eligible_users_rejects_unknown_inactive_bot_and_malformed(other_user):
    assert eligible_users([str(other_user.id)]) == [other_user]
    inactive = _user(email="i@plane.so", is_active=False)
    bot = _user(email="b@plane.so", is_bot=True)
    messages = set()
    for bad in (str(uuid.uuid4()), str(inactive.id), str(bot.id), "not-a-uuid"):
        with pytest.raises(UserNotEligible) as exc:
            eligible_users([str(other_user.id), bad])
        messages.add(str(exc.value))
    assert len(messages) == 1
    assert "not-a-uuid" not in messages.pop()


@pytest.mark.unit
@pytest.mark.django_db
def test_deprovision_disables_when_no_active_project_member(workspace, project, other_user):
    provision_workspace_member(workspace, other_user, 15)
    # queryset update bypasses the post_save receiver, which would deprovision on its own
    ProjectMember.objects.filter(pk=_add_pm(project, other_user).pk).update(is_active=False)
    assert deprovision_if_orphan(workspace.id, other_user.id) is True
    assert _wm(workspace, other_user).is_active is False


@pytest.mark.unit
@pytest.mark.django_db
def test_deprovision_skips_ws_admin_and_owner_and_users_with_other_projects(
    workspace, project, create_user, other_user
):
    # ws admin (also owner)
    assert deprovision_if_orphan(workspace.id, create_user.id) is False
    # owner who is not admin
    owner2 = _user(email="o2@plane.so")
    ws2 = Workspace.objects.create(name="W2", slug="w2", owner=owner2)
    WorkspaceMember.objects.create(workspace=ws2, member=owner2, role=15)
    assert deprovision_if_orphan(ws2.id, owner2.id) is False
    assert _wm(ws2, owner2).is_active
    # still in an active project
    provision_workspace_member(workspace, other_user, 15)
    _add_pm(project, other_user)
    assert deprovision_if_orphan(workspace.id, other_user.id) is False
    assert _wm(workspace, other_user).is_active
    # a missing row is a no-op
    assert deprovision_if_orphan(workspace.id, uuid.uuid4()) is False


@pytest.mark.unit
@pytest.mark.django_db
def test_deprovision_only_affects_given_workspace(workspace, other_user, create_user):
    ws2 = Workspace.objects.create(name="W2", slug="w2", owner=create_user)
    provision_workspace_member(workspace, other_user, 15)
    provision_workspace_member(ws2, other_user, 15)
    assert deprovision_if_orphan(workspace.id, other_user.id) is True
    assert _wm(workspace, other_user).is_active is False
    assert _wm(ws2, other_user).is_active is True


@pytest.mark.unit
@pytest.mark.django_db
def test_sweep_disables_orphans_after_project_soft_delete(workspace, project, other_user):
    provision_workspace_member(workspace, other_user, 15)
    _add_pm(project, other_user)
    assert sweep_orphan_workspace_members() == 0
    # soft-delete the project only (member rows are cleaned asynchronously)
    Project.objects.filter(pk=project.pk).update(deleted_at="2026-01-01T00:00:00Z")
    assert sweep_orphan_workspace_members() == 1
    assert _wm(workspace, other_user).is_active is False
    assert sweep_orphan_workspace_members() == 0


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("bad_role", [10, 25, None, "15", [15]])
def test_provision_unknown_role_clamps_to_guest(workspace, other_user, bad_role):
    wm = provision_workspace_member(workspace, other_user, bad_role)
    assert wm.role == 5 and wm.is_active


def _profile(user, **kw):
    from plane.db.models import Profile

    return Profile.objects.create(user=user, **kw)


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_onboards_user_whose_profile_step_is_complete(workspace, other_user):
    p = _profile(
        other_user, onboarding_step={"profile_complete": True, "workspace_create": False, "workspace_join": False}
    )
    provision_workspace_member(workspace, other_user, 15)
    p.refresh_from_db()
    assert p.is_onboarded is True
    assert p.onboarding_step["workspace_join"] is True and p.onboarding_step["profile_complete"] is True


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_onboards_on_reactivation_too(workspace, other_user):
    WorkspaceMember.objects.create(workspace=workspace, member=other_user, role=15, is_active=False)
    p = _profile(other_user, onboarding_step={"profile_complete": True})
    provision_workspace_member(workspace, other_user, 15)
    p.refresh_from_db()
    assert p.is_onboarded is True


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_leaves_incomplete_profile_untouched(workspace, other_user):
    p = _profile(other_user)
    provision_workspace_member(workspace, other_user, 15)
    p.refresh_from_db()
    assert p.is_onboarded is False
    assert p.onboarding_step["workspace_join"] is False


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_already_active_row_leaves_profile_untouched(workspace, other_user):
    WorkspaceMember.objects.create(workspace=workspace, member=other_user, role=15)
    p = _profile(other_user, onboarding_step={"profile_complete": True})
    provision_workspace_member(workspace, other_user, 15)
    p.refresh_from_db()
    assert p.is_onboarded is False


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_without_profile_row_does_not_raise(workspace, other_user):
    assert provision_workspace_member(workspace, other_user, 15).is_active


@pytest.mark.unit
@pytest.mark.django_db
def test_signal_ignores_project_member_without_user(workspace, project):
    from unittest import mock

    with (
        mock.patch("plane.ee.project_members.signals.provision_workspace_member") as prov,
        mock.patch("plane.ee.project_members.signals.deprovision_if_orphan") as deprov,
    ):
        pm = ProjectMember.objects.create(project=project, member=None, workspace=workspace, role=15)
        assert pm.pk
        pm.is_active = False
        pm.save()  # deactivation path also skipped
    prov.assert_not_called()
    deprov.assert_not_called()
    assert not WorkspaceMember.objects.filter(member__isnull=True).exists()


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("bad", [0, [], ["profile_complete"], "profile_complete"])
def test_provision_survives_non_dict_onboarding_step(workspace, other_user, bad):
    p = _profile(other_user)
    type(p).objects.filter(pk=p.pk).update(onboarding_step=bad)
    wm = provision_workspace_member(workspace, other_user, 15)
    assert wm.is_active
    p.refresh_from_db()
    assert p.onboarding_step == bad and p.is_onboarded is False


@pytest.mark.unit
@pytest.mark.django_db
def test_provision_survives_profile_write_database_error(workspace, other_user):
    from unittest import mock

    from django.db import DatabaseError

    p = _profile(other_user, onboarding_step={"profile_complete": True})
    with mock.patch("plane.db.models.Profile.save", side_effect=DatabaseError("boom")):
        wm = provision_workspace_member(workspace, other_user, 15)
    assert wm.is_active
    assert WorkspaceMember.objects.filter(workspace=workspace, member=other_user, is_active=True).exists()
    p.refresh_from_db()
    assert p.is_onboarded is False
