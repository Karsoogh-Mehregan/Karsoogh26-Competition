"""Turn the charity bag into the two-account minority game the rules describe.

Teams no longer pick "contribute" or "request": they put money into either the
mice account (موش‌گیل‌ها) or the lions account (شیرگیل‌ها), and the account
holding *less* money wins the other one. The columns are renamed to match, and
existing rows are carried across on the mapping the old semantics imply — the
requesters were the side paid when the bag succeeded, so `request` becomes
`lions` and `charity_succeeded=True` becomes a lions win; `contribute` becomes
`mice`. Nothing is deleted; a settled bag keeps its totals and its winner.

`winning_side` is nullable on a finished bag on purpose: a tie, or an account
nobody joined, refunds every stake and names no winner.
"""

from django.db import migrations, models
from django.db.models import CheckConstraint, Q

_SIDES = [("mice", "موش‌گیل‌ها"), ("lions", "شیرگیل‌ها")]
_EVENT_CODES = [
    ("territory_control", "نبرد قلمرو"),
    ("charity_bag", "مؤسسه خیریه"),
    ("centipede", "بازی هزارپا"),
    ("olympics_coin", "سکه نزدیک دیوار"),
    ("olympics_marble", "تیله هدف"),
    ("limited_auction", "حراج محدود"),
    ("prize_wheel", "گردونه شانس"),
    ("pig", "بازی خوک"),
]
_ACTION_TO_SIDE = {"contribute": "mice", "request": "lions"}


def set_sides(apps, schema_editor):
    participation = apps.get_model("events", "CharityBagParticipation")
    for action, side in _ACTION_TO_SIDE.items():
        participation.objects.filter(side=action).update(side=side)

    event = apps.get_model("events", "CharityBagEvent")
    event.objects.filter(charity_succeeded=True).update(winning_side="lions")
    event.objects.filter(charity_succeeded=False).update(winning_side="mice")


def unset_sides(apps, schema_editor):
    participation = apps.get_model("events", "CharityBagParticipation")
    for action, side in _ACTION_TO_SIDE.items():
        participation.objects.filter(side=side).update(side=action)

    event = apps.get_model("events", "CharityBagEvent")
    event.objects.filter(winning_side="lions").update(charity_succeeded=True)
    event.objects.filter(winning_side="mice").update(charity_succeeded=False)


class Migration(migrations.Migration):
    dependencies = [("events", "0010_event_board")]

    operations = [
        migrations.RemoveConstraint(
            model_name="charitybagevent",
            name="charity_bag_settlement_state_consistent",
        ),
        migrations.RenameField(
            model_name="charitybagevent",
            old_name="total_contributed",
            new_name="total_mice",
        ),
        migrations.RenameField(
            model_name="charitybagevent",
            old_name="total_requested",
            new_name="total_lions",
        ),
        migrations.RenameField(
            model_name="charitybagparticipation",
            old_name="action",
            new_name="side",
        ),
        migrations.AddField(
            model_name="charitybagevent",
            name="minimum_stake",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="charitybagevent",
            name="freeze_seconds",
            field=models.PositiveIntegerField(default=180),
        ),
        migrations.AddField(
            model_name="charitybagevent",
            name="winning_side",
            field=models.CharField(blank=True, choices=_SIDES, max_length=8, null=True),
        ),
        migrations.AlterField(
            model_name="charitybagparticipation",
            name="side",
            field=models.CharField(choices=_SIDES, max_length=8),
        ),
        migrations.RunPython(set_sides, unset_sides),
        migrations.RemoveField(model_name="charitybagevent", name="charity_succeeded"),
        migrations.AddConstraint(
            model_name="charitybagevent",
            constraint=CheckConstraint(
                condition=(
                    Q(
                        status__in=["scheduled", "active", "resolving"],
                        winning_side__isnull=True,
                        settled_at__isnull=True,
                    )
                    | Q(status="finished", settled_at__isnull=False)
                ),
                name="charity_bag_settlement_state_consistent",
            ),
        ),
        migrations.AlterField(
            model_name="eventconfiguration",
            name="code",
            field=models.CharField(choices=_EVENT_CODES, max_length=32, unique=True),
        ),
        migrations.AlterField(
            model_name="matchmakingticket",
            name="event_code",
            field=models.CharField(choices=_EVENT_CODES, max_length=32),
        ),
    ]
