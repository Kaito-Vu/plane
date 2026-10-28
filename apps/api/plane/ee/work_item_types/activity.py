from plane.db.models import IssueActivity
from plane.ee.models import Attribute

from .value_codec import _as_uuid


def track_attribute_values(
    requested_data, current_instance, issue_id, project_id, workspace_id, actor_id, issue_activities, epoch
):
    """`attribute.updated`: one activity per attribute written in the PATCH/POST body."""
    raw = requested_data.get("attribute_values") or {}
    if not isinstance(raw, dict):
        return
    values = {}
    for k, v in raw.items():
        try:
            values[_as_uuid(k)] = v  # canonical key: "ABC..." / unhyphenated ids match too
        except (ValueError, AttributeError, TypeError):
            continue
    names = dict(Attribute.objects.filter(project_id=project_id, id__in=list(values)).values_list("id", "name"))
    for attr_id, name in names.items():
        value = values.get(attr_id)
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
