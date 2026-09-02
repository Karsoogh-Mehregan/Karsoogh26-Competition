"""Seed the GameGods group so `control_game` is grantable from admin on day one.

Same shape as 0004_seed_mentor_group: the permission row is written by a
post_migrate signal that has not fired while this migration runs, so it must be
forced into existence first. `create_permissions` early-returns on a falsy
`models_module`, and the historical AppConfigStub has none — hence the shim.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "GameGods"
CODENAME = "control_game"


def _ensure_permissions(apps, schema_editor):
    app_config = apps.get_app_config("game")
    app_config.models_module = True
    try:
        create_permissions(app_config, apps=apps, using=schema_editor.connection.alias, verbosity=0)
    finally:
        app_config.models_module = None


def seed(apps, schema_editor):
    _ensure_permissions(apps, schema_editor)

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    permission = Permission.objects.get(
        codename=CODENAME, content_type__app_label="game", content_type__model="gamesettings"
    )
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(permission)


def unseed(apps, schema_editor):
    # Drop the group, not the permission: 0010 owns the permission's lifecycle.
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0010_game_god_permission"),
        ("auth", "__first__"),
        ("contenttypes", "__first__"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
