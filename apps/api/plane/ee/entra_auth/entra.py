import os
import re

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.ee.entra_auth.oidc import OIDCProvider
from plane.db.models import User
from plane.ee.entra_auth.profile import GRAPH_PHOTO_URL, claims_to_user_data, parse_domains
from plane.license.utils.instance_value import get_configuration_value
from plane.utils.url_security import pinned_fetch

_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_KEYS = ("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_ALLOWED_EMAIL_DOMAINS")


class EntraProvider(OIDCProvider):
    provider = "entra"
    scope = "openid email profile User.Read"

    @staticmethod
    def build_issuer(tenant_id: str) -> str:
        return f"https://login.microsoftonline.com/{tenant_id}/v2.0"

    def __init__(self, request, code=None, state=None, callback=None):
        tenant_id, client_id, client_secret, domains = get_configuration_value(
            [{"key": k, "default": os.environ.get(k)} for k in _KEYS]
        )
        if not (tenant_id and client_id and client_secret and _GUID_RE.match(tenant_id)):
            raise AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ENTRA_NOT_CONFIGURED"],
                error_message="ENTRA_NOT_CONFIGURED",
            )
        self.tenant_id = tenant_id
        self.allowed_domains = parse_domains(domains)
        super().__init__(
            request,
            provider=self.provider,
            issuer=self.build_issuer(tenant_id),
            client_id=client_id,
            client_secret=client_secret,
            scope=self.scope,
            redirect_uri=f"{'https' if request.is_secure() else 'http'}://{request.get_host()}/auth/entra/callback",
            code=code,
            state=state,
            callback=callback,
        )

    def authentication_error_code(self) -> str:
        return "ENTRA_PROVIDER_ERROR"

    def build_user_data(self, claims: dict) -> dict:
        return claims_to_user_data(claims, self.allowed_domains)

    def fetch_avatar(self, avatar_url):
        # The bearer token must only ever reach Graph. allowed_hosts in url_security only skips the
        # private-IP check (it is NOT a host allowlist) and the redirect helper re-sends headers on
        # every hop, so: exact-URL match + single pinned request + never follow redirects.
        access_token = (self.token_data or {}).get("access_token")
        if avatar_url != GRAPH_PHOTO_URL or not access_token:
            raise ValueError("entra avatar fetch refused")
        response = pinned_fetch(
            "GET", GRAPH_PHOTO_URL, headers={"Authorization": f"Bearer {access_token}"}, timeout=10, stream=True
        )
        if 300 <= response.status_code < 400:
            response.close()
            raise ValueError("entra avatar redirect refused")
        return response

    def save_user_data(self, user):
        if user.avatar == GRAPH_PHOTO_URL:
            user.avatar = ""  # never keep the Graph URL as a public avatar
        return super().save_user_data(user)

    def sync_user_data(self, user):
        data = self.user_data.get("user", {})
        user.first_name = data.get("first_name") or ""
        user.last_name = data.get("last_name") or ""
        user.display_name = data.get("display_name") or User.get_display_name(self.user_data.get("email"))
        # Only replace the avatar when a new photo was actually fetched (404 = no photo: keep the old one).
        new_asset = self.download_and_upload_avatar(avatar_url=data.get("avatar", ""), user=user)
        if new_asset:
            self.delete_old_avatar(user=user)
            user.avatar_asset = new_asset
        user.save()
        return user
