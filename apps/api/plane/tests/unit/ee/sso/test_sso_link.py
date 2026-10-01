# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from plane.db.models import Account, User
from plane.ee.sso.identity import subject_key

GUID = "11111111-1111-1111-1111-111111111111"


@pytest.mark.unit
@pytest.mark.django_db
def test_links_an_existing_user_to_an_oidc_subject():
    user = User.objects.create(email="an@corp.com", username="an")
    call_command("sso_link", provider="oidc", email="AN@corp.com", subject="https://idp.example.com|sub-1")
    account = Account.objects.get(user=user)
    assert account.provider == "sso-oidc"
    assert account.provider_account_id == subject_key("https://idp.example.com", "sub-1")


@pytest.mark.unit
@pytest.mark.django_db
def test_links_an_azure_object_id_lowercased():
    user = User.objects.create(email="an@corp.com", username="an")
    call_command("sso_link", provider="azure_ad", email="an@corp.com", subject=f"{GUID.upper()}:OID-1")
    assert Account.objects.get(user=user).provider_account_id == f"{GUID}:oid-1"


@pytest.mark.unit
@pytest.mark.django_db
@pytest.mark.parametrize("subject", ["oid-only", f"{GUID}:", "not-a-guid:oid-1"])
def test_azure_subject_must_be_tenant_guid_colon_oid(subject):
    User.objects.create(email="an@corp.com", username="an")
    with pytest.raises(CommandError):
        call_command("sso_link", provider="azure_ad", email="an@corp.com", subject=subject)


@pytest.mark.unit
@pytest.mark.django_db
def test_unknown_email_and_double_linking_are_refused():
    User.objects.create(email="an@corp.com", username="an")
    User.objects.create(email="bo@corp.com", username="bo")
    with pytest.raises(CommandError):
        call_command("sso_link", provider="oidc", email="nobody@corp.com", subject="https://i|s")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://i|s")
    with pytest.raises(CommandError):
        call_command("sso_link", provider="oidc", email="bo@corp.com", subject="https://i|s")


@pytest.mark.unit
@pytest.mark.django_db
def test_unlink_removes_the_link():
    user = User.objects.create(email="an@corp.com", username="an")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://i|s")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://i|s", unlink=True)
    assert not Account.objects.filter(user=user).exists()


@pytest.mark.unit
@pytest.mark.django_db
def test_subject_may_contain_pipes_trailing_slash_is_equivalent_and_move_repoints():
    an = User.objects.create(email="an@corp.com", username="an")
    bo = User.objects.create(email="bo@corp.com", username="bo")
    call_command("sso_link", provider="oidc", email="an@corp.com", subject="https://t.auth0.com/|auth0|123")
    key = subject_key("https://t.auth0.com", "auth0|123")
    assert subject_key("https://t.auth0.com/", "auth0|123") == key  # trailing slash is normalised
    assert Account.objects.get(user=an).provider_account_id == key
    with pytest.raises(CommandError):
        call_command("sso_link", provider="oidc", email="bo@corp.com", subject="https://t.auth0.com|auth0|123")
    call_command("sso_link", provider="oidc", email="bo@corp.com", subject="https://t.auth0.com|auth0|123", move=True)
    assert Account.objects.get(provider_account_id=key).user_id == bo.id
