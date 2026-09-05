"""Inbox notices for the gel item.

Duels are the other place the board writes to the inbox, and for the same
reason: being kicked out of a house is not something the map can say on its
own. The occupant has to be told. Best-effort, like the duel notices — a
broken inbox must never roll back the gel.
"""

import logging

from notifications.models import Message
from notifications.services import send_message
from teams.models import Team

logger = logging.getLogger("karsoogh")

SENDER_LABEL = "گِل"


def house_gelled(node_code: str, node_name: str, by_team_name: str, team_ids: list[int]) -> None:
    """Tell the teams that were sitting in the house that it is gone, and who did it."""
    if not team_ids:
        return
    teams = list(Team.objects.filter(pk__in=team_ids))
    if not teams:
        return
    where = node_name or node_code
    try:
        message = Message.objects.create(
            title="خانه گِل گرفت",
            body=(
                f"خانهٔ «{where}» که در اختیار شما بود توسط تیم «{by_team_name}» گِل گرفته شد "
                "و دیگر کسی نمی‌تواند وارد آن شود."
            ),
            sender_label=SENDER_LABEL,
        )
        message.teams.set(teams)
        send_message(message)
    except Exception:
        logger.warning("Gel notice failed for node %s", node_code, exc_info=True)
