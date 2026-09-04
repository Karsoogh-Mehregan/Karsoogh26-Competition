"""Move `send_announcement` off GameGods and onto a group of its own.

0002 seeded the permission onto GameGods on the reasoning that whoever runs the
event is the obvious first announcer. That conflated two jobs: running the clock
and speaking to the hall are different responsibilities, held by different people
on the day. **Notifier** is now the roster for the second one.

GameGods loses the grant, and members are deliberately *not* carried across —
the point of the split is that being a game god is no longer a licence to write
into everyone's inbox. The group starts empty; put people in it from the admin,
or with `manage.py shell`. A game god who should also announce goes in both.

Superusers still pass `CanSendAnnouncement` implicitly, as they do every other
permission check; the group is about who is *given* the job, not who could force
their way past it.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

NEW_GROUP = "Notifier"
OLD_GROUP = "GameGods"
CODENAME = "send_announcement"


def _ensure_permissions(apps, schema_editor):
    app_config = apps.get_app_config("notifications")
    app_config.models_module = True
    try:
        create_permissions(app_config, apps=apps, using=schema_editor.connection.alias, verbosity=0)
    finally:
        app_config.models_module = None


def _permission(apps):
    return apps.get_model("auth", "Permission").objects.get(
        codename=CODENAME,
        content_type__app_label="notifications",
        content_type__model="message",
    )


def seed(apps, schema_editor):
    _ensure_permissions(apps, schema_editor)

    Group = apps.get_model("auth", "Group")
    permission = _permission(apps)

    notifier, _ = Group.objects.get_or_create(name=NEW_GROUP)
    notifier.permissions.add(permission)

    game_gods = Group.objects.filter(name=OLD_GROUP).first()
    if game_gods is not None:
        game_gods.permissions.remove(permission)


def unseed(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    permission = _permission(apps)

    game_gods = Group.objects.filter(name=OLD_GROUP).first()
    if game_gods is not None:
        game_gods.permissions.add(permission)
    # Drop the group, not the permission: 0001 owns the permission's lifecycle.
    Group.objects.filter(name=NEW_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_seed_announcer_permission"),
        ("auth", "__first__"),
        ("contenttypes", "__first__"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
