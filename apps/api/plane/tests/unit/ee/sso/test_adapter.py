# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from urllib.parse import parse_qs, urlparse

import pytest
from django.test import RequestFactory

from plane.authentication.adapter.error import AuthenticationException
from plane.db.models import Account, User
from plane.ee.sso.adapter import SsoOauthProvider
from plane.ee.sso.config import PROVIDERS, config_key, seed_config
from plane.ee.sso.identity import issuer_fingerprint, placeholder_email, subject_key
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import encrypt_data

ISS = "https://idp.example.com"
META = {
    "issuer": ISS,
    "authorization_endpoint": f"{ISS}/authorize",
    "token_endpoint": f"{ISS}/token",
    "userinfo_endpoint": f"{ISS}/userinfo",
    "jwks_uri": f"{ISS}/jwks",
}
GUID = "11111111-1111-1111-1111-111111111111"
OTHER_GUID = "22222222-2222-2222-2222-222222222222"
OAUTH2_CFG = {
    "AUTH_URL": "https://o.example.com/auth",
    "TOKEN_URL": "https://o.example.com/token",
    "USERINFO_URL": "https://o.example.com/me",
}


def _configure(provider, **fields):
    seed_config()
    fields = {"ENABLED": "1", "CLIENT_ID": "cid", "CLIENT_SECRET": "sek", **fields}
    for field, value in fields.items():
        row = InstanceConfiguration.objects.get(key=config_key(provider, field))
        row.value = encrypt_data(value) if field == "CLIENT_SECRET" else value
        row.save()


def _request():
    request = RequestFactory().get("/auth/sso/oidc/callback/")
    request.session = {}
    request.META["HTTP_USER_AGENT"] = "pytest"
    return request


def _token_response(mocker, id_token):
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at", "id_token": id_token}
    return post


def _auth(provider_id):
    return SsoOauthProvider(_request(), provider_id, code="c", nonce="n1", code_verifier="v").authenticate()


@pytest.fixture
def oidc(db, mocker):
    _configure("oidc", ISSUER=ISS)
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value=META)


def _azure(mocker, **cfg):
    iss = cfg.pop("iss", f"https://login.microsoftonline.com/{GUID}/v2.0")
    _configure("azure_ad", TENANT_ID=GUID, **cfg)
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={**META, "issuer": iss})
    return iss


@pytest.mark.unit
def test_not_configured_raises(db):
    seed_config()
    with pytest.raises(AuthenticationException) as exc:
        SsoOauthProvider(_request(), "oidc")
    assert exc.value.error_code == 6000


@pytest.mark.unit
def test_auth_url_has_pkce_nonce_state_and_no_email_scope(oidc):
    p = SsoOauthProvider(_request(), "oidc", state="s1", nonce="n1", code_challenge="ch")
    q = parse_qs(urlparse(p.get_auth_url()).query)
    assert q["state"] == ["s1"] and q["nonce"] == ["n1"]
    assert q["code_challenge"] == ["ch"] and q["code_challenge_method"] == ["S256"]
    assert q["client_id"] == ["cid"] and q["response_type"] == ["code"]
    assert q["scope"] == ["openid profile"]  # least privilege: we never ask for e-mail


@pytest.mark.unit
def test_custom_callback_url_is_used_everywhere(db, mocker, make_id_token):
    custom = "https://sso.corp.com/auth/sso/oidc/callback/"
    _configure("oidc", ISSUER=ISS, CALLBACK_URL=custom)
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value=META)
    p = SsoOauthProvider(_request(), "oidc", state="s1", nonce="n1", code_challenge="ch")
    assert parse_qs(urlparse(p.get_auth_url()).query)["redirect_uri"] == [custom]
    post = _token_response(mocker, make_id_token())
    _auth("oidc")
    assert post.call_args.kwargs["data"]["redirect_uri"] == custom


@pytest.mark.unit
def test_saml_provider_id_is_rejected_by_oauth_adapter(db):
    if "saml" not in PROVIDERS:
        pytest.skip("saml added in phase 2")
    with pytest.raises(AuthenticationException) as exc:
        SsoOauthProvider(_request(), "saml")
    assert exc.value.error_code == 6000


@pytest.mark.unit
def test_oidc_identity_is_issuer_plus_sub_and_email_claims_are_ignored(oidc, mocker, make_id_token):
    _token_response(mocker, make_id_token(name="An Nguyen", email="a@b.com", email_verified=False))
    user = _auth("oidc")
    key = f"{issuer_fingerprint(ISS)}:u1"
    assert Account.objects.get(user=user).provider_account_id == key
    assert Account.objects.get(user=user).provider == "sso-oidc"
    assert user.email == placeholder_email("sso-oidc", key)
    assert (user.first_name, user.last_name) == ("An", "Nguyen")
    assert not User.objects.filter(email="a@b.com").exists()


@pytest.mark.unit
def test_existing_plane_user_with_the_same_email_is_never_taken_over(oidc, mocker, make_id_token):
    victim = User.objects.create(email="a@b.com", username="victim")
    _token_response(mocker, make_id_token(email="a@b.com", email_verified=True))
    user = _auth("oidc")
    assert user.id != victim.id
    assert not Account.objects.filter(user=victim).exists()


