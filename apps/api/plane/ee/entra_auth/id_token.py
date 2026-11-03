import secrets
from functools import lru_cache
from typing import Any

import jwt


class IdTokenError(Exception):
    pass


@lru_cache(maxsize=None)
def _client(jwks_uri: str) -> "jwt.PyJWKClient":
    # one client per jwks_uri so the key set is cached across logins; keys Microsoft removes expire with the set
    return jwt.PyJWKClient(jwks_uri, cache_keys=False, cache_jwk_set=True, lifespan=3600, timeout=3)


def get_signing_key(id_token: str, jwks_uri: str) -> Any:
    try:
        return _client(jwks_uri).get_signing_key_from_jwt(id_token).key
    except jwt.PyJWTError as e:
        raise IdTokenError(str(e)) from e


def _same(a: Any, b: str) -> bool:
    if not (isinstance(a, str) and isinstance(b, str) and b):
        return False
    # surrogatepass: a lone surrogate in a claim must not raise UnicodeEncodeError
    return secrets.compare_digest(a.encode("utf-8", "surrogatepass"), b.encode("utf-8", "surrogatepass"))


def verify_id_token(id_token: str, *, signing_key: Any, issuer: str, client_id: str, tenant_id: str, nonce: str) -> dict:
    try:
        claims = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],  # never trust the header alg (blocks HS256/none confusion)
            audience=client_id,
            issuer=issuer,
            leeway=60,  # tolerate 60s clock skew for exp/iat/nbf
            options={"require": ["exp", "iat", "iss", "aud", "sub", "oid", "tid"]},
        )
    except (jwt.PyJWTError, ValueError, TypeError) as e:
        raise IdTokenError(str(e)) from e
    if not _same(claims.get("tid"), tenant_id):
        raise IdTokenError("tid mismatch")
    if not _same(claims.get("nonce"), nonce):
        raise IdTokenError("nonce mismatch")
    for k in ("sub", "oid"):
        if not isinstance(claims[k], str):
            raise IdTokenError(f"invalid {k}")
    return claims
