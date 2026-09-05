"""One render per stream version, then per-viewer masking over the shared rows."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.utils import timezone

from core.boards import Board
from game.models import LevelConfig, Node, Occupancy
from game.services import events
from teams import board_cache
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def versioned(settings):
    """current_version() needs REDIS_URL set; the value itself is a cache read."""
    settings.REDIS_URL = "redis://127.0.0.1:6379/0"
    cache.set(events.BOARD_VERSION_CACHE_KEY, "1-0", timeout=None)
    return settings


@pytest.fixture
def board():
    easy = LevelConfig.objects.get(level="easy")
    node = Node.objects.create(board=Board.GIRLS, code="e1", name="Easy 1", level=easy)
    alpha = Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=42)
    bravo = Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=99)
    Occupancy.objects.create(node=node, team=alpha, slot=1, floor=1)
    Occupancy.objects.create(
        node=node,
        team=bravo,
        slot=2,
        floor=2,
        grade=80,
        grade_multiplier=Decimal("0.8"),
        question_assigned_at=timezone.now(),
    )
    return {"alpha": alpha, "bravo": bravo, "node": node}


@pytest.fixture
def rows():
    return [
        {
            "code": "alpha",
            "name": "Alpha",
            "balance": 42,
            "color": None,
            "holdings": [{"id": 1, "node_code": "e1", "floor": 1, "grade": 90}],
            "cleared_tolls": ["C34_0"],
            "active_tolls": ["C45_0"],
        },
        {
            "code": "bravo",
            "name": "Bravo",
            "balance": 99,
            "color": None,
            "holdings": [{"id": 2, "node_code": "e2", "floor": 1, "grade": 80}],
            "cleared_tolls": ["C45_0"],
            "active_tolls": ["C34_0"],
        },
    ]


def test_mentor_sees_every_balance(rows):
    assert board_cache.mask(rows, is_mentor=True, viewer_team_code=None) is rows


def test_a_team_sees_only_its_own_balance(rows):
    masked = board_cache.mask(rows, is_mentor=False, viewer_team_code="alpha")

    assert [(row["code"], row["balance"]) for row in masked] == [("alpha", 42), ("bravo", None)]
    assert [row["cleared_tolls"] for row in masked] == [["C34_0"], []]
    assert [row["active_tolls"] for row in masked] == [["C45_0"], []]


def test_a_team_sees_no_grade_or_seat_id_of_another(rows):
    masked = board_cache.mask(rows, is_mentor=False, viewer_team_code="alpha")

    assert masked[0]["holdings"] == [{"id": 1, "node_code": "e1", "floor": 1, "grade": 90}]
    assert masked[1]["holdings"] == [{"id": None, "node_code": "e2", "floor": 1, "grade": None}]


def test_a_mentor_keeps_every_grade_and_seat_id(rows):
    masked = board_cache.mask(rows, is_mentor=True, viewer_team_code=None)

    assert masked[1]["holdings"] == [{"id": 2, "node_code": "e2", "floor": 1, "grade": 80}]


def test_masking_leaves_the_snapshot_intact(rows):
    holdings = rows[0]["holdings"]

    board_cache.mask(rows, is_mentor=False, viewer_team_code="bravo")

    assert rows[0]["balance"] == 42
    assert rows[1]["balance"] == 99
    assert rows[0]["cleared_tolls"] == ["C34_0"]
    assert rows[1]["cleared_tolls"] == ["C45_0"]
    # The row a viewer owns is shared by reference, never copied.
    assert rows[0]["holdings"] is holdings
    assert rows[0]["holdings"][0]["grade"] == 90


def test_two_viewers_do_not_contaminate_each_other(rows):
    first = board_cache.mask(rows, is_mentor=False, viewer_team_code="alpha")
    second = board_cache.mask(rows, is_mentor=False, viewer_team_code="bravo")

    assert [row["balance"] for row in first] == [42, None]
    assert [row["cleared_tolls"] for row in first] == [["C34_0"], []]
    assert [row["balance"] for row in second] == [None, 99]
    assert [row["cleared_tolls"] for row in second] == [[], ["C45_0"]]


def test_snapshot_renders_once_per_version(rf, versioned, board, monkeypatch):
    calls = []
    original = board_cache._render
    monkeypatch.setattr(
        board_cache,
        "_render",
        lambda request, board: calls.append(1) or original(request, board),
    )
    request = rf.get("/api/teams/")

    first = board_cache.snapshot(request, Board.GIRLS)
    second = board_cache.snapshot(request, Board.GIRLS)

    assert len(calls) == 1
    assert first == second


def test_a_new_version_forces_a_re_render(rf, versioned, board, monkeypatch):
    calls = []
    original = board_cache._render
    monkeypatch.setattr(
        board_cache,
        "_render",
        lambda request, board: calls.append(1) or original(request, board),
    )
    request = rf.get("/api/teams/")

    board_cache.snapshot(request, Board.GIRLS)
    cache.set(events.BOARD_VERSION_CACHE_KEY, "2-0", timeout=None)
    board_cache.snapshot(request, Board.GIRLS)

    assert len(calls) == 2


def test_snapshot_is_not_cached_without_a_version(rf, settings, board, monkeypatch):
    settings.REDIS_URL = ""
    calls = []
    original = board_cache._render
    monkeypatch.setattr(
        board_cache,
        "_render",
        lambda request, board: calls.append(1) or original(request, board),
    )
    request = rf.get("/api/teams/")

    board_cache.snapshot(request, Board.GIRLS)
    board_cache.snapshot(request, Board.GIRLS)

    assert len(calls) == 2


def test_endpoint_output_matches_with_and_without_the_cache(client, settings, board):
    user = User.objects.create_user("alpha-user", password="x", team=board["alpha"])
    client.force_login(user)

    settings.REDIS_URL = ""
    uncached = client.get("/api/teams/").json()

    settings.REDIS_URL = "redis://127.0.0.1:6379/0"
    cache.set(events.BOARD_VERSION_CACHE_KEY, "1-0", timeout=None)
    cached = client.get("/api/teams/").json()
    again = client.get("/api/teams/").json()

    assert uncached == cached == again
    assert [(row["code"], row["balance"]) for row in cached] == [("alpha", 42), ("bravo", None)]


def test_mentor_and_team_get_different_balances_from_one_snapshot(client, versioned, board):
    mentor = User.objects.create_user("mentor", password="x")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    player = User.objects.create_user("alpha-user", password="x", team=board["alpha"])

    client.force_login(mentor)
    as_mentor = client.get("/api/teams/").json()
    client.force_login(player)
    as_player = client.get("/api/teams/").json()

    assert [row["balance"] for row in as_mentor] == [42, 99]
    assert [row["balance"] for row in as_player] == [42, None]


def test_endpoint_blinds_a_rival_seat(client, board):
    user = User.objects.create_user("alpha-user", password="x", team=board["alpha"])
    client.force_login(user)

    rows = {row["code"]: row for row in client.get("/api/teams/").json()}

    own = rows["alpha"]["holdings"][0]
    rival = rows["bravo"]["holdings"][0]
    assert own["id"] is not None
    assert rival["id"] is None
    assert rival["grade"] is None
    # The map still needs to know the seat is taken, and by whom.
    assert (rival["node_code"], rival["slot"], rival["floor"]) == ("e1", 2, 2)
