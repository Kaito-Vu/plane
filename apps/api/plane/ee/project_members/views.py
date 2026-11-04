from uuid import UUID

from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions.base import ROLE, allow_permission
from plane.app.views.project.member import ProjectMemberViewSet
from plane.db.models import ProjectMember, Workspace

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


class EeProjectMemberViewSet(ProjectMemberViewSet):
    """Project-first membership: adding/promoting a project member provisions the workspace row."""

    @allow_permission([ROLE.ADMIN])
    def create(self, request, slug, project_id):
        members = request.data.get("members", [])
        if not isinstance(members, list) or not members:
            return Response({"error": "At least one member is required"}, status=status.HTTP_400_BAD_REQUEST)

        # canonicalize ids and dedupe (last occurrence wins) before anything reads them
        by_id = {}
        try:
            for m in members:
                if not isinstance(m, dict):
                    raise UserNotEligible(NOT_ELIGIBLE_MESSAGE)
                try:
                    cid = str(UUID(str(m.get("member_id"))))
                except ValueError:
                    raise UserNotEligible(NOT_ELIGIBLE_MESSAGE)
                by_id.pop(cid, None)
                by_id[cid] = {**m, "member_id": cid}
            entries = list(by_id.values())
            users = {str(u.id): u for u in eligible_users(list(by_id))}
        except UserNotEligible as exc:
            return _error(str(exc), "USER_NOT_ELIGIBLE")
        if not all(_valid_role(e.get("role", 5)) for e in entries):
            return Response({"error": "Invalid role"}, status=status.HTTP_400_BAD_REQUEST)
        request.data["members"] = entries

        workspace = Workspace.objects.get(slug=slug)
        with transaction.atomic():
            for e in entries:
                provision_workspace_member(workspace, users[e["member_id"]], e.get("role", 5))
            response = super().create(request, slug=slug, project_id=project_id)
            if response.status_code >= 400:
                transaction.set_rollback(True)  # core refused (e.g. ws Admin target): undo provisioning
        return response

    @allow_permission([ROLE.ADMIN])
    def partial_update(self, request, slug, project_id, pk):
        role = request.data.get("role")
        target = (
            ProjectMember.objects.filter(pk=pk, workspace__slug=slug, project_id=project_id, is_active=True)
            .select_related("workspace", "member")
            .first()
        )
        if not _valid_role(role) or target is None:
            return super().partial_update(request, slug=slug, project_id=project_id, pk=pk)

        with transaction.atomic():
            provision_workspace_member(target.workspace, target.member, role)
            response = super().partial_update(request, slug=slug, project_id=project_id, pk=pk)
            if response.status_code >= 400:
                transaction.set_rollback(True)
        return response
