# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import include, path

from plane.urls import handler404, urlpatterns as core_urlpatterns  # noqa: F401

urlpatterns = [path("auth/sso/", include("plane.ee.sso.urls")), *core_urlpatterns]
