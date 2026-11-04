# External API (api/v1/) routes for the EE layer.
from django.urls import path

from plane.ee.project_members.invites import GatedApiWorkspaceInvitations
from plane.ee.project_members.views import EeProjectMemberListCreateAPIEndpoint
from plane.ee.work_item_types.views.bulk_tree import BulkTreeAPIEndpoint

urlpatterns = [
    path("workspaces/<str:slug>/projects/<uuid:project_id>/issues/bulk-tree/", BulkTreeAPIEndpoint.as_view()),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/members/",
        EeProjectMemberListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="project-members",
    ),
    path(
        "workspaces/<str:slug>/invitations/",
        GatedApiWorkspaceInvitations.as_view({"get": "list", "post": "create"}),
        name="workspace-invitations-list",
    ),
]
