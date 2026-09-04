"""Join the duel-pricing branch to the centre-level branch.

Both forked from `0022_question_body_optional_answer_type_default` and never
touched the same field, so there is nothing to reconcile and no operations here:

* `0023_floorreward_duel_cost_override_and_more` … `0025_alter_gamesettings_…`
  added `FloorReward.duel_cost_override`, the `duel` acquisition source, and the
  duel cooldown/deadline help text.
* `0023_merge_…` … `0026_seed_center_level` added `Question.max_grade`, the
  `partial_grade` release reason, and the `center` level with its own economy.

The one thing worth knowing about the combination: `0024_seed_duel_costs` writes
the design doc's duel price table onto `easy`/`medium`/`hard` only, and `center`
is seeded afterwards by `0026` with no override — so it is the single tier whose
duel price still comes from `level.duel_factor`.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0025_alter_gamesettings_duel_cooldown_minutes_and_more"),
        ("game", "0026_seed_center_level"),
    ]

    operations = []
