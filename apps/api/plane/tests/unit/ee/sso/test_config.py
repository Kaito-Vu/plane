# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.ee.sso.config import (
    PROVIDERS,
    config_key,
    get_sso_config,
    list_enabled_providers,
    seed_config,
)
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data


def _set(provider, field, value, encrypted=False):
    row = InstanceConfiguration.objects.get(key=config_key(provider, field))
    row.value = encrypt_data(value) if encrypted else value
    row.save()


@pytest.mark.unit
@pytest.mark.django_db
def test_seed_is_idempotent_and_marks_secret_encrypted():
    seed_config()
    seed_config()
    expected = sum(2 + len(p["fields"]) for p in PROVIDERS.values())  # ENABLED + LABEL + extras
    assert InstanceConfiguration.objects.filter(key__startswith="EE_SSO_").count() == expected
    assert InstanceConfiguration.objects.get(key="EE_SSO_OIDC_CLIENT_SECRET").is_encrypted is True
    assert InstanceConfiguration.objects.get(key="EE_SSO_OIDC_CLIENT_ID").is_encrypted is False


@pytest.mark.unit
@pytest.mark.django_db
def test_disabled_or_incomplete_returns_none():
    seed_config()
    assert get_sso_config("oidc") is None
    _set("oidc", "ENABLED", "1")
    _set("oidc", "CLIENT_ID", "cid")
    assert get_sso_config("oidc") is None  # secret + issuer missing
    assert get_sso_config("nope") is None


@pytest.mark.unit
@pytest.mark.django_db
def test_enabled_oidc_decrypts_secret_and_lists():
    seed_config()
    _set("oidc", "ENABLED", "1")
    _set("oidc", "LABEL", "ETC SSO")
    _set("oidc", "CLIENT_ID", "cid")
    _set("oidc", "CLIENT_SECRET", "sek", encrypted=True)
    _set("oidc", "ISSUER", "https://idp.example.com")
    cfg = get_sso_config("oidc")
    assert cfg["CLIENT_SECRET"] == "sek"
    assert cfg["SCOPE"] == "openid profile"
    assert list_enabled_providers() == [{"id": "oidc", "label": "ETC SSO", "protocol": "oidc"}]


@pytest.mark.unit
@pytest.mark.django_db
def test_azure_requires_a_guid_tenant():
    seed_config()
    for f, v in [("ENABLED", "1"), ("CLIENT_ID", "c"), ("TENANT_ID", "contoso.onmicrosoft.com")]:
        _set("azure_ad", f, v)
    _set("azure_ad", "CLIENT_SECRET", "s", encrypted=True)
    assert get_sso_config("azure_ad") is None
    for bad in ("common", "organizations", "consumers"):
        _set("azure_ad", "TENANT_ID", bad)
        assert get_sso_config("azure_ad") is None
    _set("azure_ad", "TENANT_ID", "11111111-1111-1111-1111-111111111111")
    assert get_sso_config("azure_ad") is not None


@pytest.mark.unit
@pytest.mark.django_db
def test_allow_signup_defaults_to_on_and_enabled_to_off():
    seed_config()
    assert InstanceConfiguration.objects.get(key="EE_SSO_AZURE_AD_ALLOW_SIGNUP").value == "1"
    assert InstanceConfiguration.objects.get(key="EE_SSO_AZURE_AD_ENABLED").value == "0"


@pytest.mark.unit
@pytest.mark.django_db
def test_seed_invalidates_cached_configuration_list():
    from django.core.cache import cache

    # the test DB already holds seeded rows (post_migrate), so start from an empty table
    InstanceConfiguration.all_objects.filter(key__startswith="EE_SSO_").delete()  # hard delete: model is soft-delete
    cache.set("/api/instances/configurations/", ["stale"])
    seed_config()
    assert cache.get("/api/instances/configurations/") is None


@pytest.mark.unit
def test_callback_url_default_and_override(settings):
    from django.test import RequestFactory

    from plane.ee.sso.config import callback_url

    settings.WEB_URL = "https://plane.example.com/"
    request = RequestFactory().get("/")
    default = "https://plane.example.com/auth/sso/oidc/callback/"
    assert callback_url(request, "oidc", {}) == default
    assert callback_url(request, "saml", {}) == "https://plane.example.com/auth/sso/saml/acs/"
    assert callback_url(request, "oidc", {"CALLBACK_URL": " https://sso.corp.com/cb/ "}) == "https://sso.corp.com/cb/"
    # non-absolute values are ignored
    assert callback_url(request, "oidc", {"CALLBACK_URL": "/relative"}) == default


@pytest.mark.unit
@pytest.mark.django_db
def test_default_label_when_blank():
    seed_config()
    for f, v in [("ENABLED", "1"), ("CLIENT_ID", "c"), ("TENANT_ID", "11111111-1111-1111-1111-111111111111")]:
        _set("azure_ad", f, v)
    _set("azure_ad", "CLIENT_SECRET", "s", encrypted=True)
    assert list_enabled_providers()[0]["label"] == "Microsoft"
