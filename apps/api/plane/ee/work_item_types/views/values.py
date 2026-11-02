from rest_framework import status
from rest_framework.response import Response

from plane.db.models import Issue, ProjectMember

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.ee.models import AttributeValue
from plane.ee.work_item_types.tree_ops import subtree_count

_COLS = ("value_text", "value_number", "value_boolean", "value_datetime", "value_uuid", "value_option_id")


def _visible_issue(request, slug, project_id, issue_id):
    """The issue as core issue read sees it: restricted guests only see their own issues."""
    issues = Issue.objects.filter(pk=issue_id, project_id=project_id, workspace__slug=slug)
    if ProjectMember.objects.filter(
        workspace__slug=slug,
        project_id=project_id,
        member=request.user,
        role=ROLE.GUEST.value,
        is_active=True,
        project__guest_view_all_features=False,
    ).exists():
        issues = issues.filter(created_by=request.user)
    return issues.first()


class IssueSubtreeCountEndpoint(BaseAPIView):
    """Descendants (all levels, live, excluding the issue) a delete/archive would take along."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        issue = _visible_issue(request, slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"count": subtree_count(issue, for_archive=request.query_params.get("for") == "archive")})


class IssueAttributeValuesEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id, issue_id):
        if _visible_issue(request, slug, project_id, issue_id) is None:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)
        rows = AttributeValue.objects.filter(
            workspace__slug=slug,
            project_id=project_id,
            issue_id=issue_id,
            attribute__is_active=True,
            attribute__deleted_at__isnull=True,
        ).select_related("attribute")
        out: dict = {}
        for row in rows:
            col = next((c for c in _COLS if getattr(row, c) is not None), None)
            if col is None:
                continue
            value = getattr(row, col)
            key = str(row.attribute_id)
            if row.attribute.field_type in ("multi_select", "multi_member"):
                out.setdefault(key, []).append(value)
            else:
                out[key] = value
        return Response(out)
