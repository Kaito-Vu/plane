from django.db import models

from plane.db.models.project import ProjectBaseModel


class ImportBatch(ProjectBaseModel):
    DRAFT, COMMITTED, FAILED = "draft", "committed", "failed"
    status = models.CharField(max_length=20, default=DRAFT, choices=[(s, s) for s in (DRAFT, COMMITTED, FAILED)])

    class Meta:
        db_table = "import_batches"


class ImportRow(ProjectBaseModel):
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    ref = models.CharField(max_length=255, blank=True, default="")
    type = models.CharField(max_length=64, blank=True, default="")
    parent_ref = models.CharField(max_length=255, null=True, blank=True)
    parent_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255, blank=True, default="")
    data = models.JSONField(default=dict, blank=True)
    errors = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "import_rows"
        ordering = ("created_at",)
