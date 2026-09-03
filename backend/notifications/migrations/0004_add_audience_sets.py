"""Widen the audience from one target to a set of them.

`audience` + `audience_team` + `audience_user` could say "one team" or "one
person" but never "these four teams", and never "these teams *and* every
mentor". The replacement is a union: a set of named scopes, plus an explicit
list of teams, plus an explicit list of people.

This migration only adds and backfills; 0005 drops the old columns, so a
deploy that stops here still reads correctly.
"""

from django.conf import settings
from django.db import migrations, models

# The single-target audiences map onto a one-element list; the broad ones were
# already scopes in all but name.
BROAD = {"all", "teams", "mentors", "designers"}


def widen(apps, schema_editor):
    Message = apps.get_model("notifications", "Message")

    for message in Message.objects.all().iterator():
        if message.audience in BROAD:
            message.scopes = [message.audience]
            message.save(update_fields=["scopes"])
        elif message.audience == "team" and message.audience_team_id:
            message.scopes = []
            message.save(update_fields=["scopes"])
            message.teams.add(message.audience_team_id)
        elif message.audience == "user" and message.audience_user_id:
            message.scopes = []
            message.save(update_fields=["scopes"])
            message.users.add(message.audience_user_id)


def narrow(apps, schema_editor):
    """Best effort: a message addressed to several teams cannot be expressed by
    the single-target columns, so it collapses onto the first one."""
    Message = apps.get_model("notifications", "Message")

    for message in Message.objects.all().iterator():
        scopes = message.scopes or []
        team = message.teams.first()
        user = message.users.first()
        if scopes:
            message.audience = scopes[0]
            message.audience_team = None
            message.audience_user = None
        elif team is not None:
            message.audience = "team"
            message.audience_team = team
        elif user is not None:
            message.audience = "user"
            message.audience_user = user
        else:
            message.audience = "all"
        message.save(update_fields=["audience", "audience_team", "audience_user"])


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_notifier_group'),
        ('teams', '0002_team_color'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='scopes',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='message',
            name='teams',
            field=models.ManyToManyField(blank=True, help_text='Named teams, on top of whatever the scopes already cover.', related_name='targeted_messages', to='teams.team'),
        ),
        migrations.AddField(
            model_name='message',
            name='users',
            field=models.ManyToManyField(blank=True, help_text='Named people, on top of whatever the scopes already cover.', related_name='targeted_messages', to=settings.AUTH_USER_MODEL),
        ),
        migrations.RunPython(widen, narrow),
    ]
