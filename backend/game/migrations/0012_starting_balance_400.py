"""Move the starting balance to 400 — the doc's 200+200, for every team.

`AlterField` in 0011 only changed the default for *new* rows; the singleton
GameSettings row was created earlier and still holds 500.

Guarded on the old default so a value organisers have tuned in admin is left
alone: this rewrites config that was never deliberately set, nothing else.
"""

from django.db import migrations

OLD_DEFAULT = 500
NEW_DEFAULT = 400


def set_balance(apps, schema_editor):
    apps.get_model("game", "GameSettings").objects.filter(initial_balance=OLD_DEFAULT).update(
        initial_balance=NEW_DEFAULT
    )


def unset_balance(apps, schema_editor):
    apps.get_model("game", "GameSettings").objects.filter(initial_balance=NEW_DEFAULT).update(
        initial_balance=OLD_DEFAULT
    )


class Migration(migrations.Migration):
    dependencies = [("game", "0011_entry_retry_same_question")]
    operations = [migrations.RunPython(set_balance, unset_balance)]
