import asyncio
import json
import logging
import random
import re
from typing import NamedTuple

import redis
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse
from redis.asyncio import Redis

from accounts.permissions import MENTOR_PERM
from game.services import events

logger = logging.getLogger("karsoogh")

_ENTRY_ID = re.compile(r"^\d+-\d+$")


class Frame(NamedTuple):
    id: str | None
    event: str
    payload: bytes
    mentor_only: bool


def _text(value) -> str:
    if value is None:
        return ""
    return value.decode() if isinstance(value, bytes) else str(value)


def _encode(event_type: str, data: str, entry_id: str | None = None) -> bytes:
    head = f"id: {entry_id}\n" if entry_id else ""
    return f"{head}event: {event_type}\ndata: {data}\n\n".encode()


def build_frame(entry_id, fields: dict) -> Frame:
    event_type = _text(fields.get(b"t") or fields.get("t")) or events.RESYNC
    data = _text(fields.get(b"d") or fields.get("d")) or "{}"
    stream_id = _text(entry_id)
    return Frame(
        id=stream_id,
        event=event_type,
        payload=_encode(event_type, data, stream_id),
        mentor_only=event_type in events.MENTOR_ONLY,
    )


RESYNC_FRAME = Frame(
    id=None,
    event=events.RESYNC,
    payload=_encode(events.RESYNC, "{}"),
    mentor_only=False,
)


def parse_xread(response) -> list:
    """Flatten [[stream, [(id, fields), ...]], ...]; XREAD returns [] on timeout."""
    entries = []
    for _stream, stream_entries in response or []:
        entries.extend(stream_entries)
    return entries


def _sort_key(entry_id: str) -> tuple[int, int]:
    milliseconds, _, sequence = entry_id.partition("-")
    return int(milliseconds), int(sequence)


def resume_plan(last_event_id: str | None, oldest_entry_id: str | None) -> str:
    """tail: start live. replay: send the gap. resync: the cursor was trimmed away."""
    if not last_event_id or not _ENTRY_ID.fullmatch(last_event_id):
        return "tail"
    if oldest_entry_id and _sort_key(oldest_entry_id) > _sort_key(last_event_id):
        return "resync"
    return "replay"


def _reader_client() -> Redis:
    # socket_timeout must stay None: the 5s default aborts XREAD mid-block and
    # turns a healthy idle stream into a reconnect loop.
    return Redis.from_url(
        settings.REDIS_URL,
        socket_timeout=None,
        socket_connect_timeout=5,
        health_check_interval=30,
    )


class Hub:
    """One Redis reader per worker process, fanning out to per-client queues.

    Plain XREAD, never a consumer group: a group would hand each entry to a
    single worker, so most connected clients would never see it.
    """

    def __init__(self):
        self._subscribers: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._client: Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = asyncio.Lock()

    async def ensure_started(self) -> None:
        loop = asyncio.get_running_loop()
        async with self._lock:
            if self._loop is not None and self._loop is not loop:
                raise RuntimeError("Hub is bound to a different event loop")
            if self._task is None or self._task.done():
                self._loop = loop
                self._client = _reader_client()
                self._task = loop.create_task(self._read_forever())

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=settings.SSE_QUEUE_MAXSIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        # Stays synchronous: it runs in the generator's finally, where an await
        # during aclose() would raise "async generator ignored GeneratorExit".
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def broadcast(self, frame: Frame) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                self._collapse(queue)

    def _collapse(self, queue: asyncio.Queue) -> None:
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait(RESYNC_FRAME)

    async def oldest_entry_id(self) -> str | None:
        entries = await self._client.xrange(settings.SSE_STREAM_KEY, count=1)
        return _text(entries[0][0]) if entries else None

    async def replay(self, last_event_id: str) -> list[Frame]:
        entries = await self._client.xrange(
            settings.SSE_STREAM_KEY,
            min=f"({last_event_id}",
            max="+",
            count=settings.SSE_REPLAY_LIMIT,
        )
        return [build_frame(entry_id, fields) for entry_id, fields in entries]

    async def _read_forever(self) -> None:
        cursor = "$"
        backoff = 1
        while True:
            try:
                response = await self._client.xread(
                    {settings.SSE_STREAM_KEY: cursor},
                    block=settings.SSE_BLOCK_MS,
                )
                backoff = 1
            except asyncio.CancelledError:
                raise
            except (redis.RedisError, OSError):
                logger.warning("SSE reader lost Redis; retrying in %ss", backoff, exc_info=True)
                self.broadcast(RESYNC_FRAME)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
                continue
            for entry_id, fields in parse_xread(response):
                cursor = entry_id
                self.broadcast(build_frame(entry_id, fields))


hub = Hub()


async def _stream(queue: asyncio.Queue, *, is_mentor: bool, replayed: list[Frame]):
    retry_ms = settings.SSE_RETRY_MS + random.randint(0, settings.SSE_RETRY_JITTER_MS)
    try:
        yield f"retry: {retry_ms}\n\n".encode()
        yield b": connected\n\n"

        high_water = None
        for frame in replayed:
            if frame.mentor_only and not is_mentor:
                continue
            high_water = frame.id or high_water
            yield frame.payload

        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), settings.SSE_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield b": keepalive\n\n"
                continue
            if frame.mentor_only and not is_mentor:
                continue
            if frame.id and high_water and _sort_key(frame.id) <= _sort_key(high_water):
                continue
            yield frame.payload
    finally:
        hub.unsubscribe(queue)


async def board_stream(request):
    """Long-lived hint stream. Frames say what changed; clients refetch the API."""
    user = await request.auser()
    if not user.is_authenticated:
        return HttpResponse(status=401)

    if not events.is_enabled():
        return HttpResponse(
            json.dumps({"detail": "Realtime updates are not configured."}),
            status=503,
            content_type="application/json",
        )

    is_mentor = await user.ahas_perm(MENTOR_PERM)

    await hub.ensure_started()
    queue = hub.subscribe()
    try:
        replayed = await _resume(request)
    except (redis.RedisError, OSError):
        logger.warning("SSE resume failed; starting from live", exc_info=True)
        replayed = [RESYNC_FRAME]
    except BaseException:
        hub.unsubscribe(queue)
        raise

    return StreamingHttpResponse(
        _stream(queue, is_mentor=is_mentor, replayed=replayed),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


async def _resume(request) -> list[Frame]:
    last_event_id = request.headers.get("Last-Event-ID") or request.GET.get("last_event_id")
    plan = resume_plan(last_event_id, await hub.oldest_entry_id())
    if plan in ("tail", "resync"):
        return [RESYNC_FRAME]
    frames = await hub.replay(last_event_id)
    if len(frames) >= settings.SSE_REPLAY_LIMIT:
        return [RESYNC_FRAME]
    return frames
