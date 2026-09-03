"""Louder sector colours and a stronger wash, for rows still on the first-cut defaults.

The 8% wash of the first seed read as grey on the map. Same guard as
0012_starting_balance_400: only values nobody deliberately set are rewritten,
so a Designer's own colours survive.
"""

from django.db import migrations, models

from game.design import (
    DEFAULT_HALO_STRENGTH,
    DEFAULT_NEIGHBORHOODS,
    DEFAULT_TINT_STRENGTH,
    LEGACY_HALO_STRENGTH,
    LEGACY_NEIGHBORHOOD_COLORS,
    LEGACY_TINT_STRENGTH,
)


def louder(apps, schema_editor):
    MapDesign = apps.get_model("game", "MapDesign")
    Neighborhood = apps.get_model("game", "Neighborhood")

    MapDesign.objects.filter(tint_strength=LEGACY_TINT_STRENGTH).update(
        tint_strength=DEFAULT_TINT_STRENGTH
    )
    MapDesign.objects.filter(halo_strength=LEGACY_HALO_STRENGTH).update(
        halo_strength=DEFAULT_HALO_STRENGTH
    )
    for index, _name, _theme, color in DEFAULT_NEIGHBORHOODS:
        Neighborhood.objects.filter(index=index, color=LEGACY_NEIGHBORHOOD_COLORS[index]).update(
            color=color
        )


def quieter(apps, schema_editor):
    MapDesign = apps.get_model("game", "MapDesign")
    Neighborhood = apps.get_model("game", "Neighborhood")
    MapDesign.objects.filter(tint_strength=DEFAULT_TINT_STRENGTH).update(
        tint_strength=LEGACY_TINT_STRENGTH
    )
    MapDesign.objects.filter(halo_strength=DEFAULT_HALO_STRENGTH).update(
        halo_strength=LEGACY_HALO_STRENGTH
    )
    for index, _name, _theme, color in DEFAULT_NEIGHBORHOODS:
        Neighborhood.objects.filter(index=index, color=color).update(
            color=LEGACY_NEIGHBORHOOD_COLORS[index]
        )


class Migration(migrations.Migration):
    dependencies = [("game", "0017_seed_map_design")]
    operations = [
        migrations.AlterField(
            model_name="mapdesign",
            name="tint_strength",
            field=models.PositiveSmallIntegerField(
                default=DEFAULT_TINT_STRENGTH,
                help_text="How strongly each sector is washed with its colour, 0–100.",
            ),
        ),
        migrations.AlterField(
            model_name="mapdesign",
            name="halo_strength",
            field=models.PositiveSmallIntegerField(
                default=DEFAULT_HALO_STRENGTH,
                help_text="Opacity of the neighbourhood ring around every node, 0–100.",
            ),
        ),
        migrations.RunPython(louder, quieter),
    ]
