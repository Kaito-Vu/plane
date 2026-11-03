import uuid

from rest_framework import status
from rest_framework.response import Response

from plane.db.models import Issue, ProjectMember

from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.ee.models import AttributeValue
from plane.ee.work_item_types.tree_ops import subtree_count

MAX_BATCH = 200
_COLS = ("value_text", "value_number", "value_boolean", "value_datetime", "value_uuid", "value_option_id")


def _shape(rows) -> dict:
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
    return out


def _visible_issues(request, slug, project_id):
    """Issues as core issue read sees them: restricted guests only see their own issues."""
    issues = Issue.objects.filter(project_id=project_id, workspace__slug=slug)
    if ProjectMember.objects.filter(
        workspace__slug=slug,
        project_id=project_id,
        member=request.user,
        role=ROLE.GUEST.value,
        is_active=True,
        project__guest_view_all_features=False,
    ).exists():
        issues = issues.filter(created_by=request.user)
    return issues


def _visible_issue(request, slug, project_id, issue_id):
    return _visible_issues(request, slug, project_id).filter(pk=issue_id).first()


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
        return Response(_shape(rows))


class ProjectAttributeValuesEndpoint(BaseAPIView):
    """Values for many issues in one request ({issue_id: {attribute_id: value}}): list/spreadsheet columns."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER, ROLE.GUEST])
    def get(self, request, slug, project_id):
        try:
            ids = {uuid.UUID(i) for i in request.query_params.get("issue_ids", "").split(",") if i}
        except ValueError:
            return Response({"error": "Invalid issue_ids"}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > MAX_BATCH:
            return Response({"error": f"At most {MAX_BATCH} issue_ids"}, status=status.HTTP_400_BAD_REQUEST)
        visible = list(_visible_issues(request, slug, project_id).filter(pk__in=ids).values_list("pk", flat=True))
        rows = AttributeValue.objects.filter(
            project_id=project_id,
            issue_id__in=visible,
            attribute__is_active=True,
            attribute__deleted_at__isnull=True,
        ).select_related("attribute")
        by_issue: dict = {str(i): [] for i in visible}
        for row in rows:
            by_issue[str(row.issue_id)].append(row)
        return Response({issue_id: _shape(issue_rows) for issue_id, issue_rows in by_issue.items()})
