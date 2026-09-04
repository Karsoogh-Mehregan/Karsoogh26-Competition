"""The economy table, in the shape the models now hold it.

0002/0007/0024/0026 seeded the same numbers through the old factor columns, and
0031 froze the derived ones into `FloorReward`. This states the whole table once
against the current schema: get_or_create, so a value an organiser tuned in admin
survives, and a re-run is a no-op.

It is also what `conftest._reseed_after_flush` calls to put the economy back for
a `transaction=True` test, which is why the earlier seeds cannot serve — they
write columns that no longer exist.
"""

from decimal import Decimal

from django.db import migrations

# level -> (capacity, entry_cost)
LEVELS = {
    "spawn": (1, 0),
    "easy": (1, 20),
    "medium": (2, 50),
    "hard": (3, 100),
    "toll": (1, 30),
    "center": (3, 100),
}

# (level, floor) -> (points, networth, duel_cost, buyout_cost)
FLOORS = {
    ("easy", 1): (100, 40, 400, 400),
    ("medium", 1): (200, 115, 720, 800),
    ("medium", 2): (250, 125, 900, 1000),
    ("hard", 1): (400, 270, 1440, 1600),
    ("hard", 2): (450, 285, 1600, 1800),
    ("hard", 3): (500, 300, 1760, 2000),
    ("center", 1): (400, 270, 600, 1600),
    ("center", 2): (450, 285, 675, 1800),
    ("center", 3): (500, 300, 750, 2000),
}

GRADE_CURVE = {0: "0.000", 50: "0.500", 100: "1.000"}


def seed(apps, schema_editor):
    LevelConfig = apps.get_model("game", "LevelConfig")
    FloorReward = apps.get_model("game", "FloorReward")
    GradeMultiplier = apps.get_model("game", "GradeMultiplier")

    for level, (capacity, entry_cost) in LEVELS.items():
        LevelConfig.objects.get_or_create(
            level=level, defaults={"capacity": capacity, "entry_cost": entry_cost}
        )

    for (level, floor), (points, networth, duel_cost, buyout_cost) in FLOORS.items():
        FloorReward.objects.get_or_create(
            level_id=level,
            floor=floor,
            defaults={
                "points": points,
                "networth": networth,
                "duel_cost": duel_cost,
                "buyout_cost": buyout_cost,
            },
        )

    for grade, factor in GRADE_CURVE.items():
        GradeMultiplier.objects.get_or_create(grade=grade, defaults={"factor": Decimal(factor)})


class Migration(migrations.Migration):
    dependencies = [("game", "0031_floorreward_costs")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
