"""Add the `buyout` acquisition source.

A bought floor is the fourth way a team comes to own a seat, next to a graded
attempt, an item takeover and a won duel. `choices` is Python-side only, so this
emits no SQL and touches no row.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0033_gamesettings_max_open_attempts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='occupancy',
            name='source',
            field=models.CharField(choices=[('attempt', 'تلاش'), ('item', 'آیتم'), ('duel', 'دوئل'), ('buyout', 'خرید')], default='attempt', max_length=16),
        ),
    ]
