from plane.db.models import IssueActivity
from plane.ee.models import Attribute
from plane.utils.uuid import is_valid_uuid


def track_attribute_values(
    requested_data, current_instance, issue_id, project_id, workspace_id, actor_id, issue_activities, epoch
):
    """`attribute.updated`: one activity per attribute written in the PATCH/POST body."""
    values = requested_data.get("attribute_values") or {}
    if not isinstance(values, dict):
        return
    names = dict(
        Attribute.objects.filter(
            project_id=project_id, id__in=[k for k in values if is_valid_uuid(str(k))]
        ).values_list("id", "name")
    )
    for attr_id, name in names.items():
        value = values.get(str(attr_id))
        # ponytail: old value is not captured (current_instance has no attribute values); add a snapshot if needed
        issue_activities.append(
            IssueActivity(
                issue_id=issue_id,
                actor_id=actor_id,
                verb="updated",
                field="attribute",
                old_value="",
                new_value=""
                if value is None
                else ", ".join(map(str, value))
                if isinstance(value, list)
                else str(value),
                new_identifier=attr_id,
                comment=f"updated {name} to",
                project_id=project_id,
                workspace_id=workspace_id,
                epoch=epoch,
            )
        )
