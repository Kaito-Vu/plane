from django.urls import path

from .invites import (
    ExternalInvitesStatusEndpoint,
    GatedProjectInvitations,
    GatedProjectJoin,
    GatedUserWorkspaceInvitations,
    GatedWorkspaceInvitations,
    GatedWorkspaceJoin,
)

from .views import (
    EeProjectMemberViewSet,
    EeProjectViewSet,
    ProjectMemberAllocationEndpoint,
    ProjectMemberSearchEndpoint,
)

# Same routes/names as plane/app/urls/project.py; plane.ee.urls is included first so these win.
_base = "workspaces/<str:slug>/projects/<uuid:project_id>/members/"

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/", EeProjectViewSet.as_view({"get": "list", "post": "create"}), name="project"
    ),
    path(_base, EeProjectMemberViewSet.as_view({"get": "list", "post": "create"}), name="project-member"),
    path(_base + "search/", ProjectMemberSearchEndpoint.as_view(), name="project-member-search"),
    path(_base + "allocations/", ProjectMemberAllocationEndpoint.as_view(), name="project-member-allocations"),
    path(
        _base + "<uuid:pk>/",
        EeProjectMemberViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="project-member",
    ),
    path(_base + "leave/", EeProjectMemberViewSet.as_view({"post": "leave"}), name="project-member"),
    # External-invites switch: same paths/names as core; create/accept answer 410 unless the switch is on.
    path("external-invites/", ExternalInvitesStatusEndpoint.as_view(), name="external-invites-status"),
    path(
        "workspaces/<str:slug>/invitations/",
        GatedWorkspaceInvitations.as_view({"get": "list", "post": "create"}),
        name="workspace-invitations",
    ),
    path("workspaces/<str:slug>/invitations/<uuid:pk>/join/", GatedWorkspaceJoin.as_view(), name="workspace-join"),
    path(
        "users/me/workspaces/invitations/",
        GatedUserWorkspaceInvitations.as_view({"get": "list", "post": "create"}),
        name="user-workspace-invitations",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/invitations/",
        GatedProjectInvitations.as_view({"get": "list", "post": "create"}),
        name="project-member-invite",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/join/<uuid:pk>/",
        GatedProjectJoin.as_view(),
        name="project-join",
    ),
]
