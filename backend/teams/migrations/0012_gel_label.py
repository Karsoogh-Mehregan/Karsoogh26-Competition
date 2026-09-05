"""Spell the gel item «گِل», so the backpack does not read as «flower».

`choices` is Python-side only, so this emits no SQL and touches no row.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0011_balance_reason_buyout"),
    ]

    operations = [
        migrations.AlterField(
            model_name="teamitem",
            name="item_type",
            field=models.CharField(
                choices=[
                    ("fake_document", "سند جعلی"),
                    ("gel", "گِل"),
                    ("gilari_100", "۱۰۰ گیلاری"),
                ],
                max_length=16,
            ),
        ),
    ]
