"""External-invites switch: when OFF (default) every invite/accept path answers 410 and creates no rows."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from plane.api.views import WorkspaceInvitationsViewset as ApiWorkspaceInvitationsViewset
from plane.app.views import (
    ProjectInvitationsViewset,
    ProjectJoinEndpoint,
    UserWorkspaceInvitationsViewSet,
    WorkspaceInvitationsViewset,
    WorkspaceJoinEndpoint,
)
from plane.app.views.base import BaseAPIView
from plane.license.models import InstanceConfiguration

KEY = "ALLOW_EXTERNAL_INVITES"


def external_invites_enabled() -> bool:
    return InstanceConfiguration.objects.filter(key=KEY, value="1").exists()


def gated(core_view_cls, *methods):
    """Subclass of ``core_view_cls`` whose ``methods`` answer 410 unless the switch is on, else defer to core.

    The 410 comes BEFORE the core method body (and its @allow_permission check), so it leaks nothing about
    the target. Class-level permission_classes / authentication still run first.
    """

    def make(name):
        def handler(self, *args, **kwargs):
            if not external_invites_enabled():
                return Response(
                    {"error": "External invitations are disabled on this instance", "code": "INVITES_DISABLED"},
                    status=status.HTTP_410_GONE,
                )
            return getattr(super(cls, self), name)(*args, **kwargs)

        handler.__name__ = name
        return handler

    cls = type("Gated" + core_view_cls.__name__, (core_view_cls,), {m: make(m) for m in methods})
    return cls


GatedWorkspaceInvitations = gated(WorkspaceInvitationsViewset, "create")
GatedWorkspaceJoin = gated(WorkspaceJoinEndpoint, "post")
GatedUserWorkspaceInvitations = gated(UserWorkspaceInvitationsViewSet, "create")
GatedProjectInvitations = gated(ProjectInvitationsViewset, "create")
GatedProjectJoin = gated(ProjectJoinEndpoint, "post")
GatedApiWorkspaceInvitations = gated(ApiWorkspaceInvitationsViewset, "create")


class ExternalInvitesStatusEndpoint(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"enabled": external_invites_enabled()})
