"""Add the `buyout` balance reason: the price paid for a floor and the floor's
points handed to the buyer. `choices` is Python-side only, so this emits no SQL.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('teams', '0010_team_board'),
    ]

    operations = [
        migrations.AlterField(
            model_name='balanceevent',
            name='reason',
            field=models.CharField(choices=[('initial', 'موجودی اولیه'), ('entry', 'رزرو خانه'), ('toll', 'عوارضی'), ('grade', 'نمره خانه'), ('event', 'رویداد'), ('duel', 'دوئل'), ('buyout', 'خرید طبقه')], max_length=16),
        ),
    ]
