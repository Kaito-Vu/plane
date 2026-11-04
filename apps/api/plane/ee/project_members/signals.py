from django.db.models.signals import post_save
from django.dispatch import receiver

from plane.db.models import ProjectMember

from .services import deprovision_if_orphan, provision_workspace_member


@receiver(post_save, sender=ProjectMember, dispatch_uid="ee_project_member_sync_workspace_member")
def sync_workspace_member(sender, instance, created, **kwargs):
    if not instance.is_active:
        deprovision_if_orphan(instance.workspace_id, instance.member_id)
    elif created and instance.member.is_active and not instance.member.is_bot:
        # safety net only; routine saves must not resurrect suspended ws members; ineligible users skipped
        provision_workspace_member(instance.workspace, instance.member, instance.role)
