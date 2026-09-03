"""The inbox: who a message reaches, who may send one, and what stays private.

The audience rules are the part worth pinning hardest — a message addressed to
one team that lands in every inbox is not a bug you can take back mid-contest.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client
from django.utils import timezone

from game.services import events
from game.sse import build_frame
from notifications import services
from notifications.models import Audience, Message, MessageKind, MessageStatus, Notification
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()

INBOX_URL = "/api/notifications/"
READ_URL = "/api/notifications/read/"
READ_ALL_URL = "/api/notifications/read-all/"
MESSAGES_URL = "/api/messages/"
AUDIENCES_URL = "/api/messages/audiences/"


def message_url(pk: int) -> str:
    return f"/api/messages/{pk}/"


def send_url(pk: int) -> str:
    return f"/api/messages/{pk}/send/"


# ---- fixtures --------------------------------------------------------------


@pytest.fixture
def alpha():
    return Team.objects.create(code="alpha", name="Alpha", balance=400)


@pytest.fixture
def beta():
    return Team.objects.create(code="beta", name="Beta", balance=400)


@pytest.fixture
def alpha_user(alpha):
    return User.objects.create_user("alpha-user", password="x", team=alpha)


@pytest.fixture
def beta_user(beta):
    return User.objects.create_user("beta-user", password="x", team=beta)


@pytest.fixture
def mentor_user():
    user = User.objects.create_user("mentor", password="x")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


@pytest.fixture
def announcer():
    """A game god, who migration 0002 hands `send_announcement`."""
    user = User.objects.create_user("boss", password="x")
    user.groups.add(Group.objects.get(name="GameGods"))
    return user


def session(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def draft(**kwargs) -> Message:
    return Message.objects.create(
        title=kwargs.pop("title", "خبر"),
        body=kwargs.pop("body", "متن خبر"),
        **kwargs,
    )


# ---- audience resolution ---------------------------------------------------


def test_all_reaches_everyone(alpha_user, beta_user, mentor_user):
    delivered = services.send_message(draft(audience=Audience.ALL))

    assert delivered == 3
    assert Notification.objects.count() == 3


def test_teams_reaches_only_accounts_with_a_team(alpha_user, beta_user, mentor_user):
    services.send_message(draft(audience=Audience.TEAMS))

    assert set(Notification.objects.values_list("user__username", flat=True)) == {
        "alpha-user",
        "beta-user",
    }


def test_mentors_reaches_the_mentors_group(alpha_user, mentor_user):
    services.send_message(draft(audience=Audience.MENTORS))

    assert list(Notification.objects.values_list("user__username", flat=True)) == ["mentor"]


def test_a_superuser_is_not_swept_into_the_mentor_audience(mentor_user):
    """`has_perm` is True for every superuser; the audience must not be.

    An admin account that is not actually mentoring should not collect the
    mentors' notices — see the note on `services.users_with_perm`.
    """
    User.objects.create_superuser("root", password="x")

    services.send_message(draft(audience=Audience.MENTORS))

    assert list(Notification.objects.values_list("user__username", flat=True)) == ["mentor"]


def test_designers_reaches_nobody_until_the_permission_exists(alpha_user, mentor_user):
    """`design_map` ships with the designer work, which is not on this branch.

    Resolving it must be an empty audience, not a crash — the picker offers the
    option regardless.
    """
    assert services.send_message(draft(audience=Audience.DESIGNERS)) == 0


def test_designers_reaches_the_group_once_the_permission_is_there(alpha_user):
    permission = Permission.objects.create(
        codename="design_map",
        name="Can edit the map's look",
        content_type_id=Permission.objects.first().content_type_id,
    )
    designer = User.objects.create_user("designer", password="x")
    designer.user_permissions.add(permission)

    # The audience is keyed on app_label, so borrow whatever content type the
    # row above landed on rather than hardcoding one.
    services.DESIGNER_PERM = f"{permission.content_type.app_label}.design_map"
    try:
        delivered = services.send_message(draft(audience=Audience.DESIGNERS))
    finally:
        services.DESIGNER_PERM = "game.design_map"

    assert delivered == 1
    assert Notification.objects.get().user == designer


def test_team_audience_reaches_one_team(alpha_user, beta_user, alpha):
    services.send_message(draft(audience=Audience.TEAM, audience_team=alpha))

    assert Notification.objects.get().user == alpha_user


def test_user_audience_reaches_one_person(alpha_user, beta_user):
    services.send_message(draft(audience=Audience.USER, audience_user=beta_user))

    assert Notification.objects.get().user == beta_user


def test_the_sender_is_not_a_recipient(alpha_user, announcer):
    """A sent announcement belongs in the Sent box, not the author's own bell."""
    services.send_message(draft(audience=Audience.ALL, sender=announcer))

    assert list(Notification.objects.values_list("user__username", flat=True)) == ["alpha-user"]


