"""Price the duel table from the design doc, and shorten the rest window to 5.

`FloorReward.duel_cost` used to be `level.duel_factor * points` and nothing else.
The doc prices duels from a hand-written table that no single factor reproduces —
easy floor 1 is 4.00x its points, medium is 3.60x, hard floors run 3.60x, 3.56x
and 3.52x — so 0023 added `duel_cost_override` and this writes the doc's numbers
into it.

Only rows that have no override yet are touched, so re-running never clobbers a
number an organiser tuned in admin, and a level the doc does not price keeps
falling back to `duel_factor`.

`duel_cooldown_minutes` is moved 10 -> 5 the same way, and only where it is still
sitting on the old default. The field shipped in the original schema but nothing
ever read it until the duels app landed, so 10 was a placeholder rather than a
decision; 5 is what the rules sheet says. A row an organiser has already changed
to anything else is left exactly as they set it.
"""

from django.db import migrations

# (level, floor) -> what challenging that floor costs.
DUEL_COSTS = {
    ("easy", 1): 400,
    ("medium", 1): 720,
    ("medium", 2): 900,
    ("hard", 1): 1440,
    ("hard", 2): 1600,
    ("hard", 3): 1760,
}

OLD_COOLDOWN_DEFAULT = 10
NEW_COOLDOWN = 5


def seed(apps, schema_editor):
    FloorReward = apps.get_model("game", "FloorReward")
    for (level, floor), cost in DUEL_COSTS.items():
        FloorReward.objects.filter(
            level_id=level, floor=floor, duel_cost_override__isnull=True
        ).update(duel_cost_override=cost)

    GameSettings = apps.get_model("game", "GameSettings")
    GameSettings.objects.filter(duel_cooldown_minutes=OLD_COOLDOWN_DEFAULT).update(
        duel_cooldown_minutes=NEW_COOLDOWN
    )


def unseed(apps, schema_editor):
    """Put the overrides back to null and the cooldown back to its old default.

    Scoped to exactly the values this migration writes, so a number an organiser
    changed afterwards survives a rollback.
    """
    FloorReward = apps.get_model("game", "FloorReward")
    for (level, floor), cost in DUEL_COSTS.items():
        FloorReward.objects.filter(level_id=level, floor=floor, duel_cost_override=cost).update(
            duel_cost_override=None
        )

    GameSettings = apps.get_model("game", "GameSettings")
    GameSettings.objects.filter(duel_cooldown_minutes=NEW_COOLDOWN).update(
        duel_cooldown_minutes=OLD_COOLDOWN_DEFAULT
    )


class Migration(migrations.Migration):
    dependencies = [("game", "0023_floorreward_duel_cost_override_and_more")]
    operations = [migrations.RunPython(seed, unseed)]
