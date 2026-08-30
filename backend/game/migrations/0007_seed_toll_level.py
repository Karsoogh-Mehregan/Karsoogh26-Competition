"""Seed the `toll` level used by the C34/C45 connector nodes.

Toll nodes are pass-through: a team pays to cross, nothing is held and nothing is
scored. Deliberately no FloorReward rows, which is what keeps them inert for
questions and networth. `capacity` is 1 only because the model checks 1..3;
the real rule is "unlimited", and expressing that is a later change.

entry_cost is a placeholder for organisers to tune in admin, so get_or_create.
"""

from decimal import Decimal

from django.db import migrations

TOLL_ENTRY_COST = 30


def seed(apps, schema_editor):
    LevelConfig = apps.get_model("game", "LevelConfig")

    LevelConfig.objects.get_or_create(
        level="toll",
        defaults={
            "capacity": 1,
            "entry_cost": TOLL_ENTRY_COST,
            "networth_base": 0,
            "networth_factor": Decimal("0.00"),
            "duel_factor": Decimal("0.00"),
            "buyout_factor": Decimal("0.00"),
        },
    )


def unseed(apps, schema_editor):
    apps.get_model("game", "LevelConfig").objects.filter(level="toll").delete()


class Migration(migrations.Migration):
    dependencies = [("game", "0006_edge_direction_and_toll")]
    operations = [migrations.RunPython(seed, unseed)]
