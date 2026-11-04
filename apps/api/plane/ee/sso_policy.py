"""Users who sign in through a third-party provider (OIDC, Entra, Google, ...) are managed by that
provider: they cannot change their name, set/change a password or sign in with a password.

Everything lives here; the views below shadow the core routes from plane.ee.urls / plane.ee.auth_urls,
which are included before the core ones.
"""

# Django imports
from django.http import HttpResponseRedirect

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.views import UserEndpoint
from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.host import base_host
from plane.authentication.views.app.email import SignInAuthEndpoint
from plane.authentication.views.common import ChangePasswordEndpoint, SetUserPasswordEndpoint
from plane.authentication.views.space.email import SignInAuthSpaceEndpoint
from plane.db.models import Account, User
from plane.utils.path_validator import get_safe_redirect_url

NAME_FIELDS = ("first_name", "last_name", "display_name")
PASSWORD_ERROR = "Password is managed by your identity provider"


def is_sso_user(user):
    return Account.objects.filter(user=user).exists()


def _password_sign_in_blocked(request, **host_kwargs):
    """Same redirect as a wrong password, so SSO accounts are not distinguishable from local ones."""
    email = (request.POST.get("email") or "").strip().lower()
    user = User.objects.filter(email=email).first() if email else None
    if not (user and is_sso_user(user)):
        return None
    exc = AuthenticationException(
        error_code=AUTHENTICATION_ERROR_CODES["AUTHENTICATION_FAILED_SIGN_IN"],
        error_message="AUTHENTICATION_FAILED_SIGN_IN",
        payload={"email": email},
    )
    url = get_safe_redirect_url(
        base_url=base_host(request=request, **host_kwargs),
        next_path=request.POST.get("next_path"),
        params=exc.get_error_dict(),
    )
    return HttpResponseRedirect(url)


class SsoSignInAuthEndpoint(SignInAuthEndpoint):
    def post(self, request):
        return _password_sign_in_blocked(request, is_app=True) or super().post(request)


class SsoSignInAuthSpaceEndpoint(SignInAuthSpaceEndpoint):
    def post(self, request):
        return _password_sign_in_blocked(request, is_space=True) or super().post(request)


def _forbidden():
    return Response({"error": PASSWORD_ERROR}, status=status.HTTP_403_FORBIDDEN)


class SsoChangePasswordEndpoint(ChangePasswordEndpoint):
    def post(self, request):
        return _forbidden() if is_sso_user(request.user) else super().post(request)


class SsoSetUserPasswordEndpoint(SetUserPasswordEndpoint):
    def post(self, request):
        return _forbidden() if is_sso_user(request.user) else super().post(request)


class SsoUserEndpoint(UserEndpoint):
    def retrieve(self, request):
        response = super().retrieve(request)
        sso = is_sso_user(request.user)
        response.data["is_sso_user"] = sso
        if sso:
            # nothing to set up: keeps the onboarding "set a password" step out of the way
            response.data["is_password_autoset"] = False
        return response

    def partial_update(self, request, *args, **kwargs):
        user = request.user
        if is_sso_user(user):
            for field in NAME_FIELDS:
                current = getattr(user, field)
                # a name the provider left empty can still be filled in (onboarding)
                if current and field in request.data and request.data[field] != current:
                    return Response(
                        {field: "Managed by your identity provider."}, status=status.HTTP_400_BAD_REQUEST
                    )
        return super().partial_update(request, *args, **kwargs)
