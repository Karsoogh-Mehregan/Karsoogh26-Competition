"""POST /api/teams/me/items/use/ — thin dispatch over the item usage services."""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from core.boards import Board
from game.models import (
    AcquisitionSource,
    GameSettings,
    GameStatus,
    LevelConfig,
    Node,
    Occupancy,
)
from teams.models import ItemType, Team, TeamItem

pytestmark = pytest.mark.django_db

User = get_user_model()

USE_URL = "/api/teams/me/items/use/"


@pytest.fixture
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture
def hard():
    return LevelConfig.objects.get(level="hard")


@pytest.fixture
def alpha():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=400)


@pytest.fixture
def bravo():
    return Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=400)


def client_for(team: Team | None) -> APIClient:
    user = User.objects.create_user(
        "player" if team is None else f"user-{team.code}",
        password="secret",
        team=team,
    )
    client = APIClient()
    client.force_authenticate(user)
    return client


def give(team, item_type, quantity=1) -> TeamItem:
    return TeamItem.objects.create(team=team, item_type=item_type, quantity=quantity)


def occupy(node, team, **kwargs) -> Occupancy:
    kwargs.setdefault("slot", 1)
    return Occupancy.objects.create(node=node, team=team, **kwargs)


class TestAuthentication:
    def test_anonymous_is_rejected(self):
        client = APIClient()
        response = client.post(
            USE_URL,
            {"item_type": ItemType.GILARI_100},
            format="json",
        )
        assert response.status_code == 403

    def test_user_without_a_team_is_rejected(self):
        client = client_for(None)
        response = client.post(
            USE_URL,
            {"item_type": ItemType.GILARI_100},
            format="json",
        )
        assert response.status_code == 403


class TestFakeDocument:
    def test_valid_request_uses_the_item(self, running_game, hard, alpha):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(alpha, ItemType.FAKE_DOCUMENT, quantity=2)
        client = client_for(alpha)

        response = client.post(
            USE_URL,
            {"item_type": ItemType.FAKE_DOCUMENT, "node_code": node.code, "floor": 2},
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"detail": "Item used successfully."}
        item = TeamItem.objects.get(team=alpha, item_type=ItemType.FAKE_DOCUMENT)
        assert item.quantity == 1
        holding = Occupancy.objects.active().get(team=alpha, node=node)
        assert holding.source == AcquisitionSource.ITEM
        assert holding.floor == 2

    def test_unknown_node_is_rejected(self, running_game, alpha):
        give(alpha, ItemType.FAKE_DOCUMENT)
        client = client_for(alpha)

        response = client.post(
            USE_URL,
            {"item_type": ItemType.FAKE_DOCUMENT, "node_code": "missing", "floor": 1},
            format="json",
        )

        assert response.status_code == 404
        assert TeamItem.objects.filter(team=alpha, item_type=ItemType.FAKE_DOCUMENT).exists()
        assert Occupancy.objects.filter(team=alpha).count() == 0

    def test_a_missing_floor_is_rejected(self, running_game, hard, alpha):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(alpha, ItemType.FAKE_DOCUMENT)
        client = client_for(alpha)

        response = client.post(
            USE_URL,
            {"item_type": ItemType.FAKE_DOCUMENT, "node_code": node.code},
            format="json",
        )

        assert response.status_code == 400
        assert "floor" in response.json()
        assert TeamItem.objects.filter(team=alpha, item_type=ItemType.FAKE_DOCUMENT).exists()
        assert Occupancy.objects.filter(team=alpha).count() == 0


class TestGel:
    def test_valid_request_locks_the_node(self, running_game, hard, alpha, bravo):
        node = Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        previous = occupy(node, bravo, slot=1, floor=1)
        give(alpha, ItemType.GEL)
        client = client_for(alpha)

        response = client.post(
            USE_URL,
            {"item_type": ItemType.GEL, "node_code": node.code},
            format="json",
        )

        assert response.status_code == 200
        previous.refresh_from_db()
        node.refresh_from_db()
        assert previous.released_at is not None
        assert node.gelled is True
        assert Occupancy.objects.active().filter(node=node).count() == 0
        assert not TeamItem.objects.filter(team=alpha, item_type=ItemType.GEL).exists()


class TestGilari:
    def test_valid_request_consumes_without_a_node(self, alpha):
        give(alpha, ItemType.GILARI_100, quantity=2)
        client = client_for(alpha)

        response = client.post(
            USE_URL,
            {"item_type": ItemType.GILARI_100},
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {"detail": "Item used successfully."}
        leftover = TeamItem.objects.get(team=alpha, item_type=ItemType.GILARI_100)
        assert leftover.quantity == 1
        assert Occupancy.objects.filter(team=alpha).count() == 0

    def test_extra_node_code_is_ignored(self, alpha, hard):
        Node.objects.create(board=Board.GIRLS, code="h1", name="Hard 1", level=hard)
        give(alpha, ItemType.GILARI_100)
        client = client_for(alpha)

        response = client.post(
            USE_URL,
            {"item_type": ItemType.GILARI_100, "node_code": "h1"},
            format="json",
        )

        assert response.status_code == 200
        assert Occupancy.objects.count() == 0


class TestValidation:
    def test_invalid_item_type_is_rejected(self, alpha):
        client = client_for(alpha)

        response = client.post(
            USE_URL,
            {"item_type": "not_an_item"},
            format="json",
        )

        assert response.status_code == 400
        assert "item_type" in response.json()

    def test_missing_node_code_is_rejected_for_node_items(self, running_game, alpha):
        give(alpha, ItemType.FAKE_DOCUMENT)
        give(alpha, ItemType.GEL)
        client = client_for(alpha)

        for item_type in (ItemType.FAKE_DOCUMENT, ItemType.GEL):
            response = client.post(USE_URL, {"item_type": item_type}, format="json")
            assert response.status_code == 400
            assert "node_code" in response.json()
        assert TeamItem.objects.filter(team=alpha).count() == 2
