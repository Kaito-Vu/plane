# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from .views import (
    ProjectWorkItemTypeAssignEndpoint,
    ProjectWorkItemTypeDefaultEndpoint,
    ProjectWorkItemTypesEndpoint,
    WorkItemTypeDetailEndpoint,
    WorkItemTypeListEndpoint,
    WorkItemTypeSeedEndpoint,
    WorkItemTypeUsageEndpoint,
)

urlpatterns = [
    path("", WorkItemTypeListEndpoint.as_view(), name="ee-work-item-types"),
    path("seed/", WorkItemTypeSeedEndpoint.as_view(), name="ee-work-item-types-seed"),
    path("<uuid:pk>/usage/", WorkItemTypeUsageEndpoint.as_view(), name="ee-work-item-type-usage"),
    path("<uuid:pk>/", WorkItemTypeDetailEndpoint.as_view(), name="ee-work-item-type"),
]

project_urlpatterns = [
    path("", ProjectWorkItemTypesEndpoint.as_view(), name="ee-project-work-item-types"),
    path("assign/", ProjectWorkItemTypeAssignEndpoint.as_view(), name="ee-project-work-item-type-assign"),
    path(
        "assign/<uuid:type_id>/", ProjectWorkItemTypeAssignEndpoint.as_view(), name="ee-project-work-item-type-unassign"
    ),
    path("default/", ProjectWorkItemTypeDefaultEndpoint.as_view(), name="ee-project-work-item-type-default"),
]
