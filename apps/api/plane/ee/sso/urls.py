# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import SsoCallbackEndpoint, SsoInitiateEndpoint, SsoProvidersEndpoint

urlpatterns = [
    path("providers/", SsoProvidersEndpoint.as_view(), name="ee-sso-providers"),
    path("<str:provider_id>/", SsoInitiateEndpoint.as_view(), name="ee-sso-initiate"),
    path("<str:provider_id>/callback/", SsoCallbackEndpoint.as_view(), name="ee-sso-callback"),
]
