from django.urls import include, path

from plane.ee.sso_policy import (
    SsoChangePasswordEndpoint,
    SsoSetUserPasswordEndpoint,
    SsoSignInAuthEndpoint,
    SsoSignInAuthSpaceEndpoint,
)

urlpatterns = [
    path("sign-in/", SsoSignInAuthEndpoint.as_view(), name="sign-in"),
    path("spaces/sign-in/", SsoSignInAuthSpaceEndpoint.as_view(), name="space-sign-in"),
    path("change-password/", SsoChangePasswordEndpoint.as_view(), name="forgot-password"),
    path("set-password/", SsoSetUserPasswordEndpoint.as_view(), name="set-password"),
    path("", include("plane.ee.entra_auth.urls")),
]
