from celery import shared_task

from .services import sweep_orphan_workspace_members


@shared_task
def ee_sweep_orphan_workspace_members() -> int:
    return sweep_orphan_workspace_members()
