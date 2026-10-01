# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import include, path

from plane.ee.work_item_types.urls import project_urlpatterns
from plane.urls import handler404, urlpatterns as core_urlpatterns  # noqa: F401

urlpatterns = [
    path("auth/sso/", include("plane.ee.sso.urls")),
    path("api/workspaces/<str:slug>/work-item-types/", include("plane.ee.work_item_types.urls")),
    path(
        "api/workspaces/<str:slug>/projects/<uuid:project_id>/work-item-types/",
        include((project_urlpatterns, "ee")),
    ),
    *core_urlpatterns,
]
