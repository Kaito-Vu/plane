from django.db import migrations, models


def disable_telemetry(apps, schema_editor):
    apps.get_model("license", "Instance").objects.update(is_telemetry_enabled=False)


class Migration(migrations.Migration):

    dependencies = [
        ("license", "0006_instance_is_current_version_deprecated"),
    ]

    operations = [
        migrations.AlterField(
            model_name="instance",
            name="is_telemetry_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(disable_telemetry, migrations.RunPython.noop),
    ]
