"""God-mode sign-in through Entra / an already valid app session (plugin; core untouched).

Admin and app sessions use different cookies (picked by URL path). Our URLs are app paths, so
the admin session is built by hand and its cookie is set on the response.
"""

from importlib import import_module

from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.views import View

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.utils.login import user_login
from plane.db.models import User

from .access import is_god_mode_user


def _admin_login(request, user):
    app_session = request.session
    request.session = import_module(settings.SESSION_ENGINE).SessionStore(None)
    try:
        user_login(request=request, user=user, is_admin=True)
        key = request.session.session_key
    finally:
        request.session = app_session
    response = HttpResponseRedirect(f"{base_host(request=request, is_admin=True)}general/")
    response.set_cookie(
        settings.ADMIN_SESSION_COOKIE_NAME,
        key,
        max_age=settings.ADMIN_SESSION_COOKIE_AGE,
        domain=settings.SESSION_COOKIE_DOMAIN,
        path=settings.SESSION_COOKIE_PATH,
        secure=settings.SESSION_COOKIE_SECURE or None,
        httponly=settings.SESSION_COOKIE_HTTPONLY or None,
        samesite=settings.SESSION_COOKIE_SAMESITE,
    )
    return response


def finish_entra_login(request, provider):
    """Called by the Entra callback for the "admin" surface. Never signs anyone up."""
    provider.set_token_data()
    provider.set_user_data()
    provider._check_identity()
    existing = User.objects.filter(email=provider.user_data["email"]).first()
    if not is_god_mode_user(existing):
        raise AuthenticationException(
            error_code=AUTHENTICATION_ERROR_CODES["ADMIN_AUTHENTICATION_FAILED"],
            error_message="ADMIN_AUTHENTICATION_FAILED",
        )
    return _admin_login(request, provider.complete_login_or_signup())


class GodModeSsoEndpoint(View):
    """GET ?check=1 -> {"eligible"}; GET -> reuse a valid god-mode app session, else go to Entra."""

    def get(self, request):
        eligible = is_god_mode_user(request.user)
        if request.GET.get("check"):
            return JsonResponse({"eligible": eligible})
        if eligible:
            return _admin_login(request, request.user)
        from plane.ee.entra_auth.views import EntraInitiateEndpoint

        return EntraInitiateEndpoint.as_view(surface="admin")(request)
