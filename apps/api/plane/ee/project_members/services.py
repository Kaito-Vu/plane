"""Keep WorkspaceMember rows in step with project membership (project-first membership)."""

import uuid
from typing import Iterable

from django.db import transaction
from django.db.models import Exists, F, OuterRef

from plane.db.models import ProjectMember, User, Workspace, WorkspaceMember

PROJECT_TO_WORKSPACE_ROLE: dict[int, int] = {20: 15, 15: 15, 5: 5}

WS_ADMIN = 20


NOT_ELIGIBLE_MESSAGE = "One or more users cannot be added"


class UserNotEligible(Exception):
    """A user id is malformed, unknown, inactive or a bot (one message for every cause)."""


def eligible_users(user_ids: Iterable[str]) -> list[User]:
    ids = []
    for raw in user_ids:
        try:
            ids.append(uuid.UUID(str(raw)))
        except (ValueError, AttributeError, TypeError):
            raise UserNotEligible(NOT_ELIGIBLE_MESSAGE)
    ids = list(dict.fromkeys(ids))
    users = list(User.objects.filter(id__in=ids, is_active=True, is_bot=False))
    if len(users) != len(ids):
        raise UserNotEligible(NOT_ELIGIBLE_MESSAGE)
    return users


def provision_workspace_member(workspace: Workspace, user: User, project_role: int) -> WorkspaceMember:
    """Create/reactivate the workspace row. Never lowers an active role; never grants Admin."""
    # unknown/malformed project roles clamp to Guest (least privilege); row validity is core's concern
    role = PROJECT_TO_WORKSPACE_ROLE.get(project_role, 5) if isinstance(project_role, int) else 5
    with transaction.atomic():
        # get_or_create is race-safe on first creation (savepoint + re-get on IntegrityError)
        wm, created = WorkspaceMember.objects.get_or_create(
            workspace=workspace, member=user, defaults={"role": role}
        )
        if created:
            return wm
        wm = WorkspaceMember.objects.select_for_update().get(pk=wm.pk)
        if not wm.is_active:
            wm.is_active = True
            wm.role = role
            wm.save(update_fields=["is_active", "role", "updated_at"])
        return wm


def deprovision_if_orphan(workspace_id, user_id) -> bool:
    """Disable the workspace row when the user has no live active project membership."""
    with transaction.atomic():
        wm = (
            WorkspaceMember.objects.select_for_update()
            .select_related("workspace")
            .filter(workspace_id=workspace_id, member_id=user_id, is_active=True)
            .first()
        )
        if wm is None or wm.role == WS_ADMIN or wm.workspace.owner_id == wm.member_id:
            return False
        if ProjectMember.objects.filter(
            workspace_id=workspace_id,
            member_id=user_id,
            is_active=True,
            project__deleted_at__isnull=True,
        ).exists():
            return False
        wm.is_active = False
        wm.save(update_fields=["is_active", "updated_at"])
        return True


def sweep_orphan_workspace_members() -> int:
    """Disable every orphaned workspace row; deprovision rechecks each under lock."""
    live = ProjectMember.objects.filter(
        workspace_id=OuterRef("workspace_id"),
        member_id=OuterRef("member_id"),
        is_active=True,
        project__deleted_at__isnull=True,
    )
    candidates = (
        WorkspaceMember.objects.filter(is_active=True)
        .exclude(role=WS_ADMIN)
        .exclude(member_id=F("workspace__owner_id"))
        .annotate(has_live=Exists(live))
        .filter(has_live=False)
        .values_list("workspace_id", "member_id")
    )
    return sum(deprovision_if_orphan(w, m) for w, m in list(candidates))
