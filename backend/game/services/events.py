import json
import logging

import redis
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger("karsoogh")

BOARD_SPAWN_CLAIMED = "board.spawn.claimed"
BOARD_NODE_CLAIMED = "board.node.claimed"
BOARD_GRADED = "board.graded"
BOARD_RELEASED = "board.released"
BOARD_TOLL_STARTED = "board.toll.started"
BOARD_TOLL_CLEARED = "board.toll.cleared"
QUESTION_ASSIGNED = "question.assigned"
SUBMISSION_CREATED = "mentor.submission.created"
GAME_STATE = "game.state"
NOTIFICATION_CREATED = "notification.created"
MAP_DESIGN = "map.design"
RESYNC = "resync"

MENTOR_ONLY = frozenset({SUBMISSION_CREATED})

BOARD_VERSION_CACHE_KEY = "board:version"

_client = None


def is_enabled() -> bool:
    return bool(settings.REDIS_URL)


def _get_client() -> redis.Redis:
    global _client
    if _client is None:
        # Fail fast rather than wedge a request thread on a hung Redis; the
        # reader in game.sse needs the opposite policy and builds its own.
        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=0.5,
            socket_connect_timeout=1.0,
        )
    return _client


def reset_client() -> None:
    global _client
    _client = None


def publish(
    event_type: str,
    payload: dict | None = None,
    *,
    recipients: list[int] | None = None,
) -> str | None:
    """Append one hint frame to the board stream, returning its entry id.

    Never raises. A dead Redis costs realtime updates, not the move that
    triggered them.

    `recipients` addresses the frame at particular users. It travels in its own
    stream field, never in `payload`: the reader in `game.sse` uses it to decide
    who the frame is delivered to, and a recipient list inside the payload would
    tell every one of them who else was written to.
    """
    if not is_enabled():
        return None

    fields = {"t": event_type, "d": json.dumps(payload or {}, separators=(",", ":"))}
    if recipients:
        fields["u"] = ",".join(str(user_id) for user_id in sorted(set(recipients)))
    try:
        entry_id = _get_client().xadd(
            settings.SSE_STREAM_KEY,
            fields,
            maxlen=settings.SSE_STREAM_MAXLEN,
            approximate=True,
        )
    except (redis.RedisError, OSError):
        logger.warning("SSE publish failed for %s", event_type, exc_info=True)
        return None

    version = entry_id.decode() if isinstance(entry_id, bytes) else str(entry_id)
    try:
        cache.set(BOARD_VERSION_CACHE_KEY, version, timeout=None)
    except Exception:
        logger.warning("Board version write failed for %s", version, exc_info=True)
    return version


def publish_on_commit(
    event_type: str,
    payload: dict | None = None,
    *,
    using=None,
    recipients: list[int] | None = None,
) -> None:
    """Publish once the surrounding transaction commits.

    Deferring is not cosmetic: a rolled-back move must not announce itself, and
    a stalled Redis must never happen while a select_for_update lock is held.
    """
    transaction.on_commit(
        lambda: publish(event_type, payload, recipients=recipients),
        using=using,
        robust=True,
    )


def current_version() -> str | None:
    if not is_enabled():
        return None
    try:
        return cache.get(BOARD_VERSION_CACHE_KEY)
    except Exception:
        logger.warning("Board version read failed", exc_info=True)
        return None
