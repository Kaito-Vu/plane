# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import re
import secrets
import time
from urllib.parse import urlparse

from django.core.cache import cache
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings

from plane.authentication.adapter.base import Adapter
from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.ee.sso import errors  # noqa: F401
from plane.ee.sso.config import callback_url, get_sso_config, public_origin
from plane.ee.sso.flow import provider_error
from plane.ee.sso.identity import SubjectLoginMixin, subject_key

RELAY_TTL = 600
REPLAY_TTL_FALLBACK = 3600
BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
NAMEID_PERSISTENT = "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent"

FIRST_ATTRS = [
    "firstName",
    "givenName",
    "given_name",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
    "urn:oid:2.5.4.42",
]
LAST_ATTRS = [
    "lastName",
    "sn",
    "surname",
    "family_name",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
    "urn:oid:2.5.4.4",
]


def normalize_cert(value):
    return re.sub(r"-----(BEGIN|END) CERTIFICATE-----|\s+", "", value or "")


def acs_url(request):
    return callback_url(request, "saml", get_sso_config("saml") or {})


def metadata_url(request):
    return f"{public_origin(request)}/auth/sso/saml/metadata/"


def new_relay_token():
    return secrets.token_urlsafe(32)


def _relay_key(token):
    return f"ee_sso_saml_relay:{token}"


def save_relay(token, data):
    cache.set(_relay_key(token), data, RELAY_TTL)


def pop_relay(token):
    if not token:
        return None
    data = cache.get(_relay_key(token))
    if data is not None:
        cache.delete(_relay_key(token))
    return data


def build_settings(request, cfg):
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": cfg["SP_ENTITY_ID"] or metadata_url(request),
            "assertionConsumerService": {"url": callback_url(request, "saml", cfg), "binding": BINDING_POST},
            # stable pairwise identifier; e-mail / unspecified NameIDs are reassignable and never used as identity
            "NameIDFormat": NAMEID_PERSISTENT,
        },
        "idp": {
            "entityId": cfg["IDP_ENTITY_ID"],
            "singleSignOnService": {"url": cfg["IDP_SSO_URL"], "binding": BINDING_REDIRECT},
            "x509cert": normalize_cert(cfg["IDP_X509CERT"]),
        },
        # python3-saml rejects a response that carries no valid signature (response or assertion)
        # when the IdP certificate is configured, so no extra flags are needed here.
        "security": {
            # intranet / dev hosts ("plane", "localhost", "testserver") are single-label; python3-saml rejects
            # such SP URLs unless this is set
            "allowSingleLabelDomains": True,
            "authnRequestsSigned": False,
            "wantNameIdEncrypted": False,
            "rejectDeprecatedAlgorithm": True,
        },
    }


def _prepare_request(request):
    # Derive scheme/host/path from the configured ACS URL, so python3-saml's Destination check compares against
    # what the IdP was told to post to, independent of the Host header and of proxy rewriting.
    parsed = urlparse(acs_url(request))
    return {
        "https": "on" if parsed.scheme == "https" else "off",
        "http_host": parsed.netloc,
        "script_name": parsed.path,
        "get_data": request.GET.dict(),
        "post_data": request.POST.dict(),
    }


def _first(attrs, names):
    for name in names:
        values = attrs.get(name)
        if values:
            return values[0]
    return None


class SamlProvider(SubjectLoginMixin, Adapter):
    def __init__(self, request, callback=None):
        cfg = get_sso_config("saml")
        if not cfg:
            raise AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["SSO_NOT_CONFIGURED"], error_message="SSO_NOT_CONFIGURED"
            )
        super().__init__(request, "sso-saml", callback)
        self.cfg = cfg
        self.saml_settings = build_settings(request, cfg)
        try:
            self.auth = OneLogin_Saml2_Auth(_prepare_request(request), self.saml_settings)
        except Exception as e:  # OneLogin_Saml2_Error: invalid settings
            self.logger.warning("SAML settings rejected: %s", e)
            raise provider_error()

    def login_url(self, relay_token):
        return self.auth.login(return_to=relay_token)

    def request_id(self):
        return self.auth.get_last_request_id()

    def metadata_xml(self):
        settings = OneLogin_Saml2_Settings(self.saml_settings, sp_validation_only=True)
        xml = settings.get_sp_metadata()
        xml = xml.decode() if isinstance(xml, bytes) else xml
        errors = settings.validate_metadata(xml)
        if errors:
            raise provider_error(f"SSO_PROVIDER_ERROR: invalid SP metadata {errors}")
        return xml

    def authenticate(self, request_id):
        try:
            self.auth.process_response(request_id=request_id)
        except Exception as e:  # OneLogin_Saml2_Error / lxml XMLSyntaxError / binascii.Error on garbage input
            self.logger.warning("SAML response unparsable: %s", e)
            raise provider_error()
        if self.auth.get_errors() or not self.auth.is_authenticated():
            # reason is logged only; never put it in the redirect (it can leak IdP/SP details)
            self.logger.warning(
                "SAML response rejected: %s %s", self.auth.get_errors(), self.auth.get_last_error_reason()
            )
            raise provider_error()
        # python3-saml checks InResponseTo only when the response carries one: require it to be present and ours,
        # otherwise a signed unsolicited response could be replayed against a relay token obtained from any flow
        if self.auth.get_last_response_in_response_to() != request_id:
            raise provider_error("SSO_PROVIDER_ERROR: InResponseTo missing or not ours")
        self._reject_replay()
        nameid = self.auth.get_nameid()
        if not nameid or self.auth.get_nameid_format() != NAMEID_PERSISTENT:
            self.logger.warning("SAML NameID is not persistent (format=%s)", self.auth.get_nameid_format())
            raise provider_error("SSO_PROVIDER_ERROR: NameID must be persistent")
        key = subject_key(self.cfg["IDP_ENTITY_ID"], nameid)
        attrs = self.auth.get_attributes()
        first = _first(attrs, ([self.cfg["ATTR_FIRST_NAME"]] if self.cfg.get("ATTR_FIRST_NAME") else []) + FIRST_ATTRS)
        last = _first(attrs, ([self.cfg["ATTR_LAST_NAME"]] if self.cfg.get("ATTR_LAST_NAME") else []) + LAST_ATTRS)
        profile = {"first_name": first, "last_name": last, "display_name": f"{first or ''} {last or ''}".strip()}
        return self.login_by_subject(key, profile, self.cfg["ALLOW_SIGNUP"])

    def _reject_replay(self):
        assertion_id = self.auth.get_last_assertion_id()
        not_on_or_after = self.auth.get_last_assertion_not_on_or_after()
        try:
            ttl = max(int(not_on_or_after - time.time()), 60)
        except (TypeError, ValueError):
            ttl = REPLAY_TTL_FALLBACK
        if assertion_id and not cache.add(f"ee_sso_saml_assertion:{assertion_id}", 1, ttl):
            self.logger.warning("SAML assertion replay rejected")
            raise provider_error()
