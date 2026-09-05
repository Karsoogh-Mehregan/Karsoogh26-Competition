"""Add the `weak_reasoning` balance reason: a mentor zero-grade that also
takes 10% of the team's wallet. `choices` is Python-side only, so this emits
no SQL.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("teams", "0011_balance_reason_buyout"),
    ]

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
                    ("duel", "دوئل"),
                    ("buyout", "خرید طبقه"),
                    ("weak_reasoning", "عدم ارائه"),
                ],
                max_length=16,
            ),
        ),
    ]
