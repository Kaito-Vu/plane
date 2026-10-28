from django.db import models

from plane.db.models.project import ProjectBaseModel


class AttributeValue(ProjectBaseModel):
    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="attribute_values")
    attribute = models.ForeignKey("ee.Attribute", on_delete=models.CASCADE, related_name="values")
    value_text = models.TextField(null=True, blank=True)
    value_number = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)
    value_datetime = models.DateTimeField(null=True, blank=True)
    value_uuid = models.UUIDField(null=True, blank=True)
    value_option = models.ForeignKey(
        "ee.AttributeOption", null=True, blank=True, on_delete=models.CASCADE, related_name="values"
    )

    class Meta:
        db_table = "attribute_values"
        indexes = [
            models.Index(fields=["attribute", "value_number"], name="attrval_number_idx"),
            models.Index(fields=["attribute", "value_option"], name="attrval_option_idx"),
            models.Index(fields=["attribute", "value_uuid"], name="attrval_uuid_idx"),
            models.Index(fields=["issue", "attribute"], name="attrval_issue_attr_idx"),
        ]
