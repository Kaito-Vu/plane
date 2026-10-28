from django.db import models

from plane.db.models.base import BaseModel

FIELD_TYPES = [
    (t, t)
    for t in (
        "text",
        "textarea",
        "number",
        "boolean",
        "date",
        "datetime",
        "url",
        "select",
        "multi_select",
        "member",
        "multi_member",
    )
]


class AttributeTemplate(BaseModel):
    """Workspace-level library entry; applying it copies into a project Attribute."""

    workspace = models.ForeignKey("db.Workspace", on_delete=models.CASCADE, related_name="attribute_templates")
    issue_type = models.ForeignKey("db.IssueType", on_delete=models.CASCADE, related_name="attribute_templates")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES)
    is_required = models.BooleanField(default=False)
    default_value = models.JSONField(null=True, blank=True)
    sort_order = models.FloatField(default=65535)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "attribute_templates"
        ordering = ("sort_order", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "issue_type", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="attr_template_unique_name_when_deleted_at_null",
            )
        ]


class AttributeTemplateOption(BaseModel):
    template = models.ForeignKey(AttributeTemplate, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=255)
    sort_order = models.FloatField(default=65535)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "attribute_template_options"
        ordering = ("sort_order", "created_at")
