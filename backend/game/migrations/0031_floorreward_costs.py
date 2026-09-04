"""Move the economy's derived numbers onto FloorReward as plain columns.

`networth`, `duel_cost` and `buyout_cost` were properties computed from
`LevelConfig.networth_base`/`networth_factor`/`duel_factor`/`buyout_factor`.
No single factor reproduced the design doc's tables — `duel_cost_override`
already existed for exactly that reason — so the number itself is now the
column and the factors are gone.

Backfill writes what the properties returned, so every existing row keeps the
price it had; a floor whose override was empty gets `duel_factor * points`
frozen into the column. The factor columns are dropped only after that.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations, models


def _round_half_up(value):
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def backfill(apps, schema_editor):
    FloorReward = apps.get_model("game", "FloorReward")
    for reward in FloorReward.objects.select_related("level"):
        level = reward.level
        reward.networth = level.networth_base + _round_half_up(
            level.networth_factor * reward.points
        )
        reward.buyout_cost = _round_half_up(level.buyout_factor * reward.points)
        if reward.duel_cost is None:
            reward.duel_cost = _round_half_up(level.duel_factor * reward.points)
        reward.save(update_fields=["networth", "duel_cost", "buyout_cost"])


class Migration(migrations.Migration):
    dependencies = [("game", "0030_leaderboard_frozen")]

    operations = [
        migrations.AddField(
            model_name="floorreward",
            name="networth",
            field=models.IntegerField(
                default=0, help_text="End-of-game value of holding this floor."
            ),
        ),
        migrations.AddField(
            model_name="floorreward",
            name="buyout_cost",
            field=models.PositiveIntegerField(
                default=0, help_text="What buying this floor out from its holder costs."
            ),
        ),
        migrations.RenameField(
            model_name="floorreward", old_name="duel_cost_override", new_name="duel_cost"
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="floorreward",
            name="duel_cost",
            field=models.PositiveIntegerField(
                default=0, help_text="What challenging this floor costs the attacker."
            ),
        ),
        migrations.RemoveField(model_name="levelconfig", name="networth_base"),
        migrations.RemoveField(model_name="levelconfig", name="networth_factor"),
        migrations.RemoveField(model_name="levelconfig", name="duel_factor"),
        migrations.RemoveField(model_name="levelconfig", name="buyout_factor"),
    ]
