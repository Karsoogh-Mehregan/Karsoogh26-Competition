from django.core.cache import cache

from game.services import events

from .models import Team
from .serializers import TeamSerializer

SNAPSHOT_TTL_SECONDS = 60


def _render(request, board: str) -> list[dict]:
    # `with_holdings()` prefetches the toll attempts too, so the whole board's
    # crossings cost one query rather than one per team.
    serializer = TeamSerializer(
        Team.objects.filter(board=board).with_holdings(),
        many=True,
        context={"request": request, "unmasked": True},
    )
    return [dict(row) for row in serializer.data]


def snapshot(request, board: str) -> list[dict]:
    version = events.current_version()
    if version is None:
        return _render(request, board)

    # The board is part of the key, not just the version: the two contests move
    # under one SSE version, so a shared key would hand one contest the other's
    # teams.
    key = f"board:snapshot:{version}:{board}"
    rows = cache.get(key)
    if rows is None:
        rows = _render(request, board)
        cache.set(key, rows, timeout=SNAPSHOT_TTL_SECONDS)
    return rows


def _blind_holdings(holdings: list[dict]) -> list[dict]:
    """The map needs to know who sits where, not how well they answered.

    `grade` is another team's score and `id` is the seat's Occupancy pk — the
    handle a duel or a buyout names — so neither travels to a rival. The keys
    stay present and null: the SPA reads one `Holding` shape for every row.
    """
    return [{**holding, "id": None, "grade": None} for holding in holdings]


def mask(rows: list[dict], *, is_mentor: bool, viewer_team_code: str | None) -> list[dict]:
    if is_mentor:
        return rows
    return [
        row
        if row["code"] == viewer_team_code
        else {
            **row,
            "balance": None,
            "cleared_tolls": [],
            "active_tolls": [],
            "holdings": _blind_holdings(row["holdings"]),
        }
        for row in rows
    ]
