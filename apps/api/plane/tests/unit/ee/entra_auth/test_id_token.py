import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from plane.ee.entra_auth.id_token import IdTokenError, verify_id_token

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
