from django.urls import path

from .views import (
    GodModeAdminEndpoint,
    GodModeSessionEndpoint,
    GodModeSignInEndpoint,
    GodModeWorkspaceArchiveEndpoint,
    GodModeWorkspaceEndpoint,
)

urlpatterns = [
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
]
