"""Inbox notices for the items that take a house away from a team.

Duels are the other place the board writes to the inbox, and these are here for
the same reason: losing a floor to gel or to a forged deed is not something the
map can say on its own — the team is simply gone from a building it owned a
moment ago, with nothing on screen to say who did it.

Every function here is best-effort, like the duel notices: a message that fails
to send is logged and swallowed, because a broken inbox must never roll back
the move that caused it. Messages are written with no sender, so the announcer's
Sent list stays the announcements a human wrote.
"""

import logging

from notifications.models import Message
from notifications.services import send_message
from teams.models import Team

logger = logging.getLogger("karsoogh")

GEL_LABEL = "گِل"
FAKE_DOCUMENT_LABEL = "سند جعلی"


def _send(title: str, body: str, *, sender_label: str, team_ids: list[int]) -> None:
    """Compose and fan out one notice to the teams named. Swallows what breaks."""
    teams = list(Team.objects.filter(pk__in=team_ids))
    if not teams:
        return
    try:
        message = Message.objects.create(title=title[:120], body=body, sender_label=sender_label)
        message.teams.set(teams)
        send_message(message)
    except Exception:
        logger.warning("Item notice failed: %s", title, exc_info=True)


def house_gelled(node_code: str, node_name: str, by_team_name: str, team_ids: list[int]) -> None:
    """Tell the teams that were sitting in the house that it is gone, and who did it."""
    if not team_ids:
        return
    where = node_name or node_code
    _send(
        "خانه گِل گرفت",
        (
            f"خانهٔ «{where}» که در اختیار شما بود توسط تیم «{by_team_name}» گِل گرفته شد "
            "و دیگر کسی نمی‌تواند وارد آن شود."
        ),
        sender_label=GEL_LABEL,
        team_ids=list(team_ids),
    )


def floor_taken(
    node_code: str, node_name: str, floor: int, by_team_name: str, team_id: int
) -> None:
    """Tell one team which floor of which house it just lost to a fake document."""
    where = node_name or node_code
    _send(
        "واحد شما با سند جعلی گرفته شد",
        (
            f"طبقهٔ {floor} از خانهٔ «{where}» که در اختیار شما بود با «سند جعلی» "
            f"به تیم «{by_team_name}» رسید و شما از آن بیرون آمدید."
        ),
        sender_label=FAKE_DOCUMENT_LABEL,
        team_ids=[team_id],
    )
