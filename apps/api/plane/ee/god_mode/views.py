from urllib.parse import urlencode, urljoin

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.authentication.adapter.error import AUTHENTICATION_ERROR_CODES, AuthenticationException
from plane.authentication.utils.host import base_host
from plane.db.models import Profile, Project, User, Workspace, WorkspaceMember
from plane.license.api.permissions import InstanceAdminPermission
from plane.license.api.serializers import InstanceAdminSerializer
from plane.license.api.views import (
    InstanceAdminEndpoint,
    InstanceAdminSignInEndpoint,
    InstanceAdminUserSessionEndpoint,
)
from plane.app.views.base import BaseAPIView
from plane.ee.project_members.invites import KEY as EXTERNAL_INVITES_KEY, external_invites_enabled
from plane.license.models import Instance, InstanceAdmin, InstanceConfiguration
from plane.utils.cache import invalidate_cache

from .access import is_god_mode_user


# --- workspaces ---------------------------------------------------------------------------------
class GodModeWorkspaceEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def delete(self, request, slug):
        workspace = get_object_or_404(Workspace, slug=slug)
        Profile.objects.filter(last_workspace_id=workspace.id).update(last_workspace_id=None)
        workspace.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GodModeWorkspaceArchiveEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def post(self, request, slug):
        workspace = get_object_or_404(Workspace, slug=slug)
        # Workspaces have no archive state, so archive every active project in it.
        count = Project.objects.filter(workspace=workspace, archived_at__isnull=True).update(archived_at=timezone.now())
        return Response({"archived_projects": count}, status=status.HTTP_200_OK)


class GodModeWorkspaceMemberEndpoint(BaseAPIView):
    """Assign an existing user to a workspace (or update their role / reactivate them)."""

    permission_classes = [InstanceAdminPermission]

    def get(self, request, slug):
        """Search active users by name/email; `current_role` is set when already a workspace member."""
        workspace = get_object_or_404(Workspace, slug=slug)
        search = (request.query_params.get("search") or "").strip()
        if not search:
            # no query: list current members (capped) so their role can be changed
            members = WorkspaceMember.objects.filter(workspace=workspace, is_active=True).select_related("member")
            return Response(
                [
                    {
                        "id": str(m.member_id),
                        "email": m.member.email,
                        "display_name": m.member.display_name,
                        "current_role": m.role,
                    }
                    for m in members.order_by("member__email")[:100]
                ]
            )
        if len(search) < 2:
            return Response([])
        users =User.objects.filter(is_active=True, is_bot=False).filter(
            Q(email__icontains=search)
            | Q(display_name__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
        )[:10]
        roles = dict(
            WorkspaceMember.objects.filter(workspace=workspace, is_active=True, member__in=users).values_list(
                "member_id", "role"
            )
        )
        return Response(
            [
                {
                    "id": str(u.id),
                    "email": u.email,
                    "display_name": u.display_name,
                    "current_role": roles.get(u.id),
                }
                for u in users
            ]
        )

    def post(self, request, slug):
        workspace = get_object_or_404(Workspace, slug=slug)
        email =(request.data.get("email") or "").strip().lower()
        try:
            role = int(request.data.get("role", 15))
        except (TypeError, ValueError):
            role = 0
        if role not in (5, 15, 20):
            return Response({"error": "Role must be 5, 15 or 20"}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(email=email, is_active=True).first()
        if user is None:
            return Response({"error": "No active user with this email"}, status=status.HTTP_404_NOT_FOUND)

        member, created = WorkspaceMember.objects.get_or_create(
            workspace=workspace, member=user, defaults={"role": role, "is_active": True}
        )
        if not created:
            member.role, member.is_active = role, True
            member.save(update_fields=["role", "is_active"])
        return Response(
            {"member_id": str(user.id), "role": role, "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# --- admin access -------------------------------------------------------------------------------
class GodModeAdminEndpoint(InstanceAdminEndpoint):
    """Core list endpoint, with a stricter add (role forced to 20) and a safer remove."""

    @invalidate_cache(path="/api/instances/", user=False)
    def post(self, request):
        email = (request.data.get("email") or "").strip()
        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        instance = Instance.objects.first()
        if instance is None:
            return Response({"error": "Instance is not registered yet"}, status=status.HTTP_403_FORBIDDEN)

        user = User.objects.filter(email__iexact=email, is_bot=False, is_active=True).first()
        if user is None:
            return Response(
                {"error": "No active user with this email. The user must sign up first."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if InstanceAdmin.objects.filter(instance=instance, user=user).exists():
            return Response({"error": "This user already has god-mode access"}, status=status.HTTP_409_CONFLICT)

        # superuser flag is set by the post_save receiver in access.py
        admin = InstanceAdmin.objects.create(instance=instance, user=user, role=20)
        return Response(InstanceAdminSerializer(admin).data, status=status.HTTP_201_CREATED)

    @invalidate_cache(path="/api/instances/", user=False)
    def delete(self, request, pk):
        instance = Instance.objects.first()
        target = InstanceAdmin.objects.filter(instance=instance, pk=pk).first()
        if target is None:
            return Response(status=status.HTTP_204_NO_CONTENT)
        # Self-removal is blocked, so the last admin can never be removed.
        if target.user_id == request.user.id:
            return Response({"error": "You cannot remove your own access"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Hard delete: (instance, user) is unique, a soft-deleted row would block re-adding the user.
            InstanceAdmin.objects.filter(pk=target.pk).delete(soft=False)
            if target.user_id and not InstanceAdmin.objects.filter(user_id=target.user_id).exists():
                User.objects.filter(pk=target.user_id).update(is_superuser=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- sign-in / session gate ---------------------------------------------------------------------
class GodModeSignInEndpoint(InstanceAdminSignInEndpoint):
    def post(self, request):
        email = (request.POST.get("email") or "").strip().lower()
        user = User.objects.filter(email=email).first() if email else None
        # Unknown emails fall through to core so its own errors stay unchanged.
        if user is not None and not is_god_mode_user(user):
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ADMIN_AUTHENTICATION_FAILED"],
                error_message="ADMIN_AUTHENTICATION_FAILED",
                payload={"email": email},
            )
            url = urljoin(base_host(request=request, is_admin=True), "?" + urlencode(exc.get_error_dict()))
            return HttpResponseRedirect(url)
        return super().post(request)


class GodModeSessionEndpoint(InstanceAdminUserSessionEndpoint):
    def get(self, request):
        if not is_god_mode_user(request.user):
            return Response({"is_authenticated": False}, status=status.HTTP_200_OK)
        return super().get(request)


# --- external invites switch --------------------------------------------------------------------
class GodModeExternalInvitesEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        return Response({"enabled": external_invites_enabled()})

    def patch(self, request):
        enabled = request.data.get("enabled") if isinstance(request.data, dict) else None
        if not isinstance(enabled, bool):
            return Response({"error": "enabled must be a boolean"}, status=status.HTTP_400_BAD_REQUEST)
        InstanceConfiguration.objects.update_or_create(
            key=EXTERNAL_INVITES_KEY,
            defaults={"value": "1" if enabled else "0", "category": "INVITES", "is_encrypted": False},
        )
        return Response({"enabled": enabled})
