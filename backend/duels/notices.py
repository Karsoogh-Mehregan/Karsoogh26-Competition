"""Writing duels into people's inboxes.

This is the one place in the whole project where the board narrates itself, and
it is deliberate. `notifications/models.py` explains why nothing else does: a
notification per board event is noise, and noise teaches players to stop
reading the bell. A duel is the exception because a duel *is not on the board* —
it happens in a video call the player has to be told to join, against an
opponent they did not pick a time with, at a link they have no other way of
learning. The rules sheet says as much: «درخواست دوئل به صورت پیام در سایت برای
شما فرستاده می‌شود». So duels write, and nothing else does.

Every function here is best-effort. A message that fails to send is logged and
swallowed, because a broken inbox must never roll back the duel that caused it —
the same rule the SSE publisher follows. The duel page is the source of truth
either way; these are the nudge towards it.

Messages are written with no sender. `notifications.views.MessageViewBase` shows
the announcer's Sent list only messages a person wrote, so a hundred duel
notices never bury the announcements an organiser is looking for.
"""

import logging

from notifications.models import Message
from notifications.services import send_message

logger = logging.getLogger("karsoogh")

SENDER_LABEL = "دوئل"


def _floor_label(duel) -> str:
    return f"طبقهٔ {duel.floor} ساختمان «{duel.node.name or duel.node.code}»"


def _send(title: str, body: str, *, teams=(), users=()) -> None:
    """Compose and fan out one notice. Swallows and logs anything that breaks."""
    try:
        message = Message.objects.create(title=title[:120], body=body, sender_label=SENDER_LABEL)
        if teams:
            message.teams.set(teams)
        if users:
            message.users.set(users)
        send_message(message)
    except Exception:
        logger.warning("Duel notice failed: %s", title, exc_info=True)


def duel_opened(duel) -> None:
    """Tell both teams the duel exists, and tell the judge they are on it.

    Two messages rather than one: the teams need the link and the stake, the
    judge needs to know a match has landed in their room. Both carry the same
    link, because all three of them are going to the same meeting.
    """
    where = _floor_label(duel)
    _send(
        f"دوئل: {duel.attacker.name} در برابر {duel.attacked.name}",
        (
            f"تیم «{duel.attacker.name}» برای {where} به تیم «{duel.attacked.name}» "
            f"درخواست دوئل داده است.\n"
            f"ورودی دوئل: {duel.stake}\n"
            f"داور: {duel.mentor.get_username()}\n"
            f"لینک میت: {duel.room.link}\n\n"
            "هر چه زودتر در میت حاضر شوید؛ تیمی که حاضر نشود بازنده به حساب می‌آید."
        ),
        teams=[duel.attacker, duel.attacked],
    )
    _send(
        f"دوئل جدید در اتاق «{duel.room.name}»",
        (
            f"دوئل بین «{duel.attacker.name}» و «{duel.attacked.name}» بر سر {where} "
            "به شما سپرده شد.\n"
            f"لینک میت: {duel.room.link}\n\n"
            "پس از پایان بازی، برنده را از صفحهٔ دوئل‌ها ثبت کنید."
        ),
        users=[duel.mentor],
    )


def duel_closed(duel) -> None:
    """Tell both teams who won and what it cost or paid."""
    where = _floor_label(duel)
    attacker_won = duel.winner_id == duel.attacker_id
    outcome = (
        f"{where} به تیم «{duel.attacker.name}» رسید و ورودی پرداختی بازگردانده شد."
        if attacker_won
        else (
            f"{where} برای تیم «{duel.attacked.name}» باقی ماند و ورودی دوئل "
            f"({duel.stake}) به آن تیم پرداخت شد."
        )
    )
    _send(
        f"نتیجهٔ دوئل: «{duel.winner.name}» برنده شد",
        (
            f"دوئل «{duel.attacker.name}» و «{duel.attacked.name}» با برد تیم "
            f"«{duel.winner.name}» به پایان رسید.\n{outcome}"
        ),
        teams=[duel.attacker, duel.attacked],
    )
