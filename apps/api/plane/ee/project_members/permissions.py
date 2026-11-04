from plane.app.permissions.project import ProjectBasePermission
from plane.db.models import WorkspaceMember
from plane.db.models.project import ROLE

_original_has_permission = None


def is_workspace_admin(user, slug):
    return WorkspaceMember.objects.filter(
        workspace__slug=slug, member=user, role=ROLE.ADMIN.value, is_active=True
    ).exists()


def _has_permission(self, request, view):
    # POST without project_id in the URL is project creation (the only such POST using this class).
    if request.method == "POST" and not getattr(view, "kwargs", {}).get("project_id"):
        if request.user.is_anonymous or not is_workspace_admin(request.user, view.workspace_slug):
            return False
    return _original_has_permission(self, request, view)


def install():
    """Only workspace admins create projects (public API v1). Idempotent."""
    global _original_has_permission
    if _original_has_permission is None:
        _original_has_permission = ProjectBasePermission.has_permission
        ProjectBasePermission.has_permission = _has_permission
