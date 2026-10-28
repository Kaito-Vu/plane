import base64
import hashlib
import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
import requests
from cryptography.hazmat.primitives.asymmetric import rsa

from plane.authentication.adapter.error import AuthenticationException
from plane.ee.entra_auth.entra import EntraProvider
from plane.ee.entra_auth.oidc import SESSION_NONCE, SESSION_VERIFIER

TENANT = "11111111-2222-3333-4444-555555555555"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"
CID = "client-1"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
DISCOVERY = {
    "issuer": ISS,
    "authorization_endpoint": "https://login.microsoftonline.com/t/oauth2/v2.0/authorize",
    "token_endpoint": "https://login.microsoftonline.com/t/oauth2/v2.0/token",
    "jwks_uri": "https://login.microsoftonline.com/t/discovery/v2.0/keys",
}


class FakeCache(dict):
    def set(self, k, v, ttl=None):
        self[k] = v


@pytest.fixture(autouse=True)
def env():
    cfg = {
        "ENTRA_TENANT_ID": TENANT,
        "ENTRA_CLIENT_ID": CID,
        "ENTRA_CLIENT_SECRET": "sec",
        "ENTRA_ALLOWED_EMAIL_DOMAINS": "",
    }
    state = {"cfg": cfg, "get": MagicMock(), "post": MagicMock(), "cache": FakeCache()}
    state["get"].return_value = MagicMock(json=lambda: dict(DISCOVERY), raise_for_status=lambda: None)

    def gcv(items):
        return tuple(state["cfg"].get(i["key"]) for i in items)

    with (
        patch("plane.ee.entra_auth.entra.get_configuration_value", gcv),
        patch("plane.ee.entra_auth.oidc.requests.get", state["get"]),
        patch("plane.ee.entra_auth.oidc.requests.post", state["post"]),
        patch("plane.ee.entra_auth.oidc.cache", state["cache"]),  # fresh per test: no cache leakage
        patch("plane.ee.entra_auth.oidc.get_signing_key", lambda t, u: KEY.public_key()),
    ):
        yield state


def req(session=None):
    r = MagicMock()
    r.is_secure.return_value = True
    r.get_host.return_value = "plane.example.com"
    r.session = {} if session is None else session
    return r


def token(**over):
    now = int(time.time())
    c = {
        "exp": now + 300,
        "iat": now,
        "iss": ISS,
        "aud": CID,
        "sub": "s",
        "oid": "oid-1",
        "tid": TENANT,
        "nonce": "N",
        "email": "A@B.com",
        "name": "Ann",
    }
    c.update(over)
    return jwt.encode({k: v for k, v in c.items() if v is not None}, KEY, algorithm="RS256")


def token_resp(env, body):
    env["post"].return_value = MagicMock(json=lambda: body, raise_for_status=lambda: None)


def code_of(fn):
    with pytest.raises(AuthenticationException) as e:
        fn()
    return e.value.error_message


def callback_session():
    return {SESSION_NONCE: "N", SESSION_VERIFIER: "V"}


@pytest.mark.parametrize(
    "over",
    [
        {"ENTRA_TENANT_ID": None},
        {"ENTRA_CLIENT_ID": ""},
        {"ENTRA_CLIENT_SECRET": None},
        {"ENTRA_TENANT_ID": "not-a-guid"},
    ],
)
def test_not_configured(env, over):
    env["cfg"].update(over)
    assert code_of(lambda: EntraProvider(req(), state="s")) == "ENTRA_NOT_CONFIGURED"


def test_uppercase_tenant_is_normalised(env):
    env["cfg"]["ENTRA_TENANT_ID"] = f"  {TENANT.upper()} "
    p = EntraProvider(req(), state="s")
    assert p.issuer == ISS and p.tenant_id == TENANT
    assert p.get_auth_url()  # discovery issuer check passes
    env["cfg"]["ENTRA_TENANT_ID"] = "NOT-A-GUID"
    assert code_of(lambda: EntraProvider(req(), state="s")) == "ENTRA_NOT_CONFIGURED"


def test_initiate_url_and_session(env):
    r = req()
    url = EntraProvider(r, state="st").get_auth_url()
    q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    assert url.startswith(DISCOVERY["authorization_endpoint"] + "?")
    assert q["client_id"] == CID and q["state"] == "st"
    assert q["redirect_uri"] == "https://plane.example.com/auth/entra/callback"
    assert q["scope"] == "openid email profile User.Read"
    assert q["response_type"] == "code" and q["response_mode"] == "query"
    assert q["code_challenge_method"] == "S256" and q["nonce"] == r.session[SESSION_NONCE]
    digest = hashlib.sha256(r.session[SESSION_VERIFIER].encode()).digest()
    assert q["code_challenge"] == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def test_discovery_issuer_mismatch(env):
    env["get"].return_value = MagicMock(
        json=lambda: {**DISCOVERY, "issuer": "https://evil/v2.0"}, raise_for_status=lambda: None
    )
    assert code_of(lambda: EntraProvider(req(), state="s").get_auth_url()) == "ENTRA_PROVIDER_ERROR"