def test_inactive_accounts_are_skipped(alpha_user, beta_user):
    beta_user.is_active = False
    beta_user.save(update_fields=["is_active"])

    assert services.send_message(draft(audience=Audience.ALL)) == 1


# ---- sending ---------------------------------------------------------------


def test_a_draft_delivers_nothing_until_it_is_sent(alpha_user):
    message = draft(audience=Audience.ALL)

    assert message.status == MessageStatus.DRAFT
    assert Notification.objects.count() == 0

    services.send_message(message)
    message.refresh_from_db()

    assert message.status == MessageStatus.SENT
    assert message.sent_at is not None
    assert Notification.objects.count() == 1


def test_sending_twice_does_not_duplicate(alpha_user):
    message = draft(audience=Audience.ALL)
    services.send_message(message)
    services.send_message(message)

    assert Notification.objects.count() == 1


def test_send_publishes_a_frame_addressed_to_its_recipients(
    alpha_user, beta_user, monkeypatch, django_capture_on_commit_callbacks
):
    calls = []
    monkeypatch.setattr(
        events,
        "publish",
        lambda kind, payload=None, *, recipients=None: calls.append((kind, payload, recipients)),
    )

    with django_capture_on_commit_callbacks(execute=True):
        services.send_message(draft(audience=Audience.USER, audience_user=beta_user))

    assert len(calls) == 1
    kind, payload, recipients = calls[0]
    assert kind == events.NOTIFICATION_CREATED
    assert recipients == [beta_user.pk]
    # Routing travels beside the payload, never inside it.
    assert "recipients" not in payload and "users" not in payload


def test_the_frame_only_reaches_the_users_it_names():
    frame = build_frame(
        b"1-0",
        {b"t": events.NOTIFICATION_CREATED.encode(), b"d": b"{}", b"u": b"7,9"},
    )

    assert frame.recipients == frozenset({7, 9})


def test_an_unaddressed_frame_reaches_everyone():
    assert build_frame(b"1-0", {b"t": b"board.graded", b"d": b"{}"}).recipients == frozenset()


# ---- the inbox API ---------------------------------------------------------


def test_inbox_shows_only_my_own(alpha_user, beta_user, alpha):
    services.send_message(draft(audience=Audience.TEAM, audience_team=alpha, title="فقط آلفا"))

    body = session(alpha_user).get(INBOX_URL).json()
    assert [row["title"] for row in body["results"]] == ["فقط آلفا"]
    assert body["unread"] == 1

    assert session(beta_user).get(INBOX_URL).json() == {"unread": 0, "total": 0, "results": []}


def test_inbox_card_carries_what_the_panel_renders(alpha_user, announcer):
    message = draft(audience=Audience.ALL, sender=announcer, sender_label="داور اصلی")
    services.send_message(message)

    row = session(alpha_user).get(INBOX_URL).json()["results"][0]

    assert row["sender"] == "داور اصلی"
    assert row["title"] == "خبر"
    assert row["excerpt"] == "متن خبر"
    assert row["is_read"] is False
    assert row["sent_at"] is not None


def test_excerpt_is_trimmed_but_the_body_is_whole(alpha_user):
    services.send_message(draft(audience=Audience.ALL, body="ب" * 400))

    row = session(alpha_user).get(INBOX_URL).json()["results"][0]

    assert len(row["excerpt"]) == 140
    assert row["excerpt"].endswith("…")
    assert len(row["body"]) == 400


def test_marking_read_drops_the_unread_count(alpha_user):
    services.send_message(draft(audience=Audience.ALL))
    client = session(alpha_user)
    notification_id = client.get(INBOX_URL).json()["results"][0]["id"]

    body = client.post(READ_URL, {"ids": [notification_id]}, content_type="application/json").json()

    assert body == {"marked": 1, "unread": 0}
    assert Notification.objects.get(pk=notification_id).read_at is not None


def test_marking_read_is_idempotent(alpha_user):
    services.send_message(draft(audience=Audience.ALL))
    client = session(alpha_user)
    notification_id = client.get(INBOX_URL).json()["results"][0]["id"]
    payload = {"ids": [notification_id]}

    client.post(READ_URL, payload, content_type="application/json")
    first_read = Notification.objects.get(pk=notification_id).read_at

    body = client.post(READ_URL, payload, content_type="application/json").json()

    assert body["marked"] == 0
    assert Notification.objects.get(pk=notification_id).read_at == first_read


