"""Hand `send_announcement` to the GameGods group.

Same shape as `game/migrations/0004_seed_mentor_group.py`: the permission row is
written by a post_migrate signal that has not fired while this migration runs,
so it must be forced into existence first. `create_permissions` early-returns on
a falsy `models_module`, and the historical AppConfigStub has none — hence the
shim.

No new group. The people already trusted to start and stop the event are the
obvious first holders, and announcing is not destructive enough to deserve its
own roster; anyone else gets the permission from the admin, individually or
through a group of their own.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "GameGods"
CODENAME = "send_announcement"


def _ensure_permissions(apps, schema_editor):
    app_config = apps.get_app_config("notifications")
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
        codename=CODENAME,
        content_type__app_label="notifications",
        content_type__model="message",
    )
    # The group is game's to create; if the game migrations have not run here
    # there is nobody to grant it to yet, and the admin can do it by hand.
    group = Group.objects.filter(name=GROUP_NAME).first()
    if group is not None:
        group.permissions.add(permission)


def unseed(apps, schema_editor):
    # Only take the grant back: the permission row belongs to 0001's model.
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")

    group = Group.objects.filter(name=GROUP_NAME).first()
    permission = Permission.objects.filter(
        codename=CODENAME, content_type__app_label="notifications"
    ).first()
    if group is not None and permission is not None:
        group.permissions.remove(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0001_initial"),
        ("game", "0011_game_god_group"),
        ("auth", "__first__"),
        ("contenttypes", "__first__"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
