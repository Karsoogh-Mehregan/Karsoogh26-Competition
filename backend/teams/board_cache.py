from django.core.cache import cache

from game.services import events

from .models import Team
from .serializers import TeamSerializer

SNAPSHOT_TTL_SECONDS = 60


def _render(request) -> list[dict]:
    serializer = TeamSerializer(
        Team.objects.with_holdings(),
        many=True,
        context={"request": request, "unmasked": True},
    )
    return [dict(row) for row in serializer.data]


def snapshot(request) -> list[dict]:
    version = events.current_version()
    if version is None:
        return _render(request)

    key = f"board:snapshot:{version}"
    rows = cache.get(key)
    if rows is None:
        rows = _render(request)
        cache.set(key, rows, timeout=SNAPSHOT_TTL_SECONDS)
    return rows


def mask(rows: list[dict], *, is_mentor: bool, viewer_team_code: str | None) -> list[dict]:
    if is_mentor:
        return rows
    return [
        row if row["code"] == viewer_team_code else {**row, "balance": None, "cleared_tolls": []}
        for row in rows
    ]
