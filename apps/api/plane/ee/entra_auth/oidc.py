import base64
import hashlib
import secrets
from datetime import datetime, timedelta

import pytz
import requests
from django.core.cache import cache
from urllib.parse import urlencode, urlparse

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.adapter.oauth import OauthAdapter
from plane.ee.entra_auth.id_token import get_signing_key, verify_id_token

SESSION_NONCE = "entra_nonce"
SESSION_VERIFIER = "entra_code_verifier"
_TIMEOUT = 10
_DISCOVERY_TTL = 3600
_HOST = "login.microsoftonline.com"
# every endpoint we send secrets to or trust keys from must live on Microsoft's host
_ENDPOINTS = ("authorization_endpoint", "token_endpoint", "jwks_uri")


class OIDCProvider(OauthAdapter):
    def __init__(
        self,
        request,
        *,
        provider: str,
        issuer: str,
        client_id: str,
        client_secret: str,
        scope: str,
        redirect_uri: str,
        code: str | None = None,
        state: str | None = None,
        callback=None,
    ):
        # auth/token urls come from discovery, resolved lazily so __init__ does no network I/O
        super().__init__(
            request, provider, client_id, scope, redirect_uri, None, None, None, client_secret, code, callback=callback
        )
        self.issuer = issuer
        self.state = state
        self._discovery = None

    def _fail(self) -> AuthenticationException:
        name = self.authentication_error_code()
        return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[name], error_message=name)

    def get_discovery(self) -> dict:
        if self._discovery is not None:
            return self._discovery
        key = f"oidc:discovery:{self.issuer}"
        doc = cache.get(key)
        if doc is None:
            try:
                response = requests.get(f"{self.issuer}/.well-known/openid-configuration", timeout=_TIMEOUT)
                response.raise_for_status()
                doc = response.json()
            except (requests.RequestException, ValueError):
                self.logger.warning("OIDC discovery failed")
                raise self._fail()
            if (
                not isinstance(doc, dict)
                or doc.get("issuer") != self.issuer
                or not all(isinstance(doc.get(k), str) for k in ("authorization_endpoint", "token_endpoint", "jwks_uri"))
                or any(urlparse(doc[k]).hostname != _HOST for k in _ENDPOINTS)
            ):
                self.logger.warning("OIDC discovery document rejected")
                raise self._fail()
            cache.set(key, doc, _DISCOVERY_TTL)
        self._discovery = doc
        return doc

    def get_token_url(self):
        return self.get_discovery()["token_endpoint"]

    def get_auth_url(self):
        if not self.state:
            raise self._fail()
        discovery = self.get_discovery()
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        self.request.session[SESSION_NONCE] = nonce
        self.request.session[SESSION_VERIFIER] = verifier
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "response_mode": "query",
            "scope": self.scope,
            "redirect_uri": self.redirect_uri,
            "state": self.state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{discovery['authorization_endpoint']}?{urlencode(params)}"

    def get_user_token(self, data, headers=None):
        try:
            response = requests.post(self.get_token_url(), data=data, headers=headers or {}, timeout=_TIMEOUT)
            response.raise_for_status()
            body = response.json()
        except (requests.RequestException, ValueError):
            self.logger.warning("Error getting user token")
            raise self._fail()
        if not isinstance(body, dict):
            raise self._fail()
        return body

    def set_token_data(self):
        # pop (single use): a replayed callback finds no nonce/verifier and fails
        self.nonce = self.request.session.pop(SESSION_NONCE, None)
        verifier = self.request.session.pop(SESSION_VERIFIER, None)
        if not self.nonce or not verifier or not self.code:
            raise self._fail()
        body = self.get_user_token(
            data={
                "grant_type": "authorization_code",
                "code": self.code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
        expires_in = body.get("expires_in")
        try:
            expires_at = datetime.now(tz=pytz.utc) + timedelta(seconds=int(expires_in)) if expires_in else None
        except (TypeError, ValueError, OverflowError):
            expires_at = None
        super().set_token_data(
            {
                "access_token": body.get("access_token"),
                "refresh_token": body.get("refresh_token"),
                "access_token_expired_at": expires_at,
                "refresh_token_expired_at": None,
                "id_token": body.get("id_token") or "",
            }
        )

    def build_user_data(self, claims: dict) -> dict:
        raise NotImplementedError

    def set_user_data(self):
        id_token = self.token_data.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise self._fail()
        try:
            key = get_signing_key(id_token, self.get_discovery()["jwks_uri"])
            claims = verify_id_token(
                id_token,
                signing_key=key,
                issuer=self.issuer,
                client_id=self.client_id,
                tenant_id=self.tenant_id,
                nonce=self.nonce,
            )
        except Exception:  # any failure (network, JSON, bad token) is a provider error; never log the token
            self.logger.warning("id_token verification failed")
            raise self._fail()
        super().set_user_data(self.build_user_data(claims))
