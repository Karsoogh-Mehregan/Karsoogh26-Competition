"""Join the design-lock branch to the duel-pricing/centre-level trunk.

`0027_design_lock` only adds `GameSettings.design_locked`; the other leaf is
itself an empty merge. The two branches touch no common field, so there is
nothing to reconcile and no operations here.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0027_design_lock"),
        ("game", "0027_merge_20260904_2202"),
    ]

    operations = []
