# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.http import HttpResponse, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from plane.authentication.adapter.error import AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.utils.user_auth_workflow import post_user_auth_workflow
from plane.ee.sso.flow import complete_login, provider_error, redirect_error
from plane.ee.sso.saml import SamlProvider, new_relay_token, pop_relay, save_relay


def saml_start(request, host, next_path):
    try:
        provider = SamlProvider(request)
        token = new_relay_token()
        url = provider.login_url(token)
        save_relay(token, {"request_id": provider.request_id(), "host": host, "next_path": next_path})
        return HttpResponseRedirect(url)
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
        try:
            provider = SamlProvider(request, callback=post_user_auth_workflow)
            user = provider.authenticate(relay["request_id"])
            return complete_login(request, user, host, next_path)
        except AuthenticationException as e:
            return redirect_error(host, e, next_path)


class SamlMetadataEndpoint(View):
    def get(self, request):
        try:
            return HttpResponse(SamlProvider(request).metadata_xml(), content_type="text/xml")
        except AuthenticationException:
            return HttpResponse(status=404)
