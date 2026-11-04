from django.db import migrations


def delete_all_invites(apps, schema_editor):
    # Hard delete (incl. already soft-deleted rows): _base_manager is never the soft-delete manager
    # and _raw_delete skips the soft-delete override and signals.
    for label in ("WorkspaceMemberInvite", "ProjectMemberInvite"):
        apps.get_model("db", label)._base_manager.all()._raw_delete(schema_editor.connection.alias)


class Migration(migrations.Migration):
    dependencies = [
        ("ee", "0003_god_mode_superuser_backfill"),
        ("db", "0125_reset_project_deploy_board_identity"),
    ]

    operations = [migrations.RunPython(delete_all_invites, migrations.RunPython.noop)]
