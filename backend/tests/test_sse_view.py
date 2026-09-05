"""The SSE endpoint, driven with async_to_sync: pytest here has no async runner."""

import asyncio

import pytest
from asgiref.sync import async_to_sync
from django.contrib.auth.models import Group
from django.test import AsyncClient
from django.urls import reverse

from game import sse
from game.services import events

pytestmark = pytest.mark.django_db

STREAM_URL = reverse("game:board-stream")


class FakeHub:
    """Stands in for the Redis-backed hub: same surface, no I/O."""

    def __init__(self, oldest=None, replayed=()):
        self.queues: set[asyncio.Queue] = set()
        self.started = False
        self._oldest = oldest
        self._replayed = list(replayed)

    async def ensure_started(self):
        self.started = True

    def subscribe(self):
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.queues.add(queue)
        return queue

    def unsubscribe(self, queue):
        self.queues.discard(queue)

    async def oldest_entry_id(self):
        return self._oldest

    async def replay(self, last_event_id):
        return self._replayed


@pytest.fixture
def stream_enabled(settings):
    settings.REDIS_URL = "redis://127.0.0.1:6379/0"
    return settings


@pytest.fixture
def fake_hub(monkeypatch):
    replacement = FakeHub()
    monkeypatch.setattr(sse, "hub", replacement)
    return replacement


@pytest.fixture
def player(django_user_model):
    return django_user_model.objects.create_user("alpha-user", password="x")


@pytest.fixture
def mentor(django_user_model):
    user = django_user_model.objects.create_user("mentor", password="x")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


async def _open(user=None):
    client = AsyncClient()
    if user is not None:
        await client.aforce_login(user)
    return await client.get(STREAM_URL)


async def _take(response, count):
    iterator = aiter(response.streaming_content)
    chunks = []
    try:
        for _ in range(count):
            chunks.append(await anext(iterator))
    finally:
        await iterator.aclose()
    return chunks


def test_anonymous_gets_401(stream_enabled, fake_hub):
    response = async_to_sync(_open)()

    assert response.status_code == 401
    assert fake_hub.started is False


def test_503_when_redis_is_not_configured(settings, fake_hub, player):
    settings.REDIS_URL = ""

    response = async_to_sync(_open)(player)

    assert response.status_code == 503
    assert fake_hub.started is False


def test_stream_headers(stream_enabled, fake_hub, player):
    response = async_to_sync(_open)(player)

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "text/event-stream"
    assert response.headers["Cache-Control"] == "no-cache, no-transform"
    assert response.headers["X-Accel-Buffering"] == "no"
    async_to_sync(_take)(response, 1)


def test_stream_opens_with_retry_then_resync(stream_enabled, fake_hub, player):
    response = async_to_sync(_open)(player)

    chunks = async_to_sync(_take)(response, 3)

    assert chunks[0].startswith(b"retry: ")
    assert chunks[1] == b": connected\n\n"
    assert chunks[2] == sse.RESYNC_FRAME.payload


def test_live_frames_reach_a_subscriber(stream_enabled, fake_hub, player):
    frame = sse.build_frame(b"7-0", {b"t": b"board.graded", b"d": b'{"node":"e1"}'})

    async def scenario():
        response = await _open(player)
        iterator = aiter(response.streaming_content)
        for _ in range(3):
            await anext(iterator)
        for queue in fake_hub.queues:
            queue.put_nowait(frame)
        live = await anext(iterator)
        await iterator.aclose()
        return live

    assert async_to_sync(scenario)() == frame.payload


def test_mentor_only_frames_are_withheld_from_players(stream_enabled, fake_hub):
    private = sse.build_frame(b"7-0", {b"t": events.SUBMISSION_CREATED.encode(), b"d": b"{}"})
    public = sse.build_frame(b"8-0", {b"t": b"board.graded", b"d": b"{}"})

    async def scenario(is_mentor):
        queue = fake_hub.subscribe()
        queue.put_nowait(private)
        queue.put_nowait(public)
        generator = sse._stream(queue, is_mentor=is_mentor, replayed=[])
        seen = [await anext(generator) for _ in range(3)]
        await generator.aclose()
        return seen[2]

    assert async_to_sync(scenario)(False) == public.payload
    assert async_to_sync(scenario)(True) == private.payload


def test_addressed_frames_reach_only_the_users_they_name(stream_enabled, fake_hub):
    """A notification hint must not tell the whole hall that somebody got mail."""
    addressed = sse.build_frame(
        b"7-0", {b"t": events.NOTIFICATION_CREATED.encode(), b"d": b"{}", b"u": b"42"}
    )
    everyone = sse.build_frame(b"8-0", {b"t": b"board.graded", b"d": b"{}"})

    async def scenario(user_id):
        queue = fake_hub.subscribe()
        queue.put_nowait(addressed)
        queue.put_nowait(everyone)
        generator = sse._stream(queue, is_mentor=False, replayed=[], user_id=user_id)
        seen = [await anext(generator) for _ in range(3)]
        await generator.aclose()
        return seen[2]

    # The addressed user sees it first; anyone else falls through to the public one.
    assert async_to_sync(scenario)(42) == addressed.payload
    assert async_to_sync(scenario)(7) == everyone.payload


def test_replayed_ids_are_not_delivered_twice(stream_enabled, fake_hub):
    replayed = sse.build_frame(b"7-0", {b"t": b"board.graded", b"d": b'{"n":1}'})
    stale = sse.build_frame(b"7-0", {b"t": b"board.graded", b"d": b'{"n":1}'})
    fresh = sse.build_frame(b"8-0", {b"t": b"board.graded", b"d": b'{"n":2}'})

    async def scenario():
        queue = fake_hub.subscribe()
        queue.put_nowait(stale)
        queue.put_nowait(fresh)
        generator = sse._stream(queue, is_mentor=False, replayed=[replayed])
        seen = [await anext(generator) for _ in range(4)]
        await generator.aclose()
        return seen

    seen = async_to_sync(scenario)()

    assert seen[2] == replayed.payload
    assert seen[3] == fresh.payload


def test_disconnect_unsubscribes(stream_enabled, fake_hub):
    async def scenario():
        queue = fake_hub.subscribe()
        generator = sse._stream(queue, is_mentor=False, replayed=[])
        await anext(generator)
        assert fake_hub.queues == {queue}
        await generator.aclose()
        return fake_hub.queues

    assert async_to_sync(scenario)() == set()


def test_heartbeat_when_nothing_happens(stream_enabled, fake_hub, settings):
    settings.SSE_HEARTBEAT_SECONDS = 0.01

    async def scenario():
        queue = fake_hub.subscribe()
        generator = sse._stream(queue, is_mentor=False, replayed=[])
        seen = [await anext(generator) for _ in range(3)]
        await generator.aclose()
        return seen[2]

    assert async_to_sync(scenario)() == sse.HEARTBEAT_PAYLOAD
