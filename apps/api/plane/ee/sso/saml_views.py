# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import secrets

from django.http import HttpResponse, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from plane.authentication.adapter.error import AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.utils.user_auth_workflow import post_user_auth_workflow
from plane.ee.sso.flow import complete_login, provider_error, redirect_error
from plane.ee.sso.saml import RELAY_TTL, SamlProvider, acs_url, new_relay_token, pop_relay, save_relay


BIND_COOKIE = "ee_sso_saml_bind"


def saml_start(request, host, next_path, target="app"):
    try:
        provider = SamlProvider(request)
        token = new_relay_token()
        url = provider.login_url(token)
        data = {"request_id": provider.request_id(), "host": host, "next_path": next_path, "target": target}
        response = HttpResponseRedirect(url)
        # Login-CSRF defence: bind the relay to the browser that started the flow. The IdP's POST is cross-site, so the
        # cookie must be SameSite=None (which browsers only accept with Secure). Plain-http (dev) cannot be bound.
        if acs_url(request).startswith("https://"):
            data["bind"] = secrets.token_urlsafe(32)
            response.set_cookie(
                BIND_COOKIE, data["bind"], max_age=RELAY_TTL, secure=True, httponly=True, samesite="None"
            )
        save_relay(token, data)
        return response
    except AuthenticationException as e:
        return redirect_error(host, e, next_path)


@method_decorator(csrf_exempt, name="dispatch")
class SamlAcsEndpoint(View):
    """Receives the IdP's cross-site POST. CSRF-exempt by necessity; integrity comes from the
    signed response, the one-time RelayState and the InResponseTo check."""

    def post(self, request):
        relay = pop_relay(request.POST.get("RelayState", ""))
        if not relay:
            return redirect_error(base_host(request=request, is_app=True), provider_error())
        host, next_path = relay["host"], relay.get("next_path")
        target = relay.get("target", "app")
        try:
            bind = relay.get("bind")
            if bind and not secrets.compare_digest(request.COOKIES.get(BIND_COOKIE, ""), bind):
                raise provider_error("SSO_PROVIDER_ERROR: relay not bound to this browser")
            provider = SamlProvider(request, callback=post_user_auth_workflow if target == "app" else None)
            user = provider.authenticate(relay["request_id"])
            response = complete_login(request, user, host, next_path, target)
        except AuthenticationException as e:
            response = redirect_error(host, e, next_path)
        response.delete_cookie(BIND_COOKIE, samesite="None")
        return response


class SamlMetadataEndpoint(View):
    def get(self, request):
        try:
            return HttpResponse(SamlProvider(request).metadata_xml(), content_type="text/xml")
        except AuthenticationException:
            return HttpResponse(status=404)
