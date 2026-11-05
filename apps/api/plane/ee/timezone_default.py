"""Default timezone for new records is Asia/Ho_Chi_Minh (UTC+7), without touching core models/migrations."""

from django.db.models.signals import pre_save

from plane.db.models import Cycle, Project, User, Workspace

DEFAULT_TZ = "Asia/Ho_Chi_Minh"
# ponytail: can't tell an explicit "UTC" from the core default, so new rows created as UTC become UTC+7.
FIELDS = {User: "user_timezone", Workspace: "timezone", Project: "timezone", Cycle: "timezone"}


def _apply(sender, instance, **kwargs):
    field = FIELDS[sender]
    if instance._state.adding and getattr(instance, field) == "UTC":
        setattr(instance, field, DEFAULT_TZ)


def install():
    for model in FIELDS:
        pre_save.connect(_apply, sender=model, dispatch_uid=f"ee-default-tz-{model.__name__}")
