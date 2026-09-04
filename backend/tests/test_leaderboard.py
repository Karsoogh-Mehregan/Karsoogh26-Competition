"""GET /api/leaderboard/ — public/private toggled by GameSettings.leaderboard_public."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIClient

from core.boards import Board
from game.models import GameSettings
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def teams():
    Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100)
    Team.objects.create(board=Board.GIRLS, code="bravo", name="Bravo", balance=300)
    Team.objects.create(board=Board.GIRLS, code="charlie", name="Charlie", balance=200)


@pytest.fixture
def client_team(teams):
    user = User.objects.create_user("user-alpha", password="x", team=Team.objects.get(code="alpha"))
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def client_mentor():
    mentor = User.objects.create_user("mentor", password="x")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client = APIClient()
    client.force_authenticate(mentor)
    return client


def test_hidden_from_a_team_by_default(client_team):
    assert client_team.get("/api/leaderboard/").status_code == 403


def test_visible_to_a_team_once_public(client_team):
    settings = GameSettings.load()
    settings.leaderboard_public = True
    settings.save(update_fields=["leaderboard_public"])

    response = client_team.get("/api/leaderboard/")
    assert response.status_code == 200
    assert response.json() == [
        {"rank": 1, "code": "bravo", "name": "Bravo", "balance": 300},
        {"rank": 2, "code": "charlie", "name": "Charlie", "balance": 200},
        {"rank": 3, "code": "alpha", "name": "Alpha", "balance": 100},
    ]


def test_always_visible_to_a_mentor(client_mentor, teams):
    assert client_mentor.get("/api/leaderboard/").status_code == 200


def test_anonymous_is_403(teams):
    assert APIClient().get("/api/leaderboard/").status_code == 403
