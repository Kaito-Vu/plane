# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.test import Client
from django.utils import timezone

from plane.db.models import Account
from plane.ee.sso.config import config_key, seed_config
from plane.license.models import Instance, InstanceConfiguration
from plane.license.utils.encryption import encrypt_data

ISS = "https://idp.example.com"
META = {
    "issuer": ISS,
    "authorization_endpoint": f"{ISS}/authorize",
    "token_endpoint": f"{ISS}/token",
    "jwks_uri": f"{ISS}/jwks",
}


@pytest.fixture
def setup(db, mocker):
    Instance.objects.create(
        instance_name="t",
        instance_id="i",
        current_version="1",
        last_checked_at=timezone.now(),
        is_setup_done=True,
    )
    seed_config()
    for field, value in {
        "ENABLED": "1",
        "LABEL": "ETC SSO",
        "CLIENT_ID": "cid",
        "CLIENT_SECRET": "sek",
        "ISSUER": ISS,
    }.items():
        row = InstanceConfiguration.objects.get(key=config_key("oidc", field))
        row.value = encrypt_data(value) if field == "CLIENT_SECRET" else value
        row.save()
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value=META)


def _error_code(response):
    return parse_qs(urlparse(response["Location"]).query).get("error_code", [None])[0]


@pytest.mark.unit
def test_providers_endpoint_lists_enabled(setup):
    response = Client().get("/auth/sso/providers/")
    assert response.status_code == 200
    assert response.json() == [{"id": "oidc", "label": "ETC SSO", "protocol": "oidc"}]


@pytest.mark.unit
def test_initiate_redirects_to_idp_with_pkce(setup):
    response = Client().get("/auth/sso/oidc/")
    assert response.status_code == 302
    location = urlparse(response["Location"])
    assert f"{location.scheme}://{location.netloc}{location.path}" == f"{ISS}/authorize"
    q = parse_qs(location.query)
    assert q["code_challenge_method"] == ["S256"] and q["state"] and q["nonce"]


@pytest.mark.unit
def test_initiate_unknown_provider_redirects_with_error(setup):
    response = Client().get("/auth/sso/nope/")
    assert response.status_code == 302 and _error_code(response) == "6000"


@pytest.mark.unit
def test_callback_rejects_state_mismatch(setup):
    client = Client(HTTP_USER_AGENT="pytest")  # core stores the UA on login (NOT NULL)
    client.get("/auth/sso/oidc/")
    response = client.get("/auth/sso/oidc/callback/?code=c&state=WRONG")
    assert _error_code(response) == "6001"


@pytest.mark.unit
def test_callback_success_logs_user_in(setup, mocker, make_id_token):
    client = Client(HTTP_USER_AGENT="pytest")  # core stores the UA on login (NOT NULL)
    q = parse_qs(urlparse(client.get("/auth/sso/oidc/")["Location"]).query)
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {
        "access_token": "at",
        "id_token": make_id_token(nonce=q["nonce"][0], email="new@corp.com"),
    }
    response = client.get(f"/auth/sso/oidc/callback/?code=c&state={q['state'][0]}")
    assert response.status_code == 302 and _error_code(response) is None
    assert Account.objects.filter(provider="sso-oidc").count() == 1
    # state is single-use
    again = client.get(f"/auth/sso/oidc/callback/?code=c&state={q['state'][0]}")
    assert _error_code(again) == "6001"


@pytest.mark.unit
def test_callback_must_finish_on_the_provider_that_started_the_flow(setup):
    client = Client(HTTP_USER_AGENT="pytest")
    state = parse_qs(urlparse(client.get("/auth/sso/oidc/")["Location"]).query)["state"][0]
    response = client.get(f"/auth/sso/azure_ad/callback/?code=c&state={state}")
    assert _error_code(response) == "6001"
