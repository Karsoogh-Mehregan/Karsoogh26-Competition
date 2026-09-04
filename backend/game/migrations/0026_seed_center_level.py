"""Seed the `center` level and move the CENTER node onto it.

Economy copies `hard` (the tier CENTER sat on until now), so nothing about the
board's value changes with this split — the level exists so the centre can be
tuned on its own, and organisers do that in admin. Questions are not seeded:
`center` starts with an empty pool, so stock it before a team can reach CENTER.

The node move refuses while a team holds a seat there. Capacity and entry cost
hang off `Node.level`, so repointing an occupied node would reprice a floor a
team already paid for — the same reason the Designer's tier move returns 409.
"""

from decimal import Decimal

from django.db import migrations

CENTER = "center"
LEVEL = {
    "capacity": 3,
    "entry_cost": 100,
    "networth_base": 150,
    "networth_factor": Decimal("0.30"),
    "duel_factor": Decimal("1.50"),
    "buyout_factor": Decimal("4.00"),
}
FLOORS = {1: 400, 2: 450, 3: 500}


def seed(apps, schema_editor):
    LevelConfig = apps.get_model("game", "LevelConfig")
    FloorReward = apps.get_model("game", "FloorReward")
    Node = apps.get_model("game", "Node")
    Occupancy = apps.get_model("game", "Occupancy")

    LevelConfig.objects.get_or_create(level=CENTER, defaults=LEVEL)
    for floor, points in FLOORS.items():
        FloorReward.objects.get_or_create(level_id=CENTER, floor=floor, defaults={"points": points})

    stuck = Occupancy.objects.filter(node__code="CENTER", released_at__isnull=True).exclude(
        node__level_id=CENTER
    )
    if stuck.exists():
        raise RuntimeError(
            "CENTER is occupied; release its seats in admin, then re-run this migration. "
            "Repointing an occupied node would reprice a floor a team already paid for."
        )
    Node.objects.filter(code="CENTER").update(level_id=CENTER)


def unseed(apps, schema_editor):
    apps.get_model("game", "Node").objects.filter(code="CENTER").update(level_id="hard")
    apps.get_model("game", "FloorReward").objects.filter(level_id=CENTER).delete()
    apps.get_model("game", "LevelConfig").objects.filter(level=CENTER).delete()


class Migration(migrations.Migration):
    dependencies = [("game", "0025_center_level_choice")]
    operations = [migrations.RunPython(seed, unseed)]
