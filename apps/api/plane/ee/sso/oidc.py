# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from functools import lru_cache

import jwt
import requests
from django.core.cache import cache

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.ee.sso import errors  # noqa: F401  (ensures codes are registered)

ALLOWED_ALGS = ["RS256", "ES256"]
DISCOVERY_TTL = 60 * 60


def _provider_error(message):
    return AuthenticationException(
        error_code=AUTHENTICATION_ERROR_CODES["SSO_PROVIDER_ERROR"],
        error_message=f"SSO_PROVIDER_ERROR: {message}",
    )


def _fetch_json(url):
    # Single patch point for tests (patching requests.get itself would also mock the core adapter's calls).
    # ponytail: admin-configured URL, not SSRF-guarded (internal IdPs are legitimate); see Known limits.
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()


def discover(issuer):
    base = issuer.rstrip("/")
    cache_key = f"ee_sso_discovery:{base}"
    meta = cache.get(cache_key)
    if meta:
        return meta
    try:
        meta = _fetch_json(f"{base}/.well-known/openid-configuration")
    except (requests.RequestException, ValueError):
        raise _provider_error("discovery failed")
    # OIDC Discovery §4.3: issuer in metadata must match the one used to fetch it. Some IdPs (Auth0) publish
    # it with a trailing slash, so compare ignoring that one character; callers must then verify tokens
    # against meta["issuer"] verbatim.
    if str(meta.get("issuer", "")).rstrip("/") != base:
        raise _provider_error("issuer mismatch")
    cache.set(cache_key, meta, DISCOVERY_TTL)
    return meta


@lru_cache(maxsize=16)
def _jwk_client(jwks_uri):
    return jwt.PyJWKClient(jwks_uri, timeout=10)  # keeps its own key cache


def _signing_key(jwks_uri, id_token):
    return _jwk_client(jwks_uri).get_signing_key_from_jwt(id_token).key


def verify_id_token(id_token, jwks_uri, issuer, audience, nonce):
    try:
        claims = jwt.decode(
            id_token,
            _signing_key(jwks_uri, id_token),
            algorithms=ALLOWED_ALGS,
            audience=audience,
            issuer=issuer,
            leeway=60,  # clock skew
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError:
        raise _provider_error("invalid id_token")
    if not nonce or claims.get("nonce") != nonce:
        raise _provider_error("nonce mismatch")
    # OIDC Core 3.1.3.7: with several audiences the authorized party (azp) must be this client
    if isinstance(claims.get("aud"), list) and len(claims["aud"]) > 1 and claims.get("azp") != audience:
        raise _provider_error("azp mismatch")
    return claims
