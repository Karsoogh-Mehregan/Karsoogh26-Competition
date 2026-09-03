"""The automatic half of the inbox: what the game itself tells a team.

One function per moment worth interrupting someone for, each named after the
event rather than the delivery, so the call site in `game/` reads as game code.
Every one of them is best-effort: a notification that cannot be written must
never roll back the move that caused it, so failures are logged and swallowed.

Deliberately short. A notification for every board event would be noise, and
noise is how a player learns to ignore the bell. The rule used here: interrupt
a team only for something that happened *to* it and that it did not just do.
"""

import logging

from .models import Audience
from .services import announce

logger = logging.getLogger("karsoogh")


def _safe(fn, *args, **kwargs) -> None:
    """Never let a notification failure take the game action down with it."""
    try:
        fn(*args, **kwargs)
    except Exception:  # Deliberately broad; see the module docstring.
        logger.exception("Notification failed: %s", getattr(fn, "__name__", fn))


def _node_label(node) -> str:
    return node.name or node.code


def grade_posted(occupancy) -> None:
    """A mentor scored this team's answer."""
    node = _node_label(occupancy.node)
    points = occupancy.points
    if occupancy.grade == 0:
        title = f"پاسخ شما در «{node}» نمره نگرفت"
        # Deliberately says nothing about the seat: whether a zero also frees it
        # depends on which grading path ran, and a message that guesses wrong is
        # worse than one that only reports the score.
        body = "نمرهٔ این پاسخ ۰ ثبت شد و امتیازی به این واحد تعلق نگرفت."
    else:
        title = f"پاسخ شما در «{node}» نمره گرفت"
        body = (
            f"نمرهٔ ثبت‌شده: {occupancy.grade} از ۱۰۰."
            + (f" امتیاز این واحد: {points}." if points else "")
            + (f" واحد شما: طبقهٔ {occupancy.floor}." if occupancy.floor else "")
        )
    _safe(
        announce,
        title=title,
        body=body,
        audience=Audience.TEAM,
        audience_team=occupancy.team,
        event_key="grade.posted",
    )


def floor_promoted(occupancy) -> None:
    """The house re-ranked and this team's unit got better."""
    node = _node_label(occupancy.node)
    _safe(
        announce,
        title=f"واحد شما در «{node}» ارتقا یافت",
        body=(
            f"با ورود تیم تازه به این خانه، رتبه‌بندی واحدها به‌روز شد و "
            f"شما به طبقهٔ {occupancy.floor} رسیدید. امتیاز اختلاف به موجودی شما اضافه شد."
        ),
        audience=Audience.TEAM,
        audience_team=occupancy.team,
        event_key="floor.promoted",
    )


def attempt_expired(occupancy) -> None:
    """The clock on a reserved node ran out before an answer arrived."""
    node = _node_label(occupancy.node)
    _safe(
        announce,
        title=f"زمان سؤال «{node}» تمام شد",
        body=(
            "پاسخی پیش از پایان مهلت ثبت نشد، بنابراین این ظرفیت آزاد شد و آن سؤال "
            "برای تیم شما سوخت. هزینهٔ ورود برگردانده نمی‌شود."
        ),
        audience=Audience.TEAM,
        audience_team=occupancy.team,
        event_key="attempt.expired",
    )


_STATUS_COPY = {
    "running": (
        "بازی شروع شد",
        "ساعت بازی در حال اجراست. نقشه باز است و می‌توانید حرکت کنید.",
    ),
    "paused": (
        "بازی موقتاً متوقف شد",
        "همهٔ زمان‌سنج‌ها متوقف شدند. تا اعلام بعدی حرکتی ثبت نمی‌شود.",
    ),
    "finished": (
        "بازی تمام شد",
        "ساعت بازی متوقف شد و حرکت تازه‌ای پذیرفته نمی‌شود.",
    ),
    "not_started": (
        "بازی به حالت شروع‌نشده بازگشت",
        "میز بازی پاک شد و همه‌چیز برای اجرای تازه آماده است.",
    ),
}


def game_status_changed(status: str) -> None:
    """The whole hall needs to know; everyone gets this one."""
    copy = _STATUS_COPY.get(status)
    if copy is None:
        return
    title, body = copy
    _safe(
        announce,
        title=title,
        body=body,
        audience=Audience.ALL,
        event_key="game.status",
    )