def test_i_cannot_mark_someone_elses_notification_read(alpha_user, beta_user):
    services.send_message(draft(audience=Audience.ALL))
    theirs = Notification.objects.get(user=beta_user)

    body = (
        session(alpha_user)
        .post(READ_URL, {"ids": [theirs.pk]}, content_type="application/json")
        .json()
    )

    assert body["marked"] == 0
    theirs.refresh_from_db()
    assert theirs.read_at is None


def test_mark_all_read(alpha_user):
    for index in range(3):
        services.send_message(draft(audience=Audience.ALL, title=f"خبر {index}"))

    body = session(alpha_user).post(READ_ALL_URL).json()

    assert body == {"marked": 3, "unread": 0}


def test_unread_filter(alpha_user):
    services.send_message(draft(audience=Audience.ALL, title="یک"))
    services.send_message(draft(audience=Audience.ALL, title="دو"))
    client = session(alpha_user)
    first = client.get(INBOX_URL).json()["results"][-1]["id"]
    client.post(READ_URL, {"ids": [first]}, content_type="application/json")

    body = client.get(f"{INBOX_URL}?unread=true").json()

    assert [row["title"] for row in body["results"]] == ["دو"]


def test_the_inbox_needs_a_session():
    assert Client().get(INBOX_URL).status_code in (401, 403)


# ---- the composer ----------------------------------------------------------


def test_only_an_announcer_may_compose(alpha_user, mentor_user, announcer):
    payload = {"title": "خبر", "body": "متن", "audience": "all"}

    assert session(alpha_user).post(MESSAGES_URL, payload, "application/json").status_code == 403
    assert session(mentor_user).post(MESSAGES_URL, payload, "application/json").status_code == 403
    assert session(announcer).post(MESSAGES_URL, payload, "application/json").status_code == 201


