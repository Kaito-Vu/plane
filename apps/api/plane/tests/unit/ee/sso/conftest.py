# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.cache import cache


@pytest.fixture(scope="session")
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    return private, key.public_key()


@pytest.fixture(autouse=True)
def _patch_jwks(mocker, rsa_keys):
    # delete only our keys (cache.clear() would flush the whole shared Redis DB); needs the compose Redis
    cache.delete_pattern("ee_sso_*")
    mocker.patch("plane.ee.sso.oidc._signing_key", return_value=rsa_keys[1])


@pytest.fixture
def make_id_token(rsa_keys):
    def _make(**override):
        claims = {
            "iss": "https://idp.example.com",
            "aud": "cid",
            "sub": "u1",
            "nonce": "n1",
            "email": "a@b.com",
            "exp": int(time.time()) + 300,
        }
        claims.update(override)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, rsa_keys[0], algorithm="RS256")

    return _make
