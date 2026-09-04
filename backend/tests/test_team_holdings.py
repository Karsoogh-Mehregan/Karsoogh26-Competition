"""Team.holdings and the nodes/floors the teams list exposes to the frontend."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.utils import timezone

from game.models import LevelConfig, Node, Occupancy
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()


@pytest.fixture
def auth_client(client):
    user = User.objects.create_user("mentor", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(user)
    return client


@pytest.fixture
def nodes():
    easy = LevelConfig.objects.get(level="easy")
    hard = LevelConfig.objects.get(level="hard")
    return {
        "e1": Node.objects.create(code="e1", name="Easy 1", level=easy),
        "e2": Node.objects.create(code="e2", name="Easy 2", level=easy),
        "h1": Node.objects.create(code="h1", name="Hard 1", level=hard),
    }


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha", balance=42)


def test_occupancy_defaults_to_attempt_source(team, nodes):
    occupancy = Occupancy.objects.create(node=nodes["e1"], team=team, slot=1)

    assert occupancy.source == "attempt"


def test_holdings_lists_node_and_floor(team, nodes):
    Occupancy.objects.create(node=nodes["e1"], team=team, slot=1, floor=1)
    Occupancy.objects.create(node=nodes["h1"], team=team, slot=2, floor=None)

    assert [(h.node.code, h.floor) for h in team.holdings] == [("e1", 1), ("h1", None)]


def test_holdings_excludes_released(team, nodes):
    Occupancy.objects.create(
        node=nodes["e1"],
        team=team,
        slot=1,
        floor=1,
        released_at=timezone.now(),
        release_reason="duel_lost",
    )
    kept = Occupancy.objects.create(node=nodes["e2"], team=team, slot=1, floor=2)

    assert [h.pk for h in team.holdings] == [kept.pk]


def test_with_holdings_matches_unprefetched(team, nodes):
    Occupancy.objects.create(node=nodes["e1"], team=team, slot=1, floor=1)

    prefetched = Team.objects.with_holdings().get(pk=team.pk)
    assert [h.pk for h in prefetched.holdings] == [h.pk for h in team.holdings]


def test_with_holdings_does_not_scale_with_team_count(nodes, django_assert_num_queries):
    for slot, code in enumerate(("alpha", "beta", "gamma"), start=1):
        other = Team.objects.create(code=code, name=code.title())
        Occupancy.objects.create(node=nodes["e1"], team=other, slot=slot)

    with django_assert_num_queries(3):  # teams, holdings prefetch, won-toll prefetch
        rows = [[h.node.code for h in team.holdings] for team in Team.objects.with_holdings()]

    assert rows == [["e1"], ["e1"], ["e1"]]


def test_teams_list_holding_shape(auth_client, team, nodes):
    occupancy = Occupancy.objects.create(node=nodes["h1"], team=team, slot=2, floor=3)

    response = auth_client.get("/api/teams/")

    assert response.json()[0]["holdings"] == [
        {
            "id": occupancy.pk,
            "node_code": "h1",
            "node_name": "Hard 1",
            "level": "hard",
            "slot": 2,
            "floor": 3,
            "grade": None,
            "is_spawn": False,
            "source": "attempt",
        }
    ]
