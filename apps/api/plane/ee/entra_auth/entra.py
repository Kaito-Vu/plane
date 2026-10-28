import os
import re

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.ee.entra_auth.oidc import OIDCProvider
from plane.ee.entra_auth.profile import claims_to_user_data, parse_domains
from plane.license.utils.instance_value import get_configuration_value

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
