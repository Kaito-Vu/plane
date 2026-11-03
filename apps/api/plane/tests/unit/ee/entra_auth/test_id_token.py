import time
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from plane.ee.entra_auth.id_token import IdTokenError, get_signing_key, verify_id_token

TENANT = "tenant-1"
ISS = f"https://login.microsoftonline.com/{TENANT}/v2.0"
AUD = "client-1"
NONCE = "nonce-1"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def claims(**over):
    now = int(time.time())
    c = {"exp": now + 300, "iat": now, "iss": ISS, "aud": AUD, "sub": "s", "oid": "o", "tid": TENANT, "nonce": NONCE}
    c.update(over)
    return {k: v for k, v in c.items() if v is not None}


def sign(c, key=KEY, alg="RS256"):
    return jwt.encode(c, key, algorithm=alg)


def verify(token):
    return verify_id_token(
        token, signing_key=KEY.public_key(), issuer=ISS, client_id=AUD, tenant_id=TENANT, nonce=NONCE
    )


def test_valid_token_returns_claims():
    assert verify(sign(claims()))["oid"] == "o"


@pytest.mark.parametrize(
    "over",
    [
        {"iss": "https://evil/v2.0"},
        {"aud": "other"},
        {"tid": "other-tenant"},
        {"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200},
        {"nonce": "wrong"},
        {"nonce": None},
        {"nonce": 123},
        {"oid": None},
        {"sub": None},
        {"tid": None},
        {"tid": "\ud800"},
        {"nonce": "\ud800"},
    ],
)
def test_bad_claims_rejected(over):
    with pytest.raises(IdTokenError):
        verify(sign(claims(**over)))


def test_hs256_rejected():
    with pytest.raises(IdTokenError):
        verify(sign(claims(), key="a-secret-that-is-long-enough-for-hs256", alg="HS256"))


def test_alg_none_rejected():
    with pytest.raises(IdTokenError):
        verify(sign(claims(), key=None, alg="none"))


def test_wrong_signing_key_rejected():
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(IdTokenError):
        verify(sign(claims(), key=other))


def test_garbage_rejected():
    with pytest.raises(IdTokenError):
        verify("not-a-jwt")


def _verify_with(token, **kw):
    args = dict(signing_key=KEY.public_key(), issuer=ISS, client_id=AUD, tenant_id=TENANT, nonce=NONCE)
    args.update(kw)
    return verify_id_token(token, **args)


@pytest.mark.parametrize(
    "kw,over",
    [
        ({"tenant_id": ""}, {"tid": ""}),
        ({"nonce": ""}, {"nonce": ""}),
        ({"tenant_id": None}, {}),
        ({"nonce": None}, {}),
    ],
)
def test_empty_or_none_expected_rejected(kw, over):
    with pytest.raises(IdTokenError):
        _verify_with(sign(claims(**over)), **kw)


def test_get_signing_key_reuses_client_and_returns_key():
    import plane.ee.entra_auth.id_token as m

    m._client.cache_clear()
    with patch.object(m.jwt, "PyJWKClient") as cls:
        cls.return_value.get_signing_key_from_jwt.return_value = MagicMock(key="K")
        assert get_signing_key("t", "https://a/jwks") == "K"
        assert get_signing_key("t2", "https://a/jwks") == "K"
        get_signing_key("t", "https://b/jwks")
    assert cls.call_count == 2
    cls.assert_any_call("https://a/jwks", cache_keys=False, cache_jwk_set=True, lifespan=3600, timeout=3)
    m._client.cache_clear()
