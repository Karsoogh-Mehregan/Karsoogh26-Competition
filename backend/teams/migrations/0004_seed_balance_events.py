from django.db import migrations


def seed_existing_balances(apps, schema_editor):
    """Snapshot current wallets so a merge onto main does not wipe history.

    Existing Team rows stay as they are. Teams that already have a log
    (this branch was applied earlier) are skipped; everyone else with a
    non-zero balance gets one `initial` event so the panel is not empty.
    """
    Team = apps.get_model("teams", "Team")
    BalanceEvent = apps.get_model("teams", "BalanceEvent")
    already = set(BalanceEvent.objects.values_list("team_id", flat=True))
    events = [
        BalanceEvent(
            team=team,
            delta=team.balance,
            balance_after=team.balance,
            reason="initial",
            detail="",
        )
        for team in Team.objects.exclude(pk__in=already).exclude(balance=0)
    ]
    if events:
        BalanceEvent.objects.bulk_create(events)


def unseed_existing_balances(apps, schema_editor):
    apps.get_model("teams", "BalanceEvent").objects.filter(reason="initial").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("teams", "0003_balance_events"),
    ]

    operations = [
        migrations.RunPython(seed_existing_balances, unseed_existing_balances),
    ]
