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