@pytest.mark.unit
def test_same_subject_logs_into_the_same_user_and_other_subject_does_not(oidc, mocker, make_id_token):
    _token_response(mocker, make_id_token(sub="s1"))
    first = _auth("oidc")
    _token_response(mocker, make_id_token(sub="s1", email="changed@b.com"))
    assert _auth("oidc").id == first.id
    _token_response(mocker, make_id_token(sub="s2"))
    assert _auth("oidc").id != first.id


@pytest.mark.unit
def test_missing_id_token_rejected(oidc, mocker):
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    with pytest.raises(AuthenticationException):
        _auth("oidc")


@pytest.mark.unit
def test_azure_identity_is_tid_plus_oid_and_never_calls_userinfo(db, mocker, make_id_token):
    iss = _azure(mocker)
    get = mocker.patch("plane.authentication.adapter.oauth.requests.get")
    _token_response(
        mocker, make_id_token(iss=iss, tid=GUID, oid="OID-1", preferred_username="an@corp.com", name="An Nguyen")
    )
    user = _auth("azure_ad")
    assert Account.objects.get(user=user).provider == "sso-azure_ad"
    assert Account.objects.get(user=user).provider_account_id == f"{GUID}:oid-1"
    assert user.email.endswith("@sso.invalid")  # UPN is display data only, never the e-mail
    get.assert_not_called()


@pytest.mark.unit
def test_azure_upn_change_does_not_change_the_account(db, mocker, make_id_token):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="o1", preferred_username="old@corp.com"))
    first = _auth("azure_ad")
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="o1", preferred_username="renamed@corp.com"))
    assert _auth("azure_ad").id == first.id


@pytest.mark.unit
def test_azure_reassigned_upn_with_a_new_oid_is_a_different_user(db, mocker, make_id_token):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="leaver", preferred_username="an@corp.com"))
    leaver = _auth("azure_ad")
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="newhire", preferred_username="an@corp.com"))
    assert _auth("azure_ad").id != leaver.id


@pytest.mark.unit
@pytest.mark.parametrize("claims", [{"tid": OTHER_GUID, "oid": "o"}, {"tid": GUID}, {"oid": "o"}])
def test_azure_requires_matching_tid_and_an_oid(db, mocker, make_id_token, claims):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, **claims))
    with pytest.raises(AuthenticationException) as exc:
        _auth("azure_ad")
    assert exc.value.error_code == 6001


@pytest.mark.unit
@pytest.mark.parametrize(
    "extra",
    [
        {"acct": 1},
        {"idp": "https://sts.example.com/"},
        {"preferred_username": "bob_partner.com#EXT#@corp.onmicrosoft.com"},
    ],
)
def test_azure_guest_signals_are_rejected(db, mocker, make_id_token, extra):
    iss = _azure(mocker)
    _token_response(mocker, make_id_token(iss=iss, tid=GUID, oid="o", **extra))
    with pytest.raises(AuthenticationException) as exc:
        _auth("azure_ad")
    assert exc.value.error_code == 6001


@pytest.mark.unit
def test_azure_uppercase_tenant_guid_is_normalised_for_discovery(db, mocker):
    _configure("azure_ad", TENANT_ID=GUID.upper())
    lower_iss = f"https://login.microsoftonline.com/{GUID}/v2.0"
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={**META, "issuer": lower_iss})
    assert SsoOauthProvider(_request(), "azure_ad", state="s", nonce="n", code_challenge="c").issuer == lower_iss


@pytest.mark.unit
def test_azure_issuer_override_is_used_for_discovery(db, mocker):
    override = "https://login.microsoftonline.com/custom/v2.0"
    iss = _azure(mocker, ISSUER=override, iss=override)
    p = SsoOauthProvider(_request(), "azure_ad", state="s", nonce="n", code_challenge="c")
    assert p.issuer == iss and p.token_issuer == iss


@pytest.mark.unit
def test_oauth2_identity_is_the_userinfo_id(db, mocker):
    _configure("oauth2", **OAUTH2_CFG)
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    get = mocker.patch("plane.authentication.adapter.oauth.requests.get")
    get.return_value.json.return_value = {"id": 42, "name": "Bao Tran"}
    user = SsoOauthProvider(_request(), "oauth2", code="c").authenticate()
    assert (user.first_name, user.last_name) == ("Bao", "Tran")
    assert Account.objects.get(user=user).provider_account_id == subject_key("https://o.example.com/token", "42")


@pytest.mark.unit
def test_oauth2_without_a_stable_id_is_rejected(db, mocker):
    _configure("oauth2", **OAUTH2_CFG)
    post = mocker.patch("plane.authentication.adapter.oauth.requests.post")
    post.return_value.json.return_value = {"access_token": "at"}
    mocker.patch("plane.authentication.adapter.oauth.requests.get").return_value.json.return_value = {"name": "x"}
    with pytest.raises(AuthenticationException):
        SsoOauthProvider(_request(), "oauth2", code="c").authenticate()
