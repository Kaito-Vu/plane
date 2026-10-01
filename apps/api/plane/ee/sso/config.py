# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re

from django.conf import settings
from django.core.cache import cache

from plane.license.models import InstanceConfiguration
from plane.license.utils.instance_value import get_configuration_value

DEFAULT_SCOPE = "openid profile"  # least privilege: e-mail is never used
GUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
OAUTH_FIELDS = ["CLIENT_ID", "CLIENT_SECRET", "SCOPE"]
ENCRYPTED_FIELDS = {"CLIENT_SECRET"}

# Every provider also has ENABLED and LABEL (see BASE_FIELDS). `fields` are the provider-specific
# extras; `required` must all be non-empty for the provider to count as configured.
PROVIDERS = {
    "oidc": {
        "label": "OpenID Connect",
        "protocol": "oidc",
        "fields": [*OAUTH_FIELDS, "ISSUER", "CALLBACK_URL", "ALLOW_SIGNUP"],
        "required": ["CLIENT_ID", "CLIENT_SECRET", "ISSUER"],
    },
    "azure_ad": {
        "label": "Microsoft",
        "protocol": "oidc",
        "fields": [*OAUTH_FIELDS, "TENANT_ID", "ISSUER", "CALLBACK_URL", "ALLOW_SIGNUP"],  # ISSUER optional override
        "required": ["CLIENT_ID", "CLIENT_SECRET", "TENANT_ID"],
    },
    "oauth2": {
        "label": "OAuth2",
        "protocol": "oauth2",
        "fields": [*OAUTH_FIELDS, "AUTH_URL", "TOKEN_URL", "USERINFO_URL", "CALLBACK_URL", "ALLOW_SIGNUP"],
        "required": ["CLIENT_ID", "CLIENT_SECRET", "AUTH_URL", "TOKEN_URL", "USERINFO_URL"],
    },
    "saml": {
        "label": "SAML",
        "protocol": "saml",
        "fields": [
            "IDP_ENTITY_ID",
            "IDP_SSO_URL",
            "IDP_X509CERT",
            "SP_ENTITY_ID",
            "ATTR_FIRST_NAME",
            "ATTR_LAST_NAME",
            "CALLBACK_URL",
            "ALLOW_SIGNUP",
        ],
        "required": ["IDP_ENTITY_ID", "IDP_SSO_URL", "IDP_X509CERT"],
    },
}
PROVIDER_IDS = tuple(PROVIDERS)
BASE_FIELDS = ["ENABLED", "LABEL"]
# seeded defaults; ALLOW_SIGNUP is the per-provider "allow sign-up" option ("0": only existing users may log in here)
DEFAULT_VALUES = {"ENABLED": "0", "ALLOW_SIGNUP": "1"}


def config_key(provider_id, field):
    return f"EE_SSO_{provider_id.upper()}_{field}"


def _fields(provider_id):
    return BASE_FIELDS + PROVIDERS[provider_id]["fields"]


def seed_config(**_kwargs):
    created_any = False
    for provider_id in PROVIDER_IDS:
        for field in _fields(provider_id):
            _, created = InstanceConfiguration.objects.get_or_create(
                key=config_key(provider_id, field),
                defaults={
                    "value": DEFAULT_VALUES.get(field, ""),
                    "category": f"EE_SSO_{provider_id.upper()}",
                    "is_encrypted": field in ENCRYPTED_FIELDS,
                },
            )
            created_any = created_any or created
    if created_any:
        # core caches GET /api/instances/configurations/ for 2h and only PATCH invalidates it; without this
        # the admin UI would not see freshly seeded keys on an existing instance.
        cache.delete_many(["/api/instances/configurations/", "/api/instances/"])


def get_sso_config(provider_id):
    if provider_id not in PROVIDERS:
        return None
    fields = _fields(provider_id)
    values = get_configuration_value([{"key": config_key(provider_id, f), "default": ""} for f in fields])
    cfg = dict(zip(fields, values))
    if cfg["ENABLED"] != "1":
        return None
    if not all(cfg.get(f) for f in PROVIDERS[provider_id]["required"]):
        return None
    # Azure AD is single-tenant: TENANT_ID must be the tenant GUID (not a domain, `common`, `organizations`,
    # `consumers`). Azure publishes the GUID in the discovery issuer / `tid` claim, so anything else can never match.
    if provider_id == "azure_ad" and not GUID_RE.fullmatch(cfg["TENANT_ID"].strip().lower()):
        return None
    if "SCOPE" in cfg:
        cfg["SCOPE"] = cfg["SCOPE"] or DEFAULT_SCOPE
    if "ALLOW_SIGNUP" in cfg:
        cfg["ALLOW_SIGNUP"] = cfg["ALLOW_SIGNUP"] or "1"
    cfg["LABEL"] = cfg["LABEL"] or PROVIDERS[provider_id]["label"]
    return cfg


def public_origin(request):
    """Public base URL of this Plane instance. Prefers the configured WEB_URL/APP_BASE_URL (not Host-header
    controlled); falls back to the request only when neither is set."""
    configured = settings.WEB_URL or settings.APP_BASE_URL
    if configured:
        return configured.rstrip("/")
    return f"{'https' if request.is_secure() else 'http'}://{request.get_host()}"


def callback_url(request, provider_id, cfg):
    """Redirect URI (OIDC/Azure/OAuth2) or ACS URL (SAML) sent to / registered at the IdP.
    An admin-set CALLBACK_URL wins; it must be absolute http(s) and must still reach our endpoint."""
    custom = (cfg.get("CALLBACK_URL") or "").strip()
    if custom.startswith(("http://", "https://")):
        return custom
    path = "acs" if provider_id == "saml" else "callback"
    return f"{public_origin(request)}/auth/sso/{provider_id}/{path}/"


def list_enabled_providers():
    out = []
    for provider_id in PROVIDER_IDS:
        cfg = get_sso_config(provider_id)
        if cfg:
            out.append({"id": provider_id, "label": cfg["LABEL"], "protocol": PROVIDERS[provider_id]["protocol"]})
    return out
