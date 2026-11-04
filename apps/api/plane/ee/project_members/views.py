import logging
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.throttling import UserRateThrottle
from rest_framework.response import Response

from plane.app.permissions.base import ROLE, allow_permission
from plane.app.views.project.base import ProjectViewSet
from plane.app.views.project.member import ProjectMemberViewSet
from plane.app.views.base import BaseAPIView
from plane.api.views.member import ProjectMemberListCreateAPIEndpoint
from plane.db.models import ProjectMember, User, Workspace, WorkspaceMember

from .permissions import is_workspace_admin
from .services import (
    NOT_ELIGIBLE_MESSAGE,
    PROJECT_TO_WORKSPACE_ROLE,
    UserNotEligible,
    eligible_users,
    provision_workspace_member,
)


def _valid_role(role):
    return isinstance(role, int) and role in PROJECT_TO_WORKSPACE_ROLE


def _error(message, code, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"error": message, "code": code}, status=http_status)


def _canonical_id(raw):
    try:
        return str(UUID(str(raw)))
    except ValueError:
        raise UserNotEligible(NOT_ELIGIBLE_MESSAGE)


def _reject_unsafe_add(actor, slug, project_id, member_ids, roles):
    """POST only adds: core would otherwise rewrite roles of existing members and let non-ws-admins mint admins."""
    if ProjectMember.objects.filter(project_id=project_id, member_id__in=member_ids, is_active=True).exists():
        return _error("Member is already in the project; change roles with PATCH", "ALREADY_MEMBER")
    if ROLE.ADMIN.value in roles and not is_workspace_admin(actor, slug):
        return _error("Only workspace admins can add project admins", "ROLE_NOT_ALLOWED")
    return None


class EeProjectMemberListCreateAPIEndpoint(ProjectMemberListCreateAPIEndpoint):
    """v1 member create: provision the workspace row first, else core rejects non-workspace users."""

    def post(self, request, slug, project_id):
        data = request.data
        if not isinstance(data, dict):
            return _error(NOT_ELIGIBLE_MESSAGE, "USER_NOT_ELIGIBLE")
        role = data.get("role", 5)
        try:
            (user,) = eligible_users([_canonical_id(data.get("member"))])
        except UserNotEligible as exc:
            return _error(str(exc), "USER_NOT_ELIGIBLE")
        if not _valid_role(role):
            return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
        rejected = _reject_unsafe_add(request.user, slug, project_id, [str(user.id)], [role])
        if rejected:
            return rejected

        workspace = Workspace.objects.get(slug=slug)
        with transaction.atomic():
            provision_workspace_member(workspace, user, role)
            response = super().post(request, slug=slug, project_id=project_id)
            if response.status_code >= 400:
                transaction.set_rollback(True)
        return response


class EeProjectMemberViewSet(ProjectMemberViewSet):
    """Project-first membership: adding/promoting a project member provisions the workspace row."""

    @allow_permission([ROLE.ADMIN])
    def create(self, request, slug, project_id):
        if not isinstance(request.data, dict):
            return _error(NOT_ELIGIBLE_MESSAGE, "USER_NOT_ELIGIBLE")
        members = request.data.get("members", [])
        if not isinstance(members, list) or not members:
            return Response({"error": "At least one member is required"}, status=status.HTTP_400_BAD_REQUEST)

        # canonicalize ids and dedupe (last occurrence wins) before anything reads them
        by_id = {}
        try:
            for m in members:
                if not isinstance(m, dict):
                    raise UserNotEligible(NOT_ELIGIBLE_MESSAGE)
                cid = _canonical_id(m.get("member_id"))
                by_id.pop(cid, None)
                by_id[cid] = {**m, "member_id": cid}
            entries = list(by_id.values())
            users = {str(u.id): u for u in eligible_users(list(by_id))}
        except UserNotEligible as exc:
            return _error(str(exc), "USER_NOT_ELIGIBLE")
        if not all(_valid_role(e.get("role", 5)) for e in entries):
            return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
        rejected = _reject_unsafe_add(request.user, slug, project_id, list(by_id), [e.get("role", 5) for e in entries])
        if rejected:
            return rejected
        request.data["members"] = entries

        workspace = Workspace.objects.get(slug=slug)
        with transaction.atomic():
            # sorted order: concurrent admins lock WorkspaceMember rows in the same order (no deadlock)
            for e in sorted(entries, key=lambda e: e["member_id"]):
                provision_workspace_member(workspace, users[e["member_id"]], e.get("role", 5))
            response = super().create(request, slug=slug, project_id=project_id)
            if response.status_code >= 400:
                transaction.set_rollback(True)  # core refused (e.g. ws Admin target): undo provisioning
        return response


logger = logging.getLogger(__name__)


class MemberSearchThrottle(UserRateThrottle):
    rate = "30/min"
    scope = "ee_member_search"


def _mask_email(email):
    if not email:
        return ""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


class ProjectMemberSearchEndpoint(BaseAPIView):
    """Project admin searches existing users to add; emails are masked, results capped."""

    throttle_classes = [MemberSearchThrottle]

    @allow_permission([ROLE.ADMIN])
    def get(self, request, slug, project_id):
        q = request.query_params.get("q", "").strip()
        if len(q) < 3:
            return Response({"error": "Query must be at least 3 characters"}, status=status.HTTP_400_BAD_REQUEST)
        if chr(0) in q:  # NUL bytes crash the DB driver
            return Response({"error": "Invalid query"}, status=status.HTTP_400_BAD_REQUEST)
        logger.info("member search slug=%s project_id=%s actor=%s qlen=%d", slug, project_id, request.user.id, len(q))

        users = (
            User.objects.filter(is_active=True, is_bot=False)
            .filter(Q(email__icontains=q) | Q(display_name__icontains=q))
            .exclude(id__in=ProjectMember.objects.filter(project_id=project_id, is_active=True).values("member_id"))
            .order_by("email")[:10]
        )
        users = list(users)
        # target's ACTIVE role in THIS workspace (null when none); the modal offers only legal project roles from it
        ws_roles = dict(
            WorkspaceMember.objects.filter(
                workspace__slug=slug, is_active=True, member_id__in=[u.id for u in users]
            ).values_list("member_id", "role")
        )
        return Response(
            [
                {
                    "id": u.id,
                    "display_name": u.display_name,
                    "avatar_url": u.avatar_url,
                    "email": _mask_email(u.email),
                    "workspace_role": ws_roles.get(u.id),
                }
                for u in users
            ]
        )


class EeProjectViewSet(ProjectViewSet):
    """Only workspace admins create projects."""

    def create(self, request, slug):
        if not is_workspace_admin(request.user, slug):
            return Response({"error": "Only workspace admins can create projects"}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, slug=slug)
