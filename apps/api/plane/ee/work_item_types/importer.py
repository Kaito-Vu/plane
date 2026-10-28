"""Two-step import (spec §7): rows are staged in ImportRow, validated and committed via apply_bulk_tree.

Validation is a bulk-tree dry run, so staging rows face exactly the same gate as real issue writes."""

from plane.ee.models import ImportBatch, ImportRow

from .bulk_tree import BulkTreeResult, RowError, apply_bulk_tree


def _items(batch: ImportBatch) -> list[dict]:
    items = []
    for row in batch.rows.all():
        item = {**row.data, "ref": row.ref, "type": row.type, "name": row.name}
        if row.parent_ref:
            item["parent_ref"] = row.parent_ref
        if row.parent_id is not None:
            item["parent_id"] = str(row.parent_id)
        items.append(item)
    return items


def validate_batch(batch: ImportBatch, actor) -> list[RowError]:
    result = apply_bulk_tree(batch.project, _items(batch), dry_run=True, actor=actor)
    by_ref: dict[str, list[RowError]] = {}
    for error in result["errors"]:
        by_ref.setdefault(error["ref"], []).append(error)
    rows = list(batch.rows.all())
    for row in rows:
        row.errors = by_ref.get(row.ref, [])
    ImportRow.objects.bulk_update(rows, ["errors"])
    return result["errors"]


def commit_batch(batch: ImportBatch, actor) -> BulkTreeResult:
    result = apply_bulk_tree(batch.project, _items(batch), dry_run=False, actor=actor)
    batch.status = ImportBatch.FAILED if result["errors"] else ImportBatch.COMMITTED
    batch.save(update_fields=["status", "updated_at"])
    return result
