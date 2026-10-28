import uuid

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


_LIMITS = {"ref": 255, "type": 64, "name": 255, "parent_ref": 255}


class RowInvalid(Exception):
    pass


def _fill(row: ImportRow, payload: dict) -> None:
    """Known columns map to fields; every other key is merged into row.data (passed to IssueCreateSerializer).
    Raises RowInvalid on bad types/lengths/uuid. Setting parent_ref clears parent_id and vice versa."""
    if not isinstance(payload, dict):
        raise RowInvalid("row must be an object")
    for col, limit in _LIMITS.items():
        if col in payload:
            value = payload[col]
            if value is None and col == "parent_ref":
                pass
            elif not isinstance(value, str) or len(value) > limit:
                raise RowInvalid(f"{col} must be a string of at most {limit} characters")
    pid = payload.get("parent_id")
    if pid is not None:
        try:
            pid = uuid.UUID(str(pid)) if isinstance(pid, str) else None
        except ValueError:
            pid = None
        if pid is None:
            raise RowInvalid("parent_id must be a valid UUID")
    for col in ("ref", "type", "name"):
        if col in payload:
            setattr(row, col, payload[col])
    if payload.get("parent_ref"):
        row.parent_ref, row.parent_id = payload["parent_ref"], None
    elif pid is not None:
        row.parent_ref, row.parent_id = None, pid
    else:
        if "parent_ref" in payload:
            row.parent_ref = None
        if "parent_id" in payload:
            row.parent_id = None
    skip = (*_COLUMNS, "id", "errors", "data")
    row.data = {**row.data, **{k: v for k, v in payload.items() if k not in skip}}


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
        if batch.status == ImportBatch.COMMITTED:
            return _err("batch_already_committed", "Batch was already committed")
        rows = request.data.get("rows") if isinstance(request.data, dict) else request.data
        if not isinstance(rows, list) or not rows:
            return _err("invalid_rows", "Send a non-empty list of row objects")
        if batch.rows.count() + len(rows) > MAX_ITEMS:
            return _err("too_many_rows", f"A batch holds at most {MAX_ITEMS} rows")
        objs = []
        for index, payload in enumerate(rows):
            row = ImportRow(batch=batch, project_id=batch.project_id, workspace_id=batch.workspace_id)
            try:
                _fill(row, payload)
            except RowInvalid as exc:
                return _err("invalid_rows", f"Row {index}: {exc}", details={"index": index})
            objs.append(row)
        ImportRow.objects.bulk_create(objs)
        return Response([_row_data(r) for r in objs], status=status.HTTP_201_CREATED)


class ImportRowDetailEndpoint(_Base):
    def patch(self, request, slug, project_id, pk, row_id):
        batch = self.batch(slug, project_id, pk)
        row = batch.rows.filter(pk=row_id).first() if batch else None
        if row is None:
            return _not_found("Import row")
        if batch.status == ImportBatch.COMMITTED:
            return _err("batch_already_committed", "Batch was already committed")
        try:
            _fill(row, request.data)
        except RowInvalid as exc:
            return _err("invalid_rows", str(exc))
        row.errors = []
        row.save()
        return Response(_row_data(row))


class ImportValidateEndpoint(_Base):
    def post(self, request, slug, project_id, pk):
        batch = self.batch(slug, project_id, pk)
        if batch is None:
            return _not_found("Import batch")
        if batch.status == ImportBatch.COMMITTED:
            return _err("batch_already_committed", "Batch was already committed")
        if not batch.rows.exists():
            return _err("empty_batch", "Batch has no rows")
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
                return _err("empty_batch", "Batch has no rows")
            errors = validate_batch(batch, request.user)
            if errors:
                return _err("batch_invalid", "Fix invalid rows first", details={"errors": errors})
            result = commit_batch(batch, request.user)
            if result["errors"]:
                return _err("commit_failed", "Commit failed", details={"errors": result["errors"]})
        return Response(result, status=status.HTTP_201_CREATED)
