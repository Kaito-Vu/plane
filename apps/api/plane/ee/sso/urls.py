# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .saml_views import SamlAcsEndpoint, SamlMetadataEndpoint
from .views import SsoCallbackEndpoint, SsoInitiateEndpoint, SsoProvidersEndpoint

urlpatterns = [
    path("providers/", SsoProvidersEndpoint.as_view(), name="ee-sso-providers"),
    path("saml/acs/", SamlAcsEndpoint.as_view(), name="ee-sso-saml-acs"),
    path("saml/metadata/", SamlMetadataEndpoint.as_view(), name="ee-sso-saml-metadata"),
    path("spaces/<str:provider_id>/", SsoInitiateEndpoint.as_view(), {"target": "space"}, name="ee-sso-space-initiate"),
    path("<str:provider_id>/", SsoInitiateEndpoint.as_view(), name="ee-sso-initiate"),
    path("<str:provider_id>/callback/", SsoCallbackEndpoint.as_view(), name="ee-sso-callback"),
]
