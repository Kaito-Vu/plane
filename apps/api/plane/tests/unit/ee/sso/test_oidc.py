# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.authentication.adapter.error import AuthenticationException
from plane.ee.sso.oidc import discover, verify_id_token

ISS = "https://idp.example.com"


def _verify(token, **kw):
    args = {"jwks_uri": f"{ISS}/jwks", "issuer": ISS, "audience": "cid", "nonce": "n1"}
    args.update(kw)
    return verify_id_token(token, **args)


@pytest.mark.unit
def test_valid_token_returns_claims(make_id_token):
    assert _verify(make_id_token())["email"] == "a@b.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "override, kw",
    [
        ({"exp": 1}, {}),  # expired
        ({"aud": "other"}, {}),  # wrong audience
        ({"iss": "https://evil.example.com"}, {}),  # wrong issuer
        ({"nonce": "zzz"}, {}),  # nonce mismatch
        ({"nonce": None}, {}),  # nonce missing
        ({"aud": ["cid", "other"], "azp": "other"}, {}),  # multi-audience token for another authorized party
    ],
)
def test_invalid_claims_rejected(make_id_token, override, kw):
    with pytest.raises(AuthenticationException):
        _verify(make_id_token(**override), **kw)


@pytest.mark.unit
def test_garbage_token_rejected():
    with pytest.raises(AuthenticationException):
        _verify("not.a.jwt")


@pytest.mark.unit
def test_discover_ok_and_cached(mocker):
    fetch = mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={"issuer": ISS, "jwks_uri": f"{ISS}/jwks"})
    assert discover(ISS)["jwks_uri"] == f"{ISS}/jwks"
    discover(ISS)
    assert fetch.call_count == 1


@pytest.mark.unit
def test_discover_accepts_trailing_slash_issuer(mocker, make_id_token):
    fetch = mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={"issuer": ISS + "/", "jwks_uri": "x"})
    meta = discover(ISS)  # configured without slash
    assert fetch.call_args.args[0] == f"{ISS}/.well-known/openid-configuration"
    # tokens are then verified against the verbatim issuer
    assert _verify(make_id_token(iss=ISS + "/"), issuer=meta["issuer"])["sub"] == "u1"


@pytest.mark.unit
def test_discover_issuer_mismatch_rejected(mocker):
    mocker.patch("plane.ee.sso.oidc._fetch_json", return_value={"issuer": "https://other", "jwks_uri": "x"})
    with pytest.raises(AuthenticationException):
        discover(ISS)
