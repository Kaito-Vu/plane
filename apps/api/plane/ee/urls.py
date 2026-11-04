from django.urls import include, path

from plane.ee.sso_policy import SsoUserEndpoint
from plane.ee.views import EeHealthEndpoint

urlpatterns = [
    path("ee/health/", EeHealthEndpoint.as_view(), name="ee-health"),
    path(
        "users/me/",
        SsoUserEndpoint.as_view({"get": "retrieve", "patch": "partial_update", "delete": "deactivate"}),
        name="users",
    ),
    path("", include("plane.ee.work_item_types.urls")),
    path("", include("plane.ee.god_mode.urls")),
]