def test_posting_saves_a_draft_and_delivers_nothing(announcer, alpha_user):
    response = session(announcer).post(
        MESSAGES_URL,
        {"title": "خبر", "body": "متن", "audience": "all"},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["status"] == "draft"
    # A draft still reports the reach it *would* have, so the composer can show it.
    assert response.json()["recipient_count"] == 1
    assert Notification.objects.count() == 0


def test_posting_with_send_true_delivers_at_once(announcer, alpha_user):
    response = session(announcer).post(
        MESSAGES_URL,
        {"title": "خبر", "body": "متن", "audience": "all", "send": True},
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["delivered"] == 1
    assert response.json()["message"]["status"] == "sent"


def test_sending_a_draft(announcer, alpha_user):
    client = session(announcer)
    message_id = client.post(
        MESSAGES_URL,
        {"title": "خبر", "body": "متن", "audience": "all"},
        content_type="application/json",
    ).json()["id"]

    body = client.post(send_url(message_id)).json()

    assert body["delivered"] == 1
    assert body["message"]["status"] == "sent"
    assert Notification.objects.filter(user=alpha_user).count() == 1


def test_a_sent_message_cannot_be_sent_again(announcer, alpha_user):
    client = session(announcer)
    message = draft(audience=Audience.ALL, sender=announcer)
    client.post(send_url(message.pk))

    assert client.post(send_url(message.pk)).status_code == 409


def test_a_sent_message_cannot_be_edited_or_deleted(announcer, alpha_user):
    """It is already in other people's inboxes; editing would rewrite history."""
    client = session(announcer)
    message = draft(audience=Audience.ALL, sender=announcer)
    services.send_message(message)

    edited = client.patch(
        message_url(message.pk), {"title": "دیگر"}, content_type="application/json"
    )

    assert edited.status_code == 409
    assert client.delete(message_url(message.pk)).status_code == 409


def test_a_draft_can_be_edited_and_discarded(announcer):
    client = session(announcer)
    message = draft(audience=Audience.ALL, sender=announcer)

    edited = client.patch(
        message_url(message.pk), {"title": "عنوان تازه"}, content_type="application/json"
    )

    assert edited.status_code == 200
    assert edited.json()["title"] == "عنوان تازه"
    assert client.delete(message_url(message.pk)).status_code == 204
    assert not Message.objects.filter(pk=message.pk).exists()


def test_a_team_audience_needs_a_team(announcer, alpha):
    response = session(announcer).post(
        MESSAGES_URL,
        {"title": "خبر", "body": "متن", "audience": "team"},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "audience_team" in response.json()


def test_switching_away_from_a_team_audience_clears_the_team(announcer, alpha):
    client = session(announcer)
    message_id = client.post(
        MESSAGES_URL,
        {"title": "خبر", "body": "م", "audience": "team", "audience_team": "alpha"},
        content_type="application/json",
    ).json()["id"]

    body = client.patch(
        message_url(message_id), {"audience": "all"}, content_type="application/json"
    ).json()

    assert body["audience_team"] is None


def test_another_announcers_draft_stays_private(announcer, alpha_user):
    other = User.objects.create_user("boss2", password="x")
    other.groups.add(Group.objects.get(name="GameGods"))
    mine = draft(audience=Audience.ALL, sender=announcer, title="مال من")
    theirs = draft(audience=Audience.ALL, sender=other, title="مال او")

    titles = [row["title"] for row in session(announcer).get(f"{MESSAGES_URL}?status=draft").json()]

    assert titles == ["مال من"]
    assert session(announcer).get(message_url(theirs.pk)).status_code == 404
    assert mine.pk  # keeps the fixture honest about what was compared


def test_sent_messages_are_the_shared_record(announcer, alpha_user):
    other = User.objects.create_user("boss2", password="x")
    other.groups.add(Group.objects.get(name="GameGods"))
    services.send_message(draft(audience=Audience.ALL, sender=other, title="مال او"))

    titles = [row["title"] for row in session(announcer).get(f"{MESSAGES_URL}?status=sent").json()]

    assert titles == ["مال او"]


def test_sent_rows_count_deliveries_and_reads(announcer, alpha_user, beta_user):
    message = draft(audience=Audience.ALL, sender=announcer)
    services.send_message(message)
    Notification.objects.filter(user=alpha_user).update(read_at=timezone.now())

    row = session(announcer).get(f"{MESSAGES_URL}?status=sent").json()[0]

    assert (row["recipient_count"], row["read_count"]) == (2, 1)


def test_audience_options_are_announcer_only(announcer, alpha_user, alpha):
    assert session(alpha_user).get(AUDIENCES_URL).status_code == 403

    body = session(announcer).get(AUDIENCES_URL).json()

    assert {choice["value"] for choice in body["choices"]} == set(Audience.values)
    assert [team["code"] for team in body["teams"]] == ["alpha"]
    assert {user["username"] for user in body["users"]} == {"boss", "alpha-user"}


# ---- the automatic half ----------------------------------------------------


def test_announce_writes_a_system_message(alpha_user, alpha):
    message = services.announce(
        title="زمان تمام شد",
        body="متن",
        audience=Audience.TEAM,
        audience_team=alpha,
        event_key="attempt.expired",
    )

    assert message.kind == MessageKind.SYSTEM
    assert message.status == MessageStatus.SENT
    assert message.sender_label == services.SYSTEM_SENDER_LABEL
    assert Notification.objects.get(user=alpha_user).message == message


def test_grading_a_submission_reaches_the_team(alpha, alpha_user):
    """The whole automatic path, end to end: a mentor grades, the team is told."""
    from game.models import (
        AnswerType,
        GameSettings,
        GameStatus,
        LevelConfig,
        Node,
        Occupancy,
        Question,
        Submission,
    )
    from game.services.questions import grade_submission

    settings_row = GameSettings.load()
    settings_row.status = GameStatus.RUNNING
    settings_row.save(update_fields=["status"])

    easy = LevelConfig.objects.get(pk="easy")
    node = Node.objects.create(code="e1", name="نانوایی", level=easy)
    question = Question.objects.create(
        level=easy, code="q1", title="سؤال", body="متن", answer_type=AnswerType.TEXT
    )
    holding = Occupancy.objects.create(
        team=alpha,
        node=node,
        slot=1,
        question=question,
        question_assigned_at=timezone.now(),
    )
    submission = Submission.objects.create(occupancy=holding, body="۴۲", submitted_by=alpha_user)

    grade_submission(submission, 90)

    notification = Notification.objects.get(user=alpha_user)
    assert notification.message.event_key == "grade.posted"
    assert "نانوایی" in notification.message.title
    assert notification.read_at is None


def test_an_alert_that_fails_does_not_take_the_move_down(alpha, monkeypatch, caplog):
    """Notifications are a courtesy; a broken one must never roll back a grade."""
    from notifications import alerts

    def explode(**kwargs):
        raise RuntimeError("no")

    monkeypatch.setattr(alerts, "announce", explode)

    class FakeNode:
        name = ""
        code = "e1"

    class FakeOccupancy:
        node = FakeNode()
        team = alpha
        grade = 90
        floor = 1
        points = 100

    with caplog.at_level("ERROR", logger="karsoogh"):
        alerts.grade_posted(FakeOccupancy())

    assert "Notification failed" in caplog.text
