from django.apps import AppConfig


class EeConfig(AppConfig):
    name = "plane.ee"
    label = "ee"

    def ready(self):
        from .work_item_types import signals  # noqa: F401
        from .god_mode import access

        access.install()
        from .project_members import permissions

        permissions.install()

        from . import timezone_default

        timezone_default.install()

        from celery.schedules import crontab

        from plane.celery import app

        from .project_members import signals as project_member_signals, tasks  # noqa: F401  (tasks: not covered by autodiscover)

        app.conf.beat_schedule["ee-sweep-orphan-workspace-members"] = {
            "task": "plane.ee.project_members.tasks.ee_sweep_orphan_workspace_members",
            "schedule": crontab(minute=0),
        }
