"""Seed the DuelMentors group so `judge_duel` is grantable from admin on day one.

Same shape as `game/0004_seed_mentor_group` and `notifications/0003_notifier_group`,
and for the same reason: permissions are normally written by a post_migrate
signal that has not fired while this migration runs, so the row has to be forced
into existence first. `create_permissions` early-returns on a falsy
`models_module`, and the historical AppConfigStub has none — hence the shim.

The group starts empty, deliberately. Judging a duel is a job someone is given
on the day; it is not implied by grading questions or by running the clock, and
nobody should acquire it as a side effect of a migration. Put people in it from
the admin, then give each of them a Room — a judge with no room never enters the
rotation, because picking a judge means picking a meeting to send teams to.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

GROUP_NAME = "DuelMentors"
CODENAME = "judge_duel"


def _ensure_permissions(apps, schema_editor):
    app_config = apps.get_app_config("duels")
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
        codename=CODENAME, content_type__app_label="duels", content_type__model="duel"
    )
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(permission)


def unseed(apps, schema_editor):
    # Drop the group, not the permission: 0001 owns the permission's lifecycle.
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("duels", "0001_initial"),
        ("auth", "__first__"),
        ("contenttypes", "__first__"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
