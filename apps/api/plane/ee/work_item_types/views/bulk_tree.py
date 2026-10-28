from rest_framework import status
from rest_framework.response import Response

from plane.api.views.base import BaseAPIView as ExternalAPIView
from plane.app.permissions import ProjectMemberPermission
from plane.app.views.base import BaseAPIView
from plane.db.models import Project

from ..bulk_tree import apply_bulk_tree

MAX_ITEMS = 1000  # ponytail: one request, one transaction; raise if real imports need more


class BulkTreeMixin:
    """POST {"items": [{ref, type, name, parent_ref | parent_id, attribute_values, ...}]} (spec §7).
    Member+ (spec §12). 201 created / 200 dry-run ok / 400 with per-row errors.
    Keys other than ref/type/parent_ref/parent_id are passed to IssueCreateSerializer as-is.
    ?dry_run=true: ids in `created` come from a rolled-back transaction and do not exist."""

    permission_classes = [ProjectMemberPermission]

    def post(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if project is None:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
        items = request.data.get("items") if isinstance(request.data, dict) else None
        if not isinstance(items, list) or not items or len(items) > MAX_ITEMS:
            return Response(
                {"error": f"items must be a non-empty list of at most {MAX_ITEMS} rows"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not all(isinstance(item, dict) for item in items):
            return Response({"error": "each item must be an object"}, status=status.HTTP_400_BAD_REQUEST)
        dry_run = request.query_params.get("dry_run", "").lower() in ("1", "true", "yes")
        result = apply_bulk_tree(project, items, dry_run=dry_run, actor=request.user)
        if result["errors"]:
            code = status.HTTP_400_BAD_REQUEST
        else:
            code = status.HTTP_200_OK if dry_run else status.HTTP_201_CREATED
        return Response(result, status=code)


class BulkTreeEndpoint(BulkTreeMixin, BaseAPIView):
    pass


class BulkTreeAPIEndpoint(BulkTreeMixin, ExternalAPIView):
    """/api/v1 variant: API-key auth and throttling from the external BaseAPIView."""
