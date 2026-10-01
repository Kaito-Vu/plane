# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

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
    cache.delete_pattern("ee_sso_*")
    Instance.objects.create(
        instance_name="t", instance_id="i", current_version="1", last_checked_at=timezone.now(), is_setup_done=True
    )
    seed_config()
    for field, value in {"ENABLED": "1", "CLIENT_ID": "cid", "CLIENT_SECRET": "sek", "ISSUER": ISS}.items():
        row = InstanceConfiguration.objects.get(key=config_key("oidc", field))
        row.value = encrypt_data(value) if field == "CLIENT_SECRET" else value
        row.save()
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value=META)


def _run(client, start_path, mocker, make_id_token):
    q = parse_qs(urlparse(client.get(start_path)["Location"]).query)
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {
        "access_token": "at",
        "id_token": make_id_token(nonce=q["nonce"][0], sub="sp-user"),
    }
    return client.get(f"/auth/sso/oidc/callback/?code=c&state={q['state'][0]}")


@pytest.mark.unit
def test_space_initiate_logs_in_as_space_user(setup, mocker, make_id_token):
    spy = mocker.patch("plane.ee.sso.flow.user_login")
    response = _run(Client(HTTP_USER_AGENT="pytest"), "/auth/sso/spaces/oidc/?next_path=/issues/abc", mocker, make_id_token)
    assert response.status_code == 302
    assert spy.call_args.kwargs["is_space"] is True
    assert "is_app" not in spy.call_args.kwargs
    assert response["Location"].endswith("/issues/abc")


@pytest.mark.unit
def test_app_initiate_still_logs_in_as_app_user(setup, mocker, make_id_token):
    spy = mocker.patch("plane.ee.sso.flow.user_login")
    _run(Client(HTTP_USER_AGENT="pytest"), "/auth/sso/oidc/", mocker, make_id_token)
    assert spy.call_args.kwargs["is_app"] is True


@pytest.mark.unit
def test_space_initiate_unknown_provider_redirects_with_error(setup):
    response = Client().get("/auth/sso/spaces/nope/")
    assert response.status_code == 302
    assert parse_qs(urlparse(response["Location"]).query)["error_code"] == ["6000"]
