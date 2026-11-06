from django.urls import path

from .sso import GodModeSsoEndpoint
from .views import (
    GodModeExternalInvitesEndpoint,
    GodModeAdminEndpoint,
    GodModeSessionEndpoint,
    GodModeSignInEndpoint,
    GodModeWorkspaceArchiveEndpoint,
    GodModeWorkspaceEndpoint,
    GodModeWorkspaceMemberEndpoint,
)

urlpatterns = [
    path("god-mode/sso/", GodModeSsoEndpoint.as_view(), name="god-mode-sso"),
    path("instances/admins/", GodModeAdminEndpoint.as_view(), name="god-mode-admins"),
    path("instances/admins/<uuid:pk>/", GodModeAdminEndpoint.as_view(), name="god-mode-admin-detail"),
    path("instances/admins/sign-in/", GodModeSignInEndpoint.as_view(), name="god-mode-sign-in"),
    path("instances/admins/session/", GodModeSessionEndpoint.as_view(), name="god-mode-session"),
    path("instances/workspaces/<str:slug>/", GodModeWorkspaceEndpoint.as_view(), name="god-mode-workspace"),
    path(
        "instances/workspaces/<str:slug>/archive/",
        GodModeWorkspaceArchiveEndpoint.as_view(),
        name="god-mode-workspace-archive",
    ),
    path(
        "instances/workspaces/<str:slug>/members/",
        GodModeWorkspaceMemberEndpoint.as_view(),
        name="god-mode-workspace-members",
    ),
    path("instances/external-invites/", GodModeExternalInvitesEndpoint.as_view(), name="god-mode-external-invites"),
]
