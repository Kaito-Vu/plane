from django.urls import include, path

from plane.ee.views import EeHealthEndpoint

urlpatterns = [
    path("ee/health/", EeHealthEndpoint.as_view(), name="ee-health"),
    path("", include("plane.ee.work_item_types.urls")),
]
