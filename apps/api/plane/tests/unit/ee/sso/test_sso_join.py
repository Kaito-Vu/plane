# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from plane.db.models import Account, User, Workspace, WorkspaceMember
from plane.ee.sso.identity import subject_key


@pytest.mark.unit
@pytest.mark.django_db
def test_adds_the_user_behind_a_subject_to_a_workspace_and_updates_the_role():
    owner = User.objects.create(email="owner@corp.com", username="owner")
    workspace = Workspace.objects.create(name="W", slug="w", owner=owner)
    user = User.objects.create(email="x@sso.invalid", username="x")
    Account.objects.create(
        user=user, provider="sso-oidc", provider_account_id=subject_key("https://idp", "s1"), access_token=""
    )
    call_command("sso_join", provider="oidc", subject="https://idp|s1", workspace="w")
    assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 15
    call_command("sso_join", provider="oidc", subject="https://idp|s1", workspace="w", role=20)
    assert WorkspaceMember.objects.get(workspace=workspace, member=user).role == 20


@pytest.mark.unit
@pytest.mark.django_db
def test_unknown_subject_or_workspace_is_refused():
    owner = User.objects.create(email="owner@corp.com", username="owner")
    Workspace.objects.create(name="W", slug="w", owner=owner)
    with pytest.raises(CommandError):
        call_command("sso_join", provider="oidc", subject="https://idp|nobody", workspace="w")
    with pytest.raises(CommandError):
        call_command("sso_join", provider="oidc", subject="https://idp|nobody", workspace="missing")