def test_discovery_jwks_host_pinned(env):
    env["get"].return_value = MagicMock(
        json=lambda: {**DISCOVERY, "jwks_uri": "https://evil.example/keys"}, raise_for_status=lambda: None
    )
    assert code_of(lambda: EntraProvider(req(), state="s").get_auth_url()) == "ENTRA_PROVIDER_ERROR"


def test_discovery_jwks_host_valid(env):
    assert EntraProvider(req(), state="s").get_auth_url()


@pytest.mark.parametrize("state", [None, ""])
def test_auth_url_requires_state(env, state):
    assert code_of(lambda: EntraProvider(req(), state=state).get_auth_url()) == "ENTRA_PROVIDER_ERROR"


def test_auth_url_has_no_client_secret(env):
    url = EntraProvider(req(), state="st").get_auth_url()
    assert "client_secret" not in url and "sec" not in parse_qs(urlparse(url).query).get("client_secret", [])


def test_discovery_network_error(env):
    env["get"].side_effect = requests.ConnectionError()
    assert code_of(lambda: EntraProvider(req(), state="s").get_auth_url()) == "ENTRA_PROVIDER_ERROR"


def test_discovery_cached(env):
    EntraProvider(req(), state="s").get_auth_url()
    EntraProvider(req(), state="s").get_auth_url()
    assert env["get"].call_count == 1
    assert env["get"].call_args.kwargs["timeout"]


@pytest.mark.parametrize("missing", [SESSION_NONCE, SESSION_VERIFIER])
def test_callback_missing_session(env, missing):
    s = callback_session()
    del s[missing]
    token_resp(env, {"id_token": token()})
    assert code_of(lambda: EntraProvider(req(s), code="c").set_token_data()) == "ENTRA_PROVIDER_ERROR"
    env["post"].assert_not_called()


def test_replay_fails_second_time(env):
    s = callback_session()
    token_resp(env, {"id_token": token()})
    p = EntraProvider(req(s), code="c")
    p.set_token_data()
    p.set_user_data()
    assert code_of(lambda: EntraProvider(req(s), code="c").set_token_data()) == "ENTRA_PROVIDER_ERROR"


@pytest.mark.parametrize("body", [{}, {"id_token": "garbage"}, {"id_token": ""}])
def test_bad_or_missing_id_token(env, body):
    token_resp(env, body)
    p = EntraProvider(req(callback_session()), code="c")
    p.set_token_data()
    assert code_of(p.set_user_data) == "ENTRA_PROVIDER_ERROR"


def test_wrong_nonce_rejected(env):
    token_resp(env, {"id_token": token(nonce="other")})
    p = EntraProvider(req(callback_session()), code="c")
    p.set_token_data()
    assert code_of(p.set_user_data) == "ENTRA_PROVIDER_ERROR"


def test_signing_key_lookup_error_is_provider_error(env):
    token_resp(env, {"id_token": token()})
    p = EntraProvider(req(callback_session()), code="c")
    p.set_token_data()
    with patch("plane.ee.entra_auth.oidc.get_signing_key", side_effect=OSError("boom")):
        assert code_of(p.set_user_data) == "ENTRA_PROVIDER_ERROR"


def test_token_request_contents_and_user_data(env):
    token_resp(env, {"id_token": token(), "access_token": "at"})
    p = EntraProvider(req(callback_session()), code="c")
    p.set_token_data()
    p.set_user_data()
    kw = env["post"].call_args.kwargs
    assert kw["data"]["code_verifier"] == "V" and kw["data"]["client_secret"] == "sec"
    assert kw["data"]["redirect_uri"] == "https://plane.example.com/auth/entra/callback"
    assert kw["timeout"]
    assert p.token_data["access_token_expired_at"] is None
    assert p.user_data["email"] == "a@b.com" and p.user_data["user"]["provider_id"] == "oid-1"


def test_allowed_domains_enforced(env):
    env["cfg"]["ENTRA_ALLOWED_EMAIL_DOMAINS"] = " Other.com "
    token_resp(env, {"id_token": token()})
    p = EntraProvider(req(callback_session()), code="c")
    p.set_token_data()
    assert code_of(p.set_user_data) == "ENTRA_EMAIL_UNUSABLE"


def test_token_endpoint_error_maps_to_provider_error(env):
    env["post"].side_effect = requests.ConnectionError()
    assert code_of(lambda: EntraProvider(req(callback_session()), code="c").set_token_data()) == "ENTRA_PROVIDER_ERROR"
