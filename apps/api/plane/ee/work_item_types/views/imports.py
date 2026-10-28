from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

from plane.app.permissions import ProjectMemberPermission
from plane.app.views.base import BaseAPIView
from plane.db.models import Project
from plane.ee.models import ImportBatch, ImportRow

from ..importer import commit_batch, validate_batch
from .bulk_tree import MAX_ITEMS

_COLUMNS = ("ref", "type", "parent_ref", "parent_id", "name")


def _err(code, message, http=status.HTTP_400_BAD_REQUEST, details=None):
    return Response({"error_code": code, "message": message, "details": details or {}}, status=http)


def _not_found(what):
    return _err("not_found", f"{what} not found", status.HTTP_404_NOT_FOUND)


def _row_data(row: ImportRow) -> dict:
    return {
        "id": str(row.id),
        "ref": row.ref,
        "type": row.type,
        "parent_ref": row.parent_ref,
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "name": row.name,
        "data": row.data,
        "errors": row.errors,
    }


def _fill(row: ImportRow, payload: dict) -> None:
    """Known columns map to fields; every other key is merged into row.data (passed to IssueCreateSerializer)."""
    for col in _COLUMNS:
        if col in payload:
            setattr(row, col, payload[col])
    extra = {k: v for k, v in payload.items() if k not in _COLUMNS and k not in ("id", "errors")}
    row.data = {**row.data, **extra}


class _Base(BaseAPIView):
    permission_classes = [ProjectMemberPermission]

    def batch(self, slug, project_id, pk):
        return ImportBatch.objects.filter(pk=pk, project_id=project_id, project__workspace__slug=slug).first()


class ImportBatchEndpoint(_Base):
    def post(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if project is None:
            return _not_found("Project")
        batch = ImportBatch.objects.create(project=project, workspace_id=project.workspace_id)
        return Response({"id": str(batch.id), "status": batch.status}, status=status.HTTP_201_CREATED)


class ImportRowsEndpoint(_Base):
    def post(self, request, slug, project_id, pk):
        batch = self.batch(slug, project_id, pk)
        if batch is None:
            return _not_found("Import batch")
        if batch.status != ImportBatch.DRAFT:
            return _err("batch_already_committed", "Batch is not a draft")
        rows = request.data.get("rows") if isinstance(request.data, dict) else request.data
        if not isinstance(rows, list) or not rows or not all(isinstance(r, dict) for r in rows):
            return _err("invalid_rows", "Send a non-empty list of row objects")
        if batch.rows.count() + len(rows) > MAX_ITEMS:
            return _err("too_many_rows", f"A batch holds at most {MAX_ITEMS} rows")
        objs = []
        for payload in rows:
            row = ImportRow(batch=batch, project_id=batch.project_id, workspace_id=batch.workspace_id)
            _fill(row, payload)
            objs.append(row)
        ImportRow.objects.bulk_create(objs)
        return Response([_row_data(r) for r in objs], status=status.HTTP_201_CREATED)


class ImportRowDetailEndpoint(_Base):
    def patch(self, request, slug, project_id, pk, row_id):
        batch = self.batch(slug, project_id, pk)
        row = batch.rows.filter(pk=row_id).first() if batch else None
        if row is None:
            return _not_found("Import row")
        if batch.status != ImportBatch.DRAFT:
            return _err("batch_already_committed", "Batch is not a draft")
        if not isinstance(request.data, dict):
            return _err("invalid_rows", "Send a row object")
        _fill(row, request.data)
        row.errors = []
        row.save()
        return Response(_row_data(row))


class ImportValidateEndpoint(_Base):
    def post(self, request, slug, project_id, pk):
        batch = self.batch(slug, project_id, pk)
        if batch is None:
            return _not_found("Import batch")
        errors = validate_batch(batch, request.user)
        return Response({"valid": not errors, "errors": errors})


class ImportCommitEndpoint(_Base):
    def post(self, request, slug, project_id, pk):
        with transaction.atomic():
            batch = (
                ImportBatch.objects.select_for_update()
                .filter(pk=pk, project_id=project_id, project__workspace__slug=slug)
                .first()
            )
            if batch is None:
                return _not_found("Import batch")
            if batch.status == ImportBatch.COMMITTED:
                return _err("batch_already_committed", "Batch was already committed")
            if not batch.rows.exists():
                return _err("invalid_rows", "Batch has no rows")
            errors = validate_batch(batch, request.user)
            if errors:
                return _err("batch_invalid", "Fix invalid rows first", details={"errors": errors})
            result = commit_batch(batch, request.user)
        return Response(result, status=status.HTTP_201_CREATED)
