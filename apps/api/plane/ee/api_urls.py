# External API (api/v1/) routes for the EE layer.
from django.urls import path

from plane.ee.work_item_types.views.bulk_tree import BulkTreeAPIEndpoint

urlpatterns = [
    path("workspaces/<str:slug>/projects/<uuid:project_id>/issues/bulk-tree/", BulkTreeAPIEndpoint.as_view()),
]
