"""Add the `networth` balance reason: the end-of-game settlement that pays each
team `FloorReward.networth` for every floor it still holds. `choices` is
Python-side only, so this emits no SQL.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0013_merge_20260905_1232"),
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
                    ("networth", "ارزش دارایی"),
                ],
                max_length=16,
            ),
        ),
    ]
