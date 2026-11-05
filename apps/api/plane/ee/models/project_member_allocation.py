from django.db import models

from plane.db.models.base import BaseModel


class ProjectMemberAllocation(BaseModel):
    """Allocation window of a project member. Informational: an ended window does not revoke access."""

    project_member = models.OneToOneField(
        "db.ProjectMember", on_delete=models.CASCADE, related_name="allocation"
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)  # null = open-ended

    class Meta:
        db_table = "project_member_allocations"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__isnull=True)
                | models.Q(start_date__isnull=True)
                | models.Q(end_date__gte=models.F("start_date")),
                name="project_member_allocation_end_gte_start",
            )
        ]
