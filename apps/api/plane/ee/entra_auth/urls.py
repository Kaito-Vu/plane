from django.urls import path, re_path

from plane.ee.entra_auth.views import EntraCallbackEndpoint, EntraInitiateEndpoint, EntraInitiateSpaceEndpoint

urlpatterns = [
    path("entra/", EntraInitiateEndpoint.as_view(), name="entra-initiate"),
    path("spaces/entra/", EntraInitiateSpaceEndpoint.as_view(), name="space-entra-initiate"),
    re_path(r"^entra/callback/?$", EntraCallbackEndpoint.as_view(), name="entra-callback"),
]
