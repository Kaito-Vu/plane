# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

from plane.ee.god_mode.access import is_god_mode_user
from plane.license.models import Instance, InstanceAdmin


@pytest.fixture
def instance(db):
    return Instance.objects.create(
        instance_name="t", instance_id="t", current_version="1", last_checked_at=timezone.now()
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "is_superuser, role, expected",
    [(True, 20, True), (False, 20, False), (True, 15, False), (True, None, False)],
)
def test_is_god_mode_user(instance, create_user, is_superuser, role, expected):
    create_user.is_superuser = is_superuser
    create_user.save()
    if role:
        InstanceAdmin.objects.create(instance=instance, user=create_user, role=role)
    assert is_god_mode_user(create_user) is expected


@pytest.mark.unit
def test_anonymous_denied(instance):
    assert is_god_mode_user(AnonymousUser()) is False


@pytest.mark.unit
def test_signal_grants_superuser_and_session_gate(instance, create_user, session_client):
    assert create_user.is_superuser is False
    admin = InstanceAdmin.objects.create(instance=instance, user=create_user, role=20)
    create_user.refresh_from_db()
    assert create_user.is_superuser is True

    # the admins API is now reachable, and self-removal is refused
    assert session_client.get("/api/instances/admins/").status_code == 200
    assert session_client.delete(f"/api/instances/admins/{admin.id}/").status_code == 400

    # a plain user is locked out of every InstanceAdminPermission endpoint
    create_user.is_superuser = False
    create_user.save()
    assert session_client.get("/api/instances/admins/").status_code == 403
