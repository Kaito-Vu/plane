from django.db.models.signals import pre_save
from django.dispatch import receiver

from plane.db.models import Issue
from plane.db.models.state import StateGroup

from .validators import check_hierarchy


@receiver(pre_save, sender=Issue, dispatch_uid="ee_work_item_types_issue_pre_save")
def enforce_hierarchy(sender, instance: Issue, raw=False, **kwargs):
    # ponytail: untyped issues are skipped here (type_required is enforced by the serializer gate);
    # QuerySet.update/bulk_create bypass pre_save entirely (spec §13.16).
    if raw or instance.type_id is None or instance.is_draft or instance.deleted_at is not None:
        return
    if instance.state_id is not None and instance.state.group == StateGroup.TRIAGE.value:
        return
    check_hierarchy(
        instance.type,
        instance.parent,
        None if instance._state.adding else instance.id,
        instance.project_id,
        triage=False,
    )
