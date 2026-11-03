from celery import shared_task


@shared_task
def soft_delete_issues_related(issue_ids: list[str]) -> None:
    """Fan-out of core's per-issue soft-delete cascade for a whole subtree: one broker message, not one per issue."""
    from plane.bgtasks.deletion_task import soft_delete_related_objects

    for pk in issue_ids:
        soft_delete_related_objects("db", "issue", pk)  # direct call: runs inline in this worker


@shared_task
def log_issues_activity(issue_ids: list[str], activity: dict) -> None:
    """One issue_activity per cascaded issue, produced inside the worker."""
    from plane.bgtasks.issue_activities_task import issue_activity  # bgtasks import views; keep lazy

    for pk in issue_ids:
        requested = activity["requested"]
        issue_activity(
            type=activity["type"],
            requested_data=_dumps({**requested, "issue_id": pk} if activity["type"].endswith("deleted") else requested),
            actor_id=activity["actor_id"],
            issue_id=pk,
            project_id=activity["project_id"],
            current_instance=_dumps(activity["current"]) if activity["current"] is not None else None,
            epoch=activity["epoch"],
        )


def _dumps(value) -> str:
    import json

    return json.dumps(value)
