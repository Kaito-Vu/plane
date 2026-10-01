# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import Client, RequestFactory
from django.utils import timezone

from plane.db.models import Account
from plane.ee.sso.config import config_key, seed_config
from plane.ee.sso.saml import acs_url, metadata_url
from plane.license.models import Instance, InstanceConfiguration
from plane.tests.unit.ee.sso.saml_helpers import build_saml_response, make_cert_and_key

IDP = "https://idp.example.com/meta"


@pytest.fixture(scope="module")
def keys():
    return make_cert_and_key()


def _instance():
    Instance.objects.create(
        instance_name="t", instance_id="i", current_version="1", last_checked_at=timezone.now(), is_setup_done=True
    )


@pytest.fixture
def setup(db, keys):
    cache.delete_pattern("ee_sso_*")
    _instance()
    seed_config()
    for field, value in {
        "ENABLED": "1",
        "IDP_ENTITY_ID": IDP,
        "IDP_SSO_URL": "https://idp.example.com/sso",
        "IDP_X509CERT": keys[1],
    }.items():
        row = InstanceConfiguration.objects.get(key=config_key("saml", field))
        row.value = value
        row.save()


def _error_code(response):
    return parse_qs(urlparse(response["Location"]).query).get("error_code", [None])[0]


def _start(client):
    response = client.get("/auth/sso/saml/")
    assert response.status_code == 302
    relay = parse_qs(urlparse(response["Location"]).query)["RelayState"][0]
    return relay, cache.get(f"ee_sso_saml_relay:{relay}")["request_id"]


def _post_acs(client, keys, relay, request_id, **kw):
    request = RequestFactory().get("/")
    args = dict(
        acs_url=acs_url(request),
        idp_entity_id=IDP,
        sp_entity_id=metadata_url(request),
        in_response_to=request_id,
        name_id="persistent-new",
        key_pem=keys[0],
        cert_pem=keys[1],
    )
    args.update(kw)
    return client.post("/auth/sso/saml/acs/", {"SAMLResponse": build_saml_response(**args), "RelayState": relay})


@pytest.mark.unit
def test_metadata_is_public_xml(setup):
    response = Client().get("/auth/sso/saml/metadata/")
    assert response.status_code == 200
    assert "xml" in response["Content-Type"]
    assert b"EntityDescriptor" in response.content


@pytest.mark.unit
def test_initiate_redirects_to_idp_and_saves_relay(setup):
    relay, request_id = _start(Client())
    assert relay and request_id


@pytest.mark.unit
def test_initiate_unconfigured_redirects_with_error(db):
    seed_config()
    _instance()
    response = Client().get("/auth/sso/saml/")
    assert response.status_code == 302 and _error_code(response) == "6000"


@pytest.mark.unit
def test_acs_success_without_csrf_token_or_session(setup, keys):
    relay, request_id = _start(Client())
    # a fresh client models the IdP's cross-site POST: no session cookie, no CSRF token
    response = _post_acs(Client(enforce_csrf_checks=True, HTTP_USER_AGENT="pytest"), keys, relay, request_id)
    assert response.status_code == 302 and _error_code(response) is None
    assert Account.objects.filter(provider="sso-saml").count() == 1


@pytest.mark.unit
def test_oauth_callback_url_for_saml_is_a_provider_error_not_500(setup):
    # the generic OAuth callback route also matches /auth/sso/saml/callback/; it must fail cleanly
    response = Client().get("/auth/sso/saml/callback/?code=c&state=x")
    assert response.status_code == 302 and _error_code(response) == "6001"


@pytest.mark.unit
def test_acs_garbage_post_redirects_with_error(setup):
    relay, _ = _start(Client())
    response = Client().post("/auth/sso/saml/acs/", {"SAMLResponse": "garbage", "RelayState": relay})
    assert response.status_code == 302 and _error_code(response) == "6001"


@pytest.mark.unit
def test_acs_rejects_unknown_relay_state(setup, keys):
    response = _post_acs(Client(), keys, "bogus", "_x")
    assert _error_code(response) == "6001"


@pytest.mark.unit
def test_acs_relay_is_single_use(setup, keys):
    relay, request_id = _start(Client())
    assert _error_code(_post_acs(Client(HTTP_USER_AGENT="pytest"), keys, relay, request_id)) is None
    assert _error_code(_post_acs(Client(), keys, relay, request_id)) == "6001"


@pytest.mark.unit
def test_acs_rejects_bad_signature(setup, keys):
    relay, request_id = _start(Client())
    response = _post_acs(Client(), keys, relay, request_id, sign=False)
    assert _error_code(response) == "6001"
    assert Account.objects.filter(provider="sso-saml").count() == 0


@pytest.fixture
def https_acs(setup):
    row = InstanceConfiguration.objects.get(key=config_key("saml", "CALLBACK_URL"))
    row.value = "https://plane.example.com/auth/sso/saml/acs/"
    row.save()


@pytest.mark.unit
def test_https_flow_binds_relay_to_the_starting_browser(https_acs, keys):
    browser = Client(HTTP_USER_AGENT="pytest")
    relay, request_id = _start(browser)
    cookie = browser.cookies["ee_sso_saml_bind"]
    assert cookie["samesite"] == "None" and cookie["secure"]
    assert _error_code(_post_acs(browser, keys, relay, request_id)) is None


@pytest.mark.unit
def test_login_csrf_response_posted_from_another_browser_is_rejected(https_acs, keys):
    relay, request_id = _start(Client())  # attacker starts the flow ...
    victim = Client(HTTP_USER_AGENT="pytest")  # ... victim's browser posts it without the bind cookie
    assert _error_code(_post_acs(victim, keys, relay, request_id)) == "6001"
    assert Account.objects.filter(provider="sso-saml").count() == 0
