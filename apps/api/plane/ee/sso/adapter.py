# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import datetime, timedelta
from urllib.parse import urlencode

import pytz

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.adapter.oauth import OauthAdapter
from plane.ee.sso import errors  # noqa: F401
from plane.ee.sso.config import PROVIDERS, callback_url, get_sso_config
from plane.ee.sso.identity import SubjectLoginMixin, subject_key
from plane.ee.sso.oidc import discover, verify_id_token

AZURE_ISSUER = "https://login.microsoftonline.com/{tenant}/v2.0"


def _error(code, message=None):
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[code], error_message=message or code)


class SsoOauthProvider(SubjectLoginMixin, OauthAdapter):
    def __init__(
        self,
        request,
        provider_id,
        state=None,
        nonce=None,
        code_challenge=None,
        code=None,
        code_verifier=None,
        callback=None,
    ):
        cfg = get_sso_config(provider_id)
        if not cfg or PROVIDERS[provider_id]["protocol"] not in ("oidc", "oauth2"):
            raise _error("SSO_NOT_CONFIGURED")
        self.provider_id = provider_id
        self.cfg = cfg
        self.nonce = nonce
        self.code_verifier = code_verifier
        self.id_claims = {}
        self.issuer = self._issuer(provider_id, cfg)
        if self.issuer:
            meta = discover(self.issuer)
            # token `iss` must equal the discovery document's issuer string exactly (may end in "/")
            self.token_issuer = meta["issuer"]
            auth_url = meta.get("authorization_endpoint")
            token_url = meta.get("token_endpoint")
            userinfo_url = meta.get("userinfo_endpoint")
            self.jwks_uri = meta.get("jwks_uri")
            if not (auth_url and token_url and self.jwks_uri):
                raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: incomplete discovery document")
        else:
            auth_url, token_url, userinfo_url = cfg["AUTH_URL"], cfg["TOKEN_URL"], cfg["USERINFO_URL"]

        redirect_uri = callback_url(request, provider_id, cfg)
        params = {
            "client_id": cfg["CLIENT_ID"],
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": cfg["SCOPE"],
            "state": state,
        }
        if self.issuer:
            params.update({"nonce": nonce, "code_challenge": code_challenge, "code_challenge_method": "S256"})
        params = {k: v for k, v in params.items() if v}
        super().__init__(
            request,
            f"sso-{provider_id}",
            cfg["CLIENT_ID"],
            cfg["SCOPE"],
            redirect_uri,
            f"{auth_url}{'&' if '?' in auth_url else '?'}{urlencode(params)}",
            token_url,
            userinfo_url,
            cfg["CLIENT_SECRET"],
            code,
            callback=callback,
        )

    @staticmethod
    def _issuer(provider_id, cfg):
        if provider_id == "oidc":
            return cfg["ISSUER"].strip().rstrip("/")
        if provider_id == "azure_ad":
            # single tenant, v2.0 endpoint; ISSUER is an optional override (must also be a v2.0 issuer)
            tenant_issuer = AZURE_ISSUER.format(tenant=cfg["TENANT_ID"].strip().lower())
            return (cfg.get("ISSUER") or tenant_issuer).strip().rstrip("/")
        return None

    def authentication_error_code(self):
        return "SSO_PROVIDER_ERROR"

    def set_token_data(self):
        data = {
            "code": self.code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        if self.issuer:
            data["code_verifier"] = self.code_verifier
        token = self.get_user_token(data=data, headers={"Accept": "application/json"})
        if not token.get("access_token") and not token.get("id_token"):
            raise _error("SSO_PROVIDER_ERROR")
        if self.issuer:
            if not token.get("id_token"):
                raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: id_token missing")
            self.id_claims = verify_id_token(
                token["id_token"], self.jwks_uri, self.token_issuer, self.client_id, self.nonce
            )
        expires_in = token.get("expires_in")
        super().set_token_data(
            {
                "access_token": token.get("access_token", ""),
                "refresh_token": token.get("refresh_token"),
                "access_token_expired_at": (
                    datetime.now(tz=pytz.utc) + timedelta(seconds=int(expires_in)) if expires_in else None
                ),
                "refresh_token_expired_at": None,
                "id_token": token.get("id_token", ""),
            }
        )

    def _azure_subject(self, claims):
        """Entra best practice: identify by `oid` within the tenant `tid` (sub is per-app; UPN/e-mail are mutable)."""
        tenant = self.cfg["TENANT_ID"].strip().lower()  # get_sso_config guarantees a GUID
        if str(claims.get("tid", "")).lower() != tenant:
            raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: tenant mismatch")
        oid = str(claims.get("oid") or "").strip().lower()
        if not oid:
            raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: oid missing")
        # B2B guests: federated from another IdP (idp != iss), acct == 1, or a `#EXT#` UPN when one is present
        if (
            (claims.get("idp") and claims.get("idp") != claims.get("iss"))
            or str(claims.get("acct")) == "1"
            or "#EXT#" in str(claims.get("preferred_username") or "").upper()
        ):
            raise _error("SSO_PROVIDER_ERROR", "SSO_PROVIDER_ERROR: guest accounts are not allowed")
        return f"{tenant}:{oid}"

    def set_user_data(self):
        claims = self.id_claims if self.issuer else self.get_user_response()  # OIDC: the verified id_token
        if self.provider_id == "azure_ad":
            key = self._azure_subject(claims)
        elif self.issuer:
            key = subject_key(self.token_issuer, claims.get("sub"))
        else:
            key = subject_key(self.token_url, claims.get("sub") or claims.get("id"))
        first = claims.get("given_name") or claims.get("first_name")
        last = claims.get("family_name") or claims.get("last_name")
        if not (first or last) and claims.get("name"):
            first, _, last = str(claims["name"]).partition(" ")
        self.subject_key = key
        self.profile = {
            "first_name": first,
            "last_name": last,
            "display_name": claims.get("name") or claims.get("preferred_username"),  # display only
        }

    def authenticate(self):
        self.set_token_data()
        self.set_user_data()
        return self.login_by_subject(self.subject_key, self.profile, self.cfg["ALLOW_SIGNUP"])
