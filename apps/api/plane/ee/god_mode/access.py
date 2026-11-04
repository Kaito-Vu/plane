from django.db.models.signals import post_save
from django.dispatch import receiver

from plane.license.models import Instance, InstanceAdmin


def is_god_mode_user(user):
    """Active, non-bot superuser who is also a role-20 instance admin."""
    if user is None or user.is_anonymous or user.is_bot or not (user.is_active and user.is_superuser):
        return False
    instance = Instance.objects.first()
    return InstanceAdmin.objects.filter(role=20, instance=instance, user=user).exists()


@receiver(post_save, sender=InstanceAdmin)
def grant_superuser(sender, instance, **kwargs):
    # Covers sign-up, the admins API and the create_instance_admin command without touching them.
    if instance.role == 20 and instance.user_id:
        type(instance.user).objects.filter(pk=instance.user_id).update(is_superuser=True, is_staff=True)


def install():
    """Make every core endpoint guarded by InstanceAdminPermission require the god-mode rule."""
    from plane.license.api.permissions.instance import InstanceAdminPermission

    InstanceAdminPermission.has_permission = lambda self, request, view: is_god_mode_user(request.user)
