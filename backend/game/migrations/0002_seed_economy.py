"""Seed the economy from the design doc's scoring table.

get_or_create, so re-running never clobbers values organisers have tuned in
admin. Map topology (Node/Edge) is deliberately not seeded here.
"""

from decimal import Decimal

from django.db import migrations

# level -> (capacity, entry_cost, networth_base, networth_factor, duel_factor)
LEVELS = {
    "spawn": (1, 0, 0, "0.00", "0.00"),
    "easy": (1, 20, 30, "0.10", "2.00"),
    "medium": (2, 50, 75, "0.20", "1.80"),
    "hard": (3, 100, 150, "0.30", "1.50"),
}

# level -> {floor: points}
FLOORS = {
    "easy": {1: 100},
    "medium": {1: 200, 2: 250},
    "hard": {1: 400, 2: 450, 3: 500},
}

# Linear by default; add breakpoints in admin to bend the curve.
GRADE_CURVE = {0: "0.000", 50: "0.500", 100: "1.000"}


def seed(apps, schema_editor):
    LevelConfig = apps.get_model("game", "LevelConfig")
    FloorReward = apps.get_model("game", "FloorReward")
    GradeMultiplier = apps.get_model("game", "GradeMultiplier")

    for level, (cap, entry, nw_base, nw_factor, duel) in LEVELS.items():
        LevelConfig.objects.get_or_create(
            level=level,
            defaults={
                "capacity": cap,
                "entry_cost": entry,
                "networth_base": nw_base,
                "networth_factor": Decimal(nw_factor),
                "duel_factor": Decimal(duel),
                "buyout_factor": Decimal("4.00"),
            },
        )

    for level, floors in FLOORS.items():
        for floor, points in floors.items():
            FloorReward.objects.get_or_create(
                level_id=level, floor=floor, defaults={"points": points}
            )

    for grade, factor in GRADE_CURVE.items():
        GradeMultiplier.objects.get_or_create(grade=grade, defaults={"factor": Decimal(factor)})


def unseed(apps, schema_editor):
    apps.get_model("game", "FloorReward").objects.all().delete()
    apps.get_model("game", "GradeMultiplier").objects.filter(grade__in=GRADE_CURVE).delete()
    apps.get_model("game", "LevelConfig").objects.filter(level__in=LEVELS).delete()


class Migration(migrations.Migration):
    dependencies = [("game", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
