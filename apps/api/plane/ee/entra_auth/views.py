import os
import uuid
from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from django.views import View

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.utils.login import user_login
from plane.authentication.utils.oauth_state import validate_oauth_state
from plane.authentication.utils.redirection_path import get_redirection_path
from plane.authentication.utils.user_auth_workflow import post_user_auth_workflow
from plane.ee.entra_auth.entra import EntraProvider
from plane.license.models import Instance
from plane.license.utils.instance_value import get_configuration_value
from plane.utils.path_validator import validate_next_path

SESSION_SURFACE = "entra_surface"


def _redirect_error(host, exc, next_path=None):
    params = exc.get_error_dict()
    if next_path:
        params["next_path"] = str(validate_next_path(next_path))
    return HttpResponseRedirect(f"{host}?{urlencode(params)}")


def _error(code):
    return AuthenticationException(error_code=AUTHENTICATION_ERROR_CODES[code], error_message=code)


def _entra_enabled():
    (value,) = get_configuration_value([{"key": "IS_ENTRA_ENABLED", "default": os.environ.get("IS_ENTRA_ENABLED", "0")}])
    return value == "1"


def _instance_ready():
    instance = Instance.objects.first()
    return instance is not None and instance.is_setup_done


class _EntraInitiate(View):
    surface = "app"

    def get(self, request):
        is_app = self.surface == "app"
        host = base_host(request=request, is_app=is_app, is_space=not is_app)
        request.session["host"] = host
        request.session[SESSION_SURFACE] = self.surface
        next_path = request.GET.get("next_path")
        request.session.pop("next_path", None)  # never inherit a path from an abandoned login
        if next_path:
            request.session["next_path"] = str(validate_next_path(next_path))

        if not _instance_ready():
            return _redirect_error(host, _error("INSTANCE_NOT_CONFIGURED"), next_path)
        if not _entra_enabled():
            return _redirect_error(host, _error("ENTRA_NOT_CONFIGURED"), next_path)
        try:
            state = uuid.uuid4().hex
            provider = EntraProvider(request=request, state=state)
            request.session["state"] = state
            return HttpResponseRedirect(provider.get_auth_url())
        except AuthenticationException as e:
            return _redirect_error(host, e, next_path)


class EntraInitiateEndpoint(_EntraInitiate):
    surface = "app"


class EntraInitiateSpaceEndpoint(_EntraInitiate):
    surface = "space"


class EntraCallbackEndpoint(View):
    """Single redirect URI registered in Entra; the initiating surface is read from the session."""

    def get(self, request):
        code = request.GET.get("code")
        state = request.GET.get("state")
        is_space = request.session.get(SESSION_SURFACE) == "space"
        is_app = not is_space
        host = request.session.get("host") or base_host(request=request, is_app=is_app, is_space=is_space)
        next_path = request.session.pop("next_path", None)

        if not _entra_enabled():
            return _redirect_error(host, _error("ENTRA_NOT_CONFIGURED"), next_path)
        if not validate_oauth_state(request=request, state=state) or not code:
            return _redirect_error(host, _error("ENTRA_PROVIDER_ERROR"), next_path)
        request.session.pop(SESSION_SURFACE, None)  # state validated: surface is single-use

        try:
            if not _instance_ready():
                raise _error("INSTANCE_NOT_CONFIGURED")
            provider = EntraProvider(
                request=request, code=code, callback=post_user_auth_workflow if is_app else None
            )
            user = provider.authenticate()
            user_login(request=request, user=user, is_app=is_app, is_space=is_space)
            if next_path:
                path = str(validate_next_path(next_path))
            else:
                path = get_redirection_path(user=user) if is_app else ""
            return HttpResponseRedirect(f"{host.rstrip('/')}/{path.lstrip('/')}" if path else host)
        except AuthenticationException as e:
            return _redirect_error(host, e, next_path)
