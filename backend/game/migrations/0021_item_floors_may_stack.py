"""Allow stacked item floors on one house.

`occ_one_unit_per_team` remains the attempt rule: a team still cannot reserve
the same node twice. Gel needs one active Occupancy per `FloorReward` on that
node's level, which the old partial unique forbade. This only loosens the
index condition; no rows are rewritten.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0020_occupancy_item_takeover_reason"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="occupancy",
            name="occ_one_unit_per_team",
        ),
        migrations.AddConstraint(
            model_name="occupancy",
            constraint=models.UniqueConstraint(
                condition=models.Q(("released_at__isnull", True), ("source", "attempt")),
                fields=("team", "node"),
                name="occ_one_unit_per_team",
            ),
        ),
    ]
