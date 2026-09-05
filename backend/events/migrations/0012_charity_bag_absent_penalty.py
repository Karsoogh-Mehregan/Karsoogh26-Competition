"""Record what the absent teams were fined.

Split from `0011` rather than folded into it: that migration is already applied
on running databases, and editing an applied migration leaves the table without
the column while Django believes the change landed.

The default of 0 is correct for every existing row — bags settled before this
column existed charged no fine.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0011_charity_bag_two_accounts")]

    operations = [
        migrations.AddField(
            model_name="charitybagevent",
            name="absent_penalty_total",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
