# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import base64
import hashlib
import secrets
import uuid

from django.http import HttpResponseRedirect, JsonResponse
from django.views import View

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.utils.user_auth_workflow import post_user_auth_workflow
from plane.ee.sso.adapter import SsoOauthProvider
from plane.ee.sso.config import list_enabled_providers
from plane.ee.sso.flow import complete_login, provider_error, redirect_error
from plane.license.models import Instance
from plane.utils.path_validator import validate_next_path


class SsoProvidersEndpoint(View):
    def get(self, request):
        return JsonResponse(list_enabled_providers(), safe=False)


class SsoInitiateEndpoint(View):
    def get(self, request, provider_id):
        host = base_host(request=request, is_app=True)
        request.session["host"] = host
        next_path = request.GET.get("next_path")
        if next_path:
            request.session["next_path"] = str(validate_next_path(next_path))

        instance = Instance.objects.first()
        if instance is None or not instance.is_setup_done:
            return redirect_error(
                host,
                AuthenticationException(
                    error_code=AUTHENTICATION_ERROR_CODES["INSTANCE_NOT_CONFIGURED"],
                    error_message="INSTANCE_NOT_CONFIGURED",
                ),
                next_path,
            )
        try:
            state, nonce = uuid.uuid4().hex, secrets.token_urlsafe(24)
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
            provider = SsoOauthProvider(request, provider_id, state=state, nonce=nonce, code_challenge=challenge)
            request.session["sso_state"] = state
            request.session["sso_nonce"] = nonce
            request.session["sso_verifier"] = verifier
            return HttpResponseRedirect(provider.get_auth_url())
        except AuthenticationException as e:
            return redirect_error(host, e, next_path)


class SsoCallbackEndpoint(View):
    def get(self, request, provider_id):
        host = request.session.pop("host", None) or base_host(request=request, is_app=True)
        next_path = request.session.pop("next_path", None)
        # one-time use: pop so a replayed callback fails the state check
        expected_state = request.session.pop("sso_state", None)
        nonce = request.session.pop("sso_nonce", None)
        verifier = request.session.pop("sso_verifier", None)
        code, state = request.GET.get("code"), request.GET.get("state")

        if not code or not expected_state or not secrets.compare_digest(str(state or ""), expected_state):
            return redirect_error(host, provider_error(), next_path)
        try:
            provider = SsoOauthProvider(
                request,
                provider_id,
                code=code,
                nonce=nonce,
                code_verifier=verifier,
                callback=post_user_auth_workflow,
            )
            user = provider.authenticate()
            return complete_login(request, user, host, next_path)
        except AuthenticationException as e:
            return redirect_error(host, e, next_path)
