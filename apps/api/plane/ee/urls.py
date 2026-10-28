from django.urls import path

from plane.ee.views import EeHealthEndpoint

urlpatterns = [
    path("ee/health/", EeHealthEndpoint.as_view(), name="ee-health"),
]
