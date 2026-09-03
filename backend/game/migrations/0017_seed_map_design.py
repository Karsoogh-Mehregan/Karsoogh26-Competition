"""Seed the eight neighbourhoods, the MapDesign row, and the Designers group.

Same shape as 0011_seed_game_god_group: the permission row is written by a
post_migrate signal that has not fired while this migration runs, so it is
forced into existence first. Neighbourhoods use get_or_create on `index`, so a
colour a Designer has already picked in admin is never clobbered by a re-run.
"""

from django.contrib.auth.management import create_permissions
from django.db import migrations

from game.design import DEFAULT_NEIGHBORHOODS

GROUP_NAME = "Designers"
CODENAME = "design_map"


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
    Neighborhood = apps.get_model("game", "Neighborhood")
    MapDesign = apps.get_model("game", "MapDesign")

    permission = Permission.objects.get(
        codename=CODENAME, content_type__app_label="game", content_type__model="mapdesign"
    )
    group, _ = Group.objects.get_or_create(name=GROUP_NAME)
    group.permissions.add(permission)

    for index, name, theme, color in DEFAULT_NEIGHBORHOODS:
        Neighborhood.objects.get_or_create(
            index=index, defaults={"name": name, "theme": theme, "color": color}
        )

    MapDesign.objects.get_or_create(pk=1)


def unseed(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name=GROUP_NAME).delete()
    apps.get_model("game", "Neighborhood").objects.all().delete()
    apps.get_model("game", "MapDesign").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0016_map_design"),
        ("auth", "__first__"),
        ("contenttypes", "__first__"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
