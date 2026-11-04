from django.db import migrations


def backfill(apps, schema_editor):
    InstanceAdmin = apps.get_model("license", "InstanceAdmin")
    User = apps.get_model("db", "User")
    ids = list(InstanceAdmin.objects.filter(role=20, user__isnull=False).values_list("user_id", flat=True))
    User.objects.filter(id__in=ids).update(is_superuser=True, is_staff=True)


class Migration(migrations.Migration):
    dependencies = [
        ("ee", "0002_import_staging"),
        ("license", "0006_instance_is_current_version_deprecated"),
        ("db", "0125_reset_project_deploy_board_identity"),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
