from django.db import models

from plane.db.models.base import BaseModel
from plane.db.models.project import ProjectBaseModel

from .template import FIELD_TYPES


class Attribute(ProjectBaseModel):
    issue_type = models.ForeignKey("db.IssueType", on_delete=models.CASCADE, related_name="attributes")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    system_key = models.CharField(max_length=64, null=True, blank=True)
    default_value = models.JSONField(null=True, blank=True)
    sort_order = models.FloatField(default=65535)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "attributes"
        ordering = ("sort_order", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["project", "issue_type", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="attribute_unique_name_when_deleted_at_null",
            )
        ]


class AttributeOption(BaseModel):
    attribute = models.ForeignKey(Attribute, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=255)
    sort_order = models.FloatField(default=65535)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "attribute_options"
        ordering = ("sort_order", "created_at")
