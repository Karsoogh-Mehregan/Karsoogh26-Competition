"""Add the `toll` balance reason on top of `event`.

Two branches each added a reason to the same field and each generated a `0007`,
which leaves the graph with two leaves. This linearises them: `event` came in on
main, `toll` goes after it, and the field ends up listing every reason the model
declares. `choices` is Python-side only, so neither migration emits SQL and the
order is a bookkeeping question, not a data one.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("teams", "0007_event_balance_reason")]

    operations = [
        migrations.AlterField(
            model_name="balanceevent",
            name="reason",
            field=models.CharField(
                choices=[
                    ("initial", "موجودی اولیه"),
                    ("entry", "رزرو خانه"),
                    ("toll", "عوارضی"),
                    ("grade", "نمره خانه"),
                    ("event", "رویداد"),
                ],
                max_length=16,
            ),
        ),
    ]
