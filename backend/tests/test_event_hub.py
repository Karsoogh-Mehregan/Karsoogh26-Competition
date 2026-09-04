import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from events.models import EventCode, EventConfiguration, MatchmakingStatus, TerritoryGame
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def teams():
    return [
        Team.objects.create(code="alpha", name="Alpha", balance=500),
        Team.objects.create(code="beta", name="Beta", balance=500),
    ]


@pytest.fixture
def mentor():
    user = User.objects.create_user("mentor-hub", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


def team_user(team):
    return User.objects.create_user(team.code, password="secret", team=team)


def test_catalog_lists_all_events_and_mentor_controls_timer(client, mentor):
    client.force_login(mentor)
    response = client.get("/api/events/catalog/")
    assert response.status_code == 200
    assert len(response.json()) == len(EventCode.values)

    response = client.patch(
        "/api/events/catalog/charity_bag/",
        {"enabled": False, "duration_seconds": 900},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["duration_seconds"] == 900


def test_disabled_event_rejects_mutation(client, mentor, teams):
    EventConfiguration.objects.filter(code=EventCode.TERRITORY_CONTROL).update(enabled=False)
    client.force_login(mentor)
    response = client.post(
        "/api/events/territory-control/games/",
        {"player_one": teams[0].code, "player_two": teams[1].code},
    )
    assert response.status_code == 403
    assert TerritoryGame.objects.count() == 0


def test_matchmaking_pairs_two_teams_and_is_idempotent_while_waiting(client, teams):
    first_user = team_user(teams[0])
    second_user = team_user(teams[1])

    client.force_login(first_user)
    first = client.post("/api/events/matchmaking/territory_control/join/")
    retry = client.post("/api/events/matchmaking/territory_control/join/")
    assert first.status_code == 201
    assert retry.json()["id"] == first.json()["id"]
    assert retry.json()["status"] == MatchmakingStatus.WAITING

    client.force_login(second_user)
    second = client.post("/api/events/matchmaking/territory_control/join/")
    assert second.status_code == 200
    assert second.json()["status"] == MatchmakingStatus.MATCHED
    assert second.json()["matched_team"]["code"] == teams[0].code
    assert TerritoryGame.objects.filter(pk=second.json()["match_id"]).exists()

    client.force_login(first_user)
    tickets = client.get("/api/events/matchmaking/").json()
    assert tickets[0]["status"] == MatchmakingStatus.MATCHED
    assert tickets[0]["match_id"] == second.json()["match_id"]


def test_team_can_cancel_waiting_ticket(client, teams):
    client.force_login(team_user(teams[0]))
    client.post("/api/events/matchmaking/centipede/join/")
    response = client.post("/api/events/matchmaking/centipede/cancel/")
    assert response.status_code == 200
    assert response.json()["status"] == MatchmakingStatus.CANCELLED


def test_team_can_dismiss_finished_match_and_join_again(client, teams):
    first_user = team_user(teams[0])
    second_user = team_user(teams[1])
    client.force_login(first_user)
    client.post("/api/events/matchmaking/territory_control/join/")
    client.force_login(second_user)
    matched = client.post("/api/events/matchmaking/territory_control/join/").json()

    client.force_login(first_user)
    own_ticket = client.get("/api/events/matchmaking/").json()[0]
    blocked = client.post(f"/api/events/matchmaking/{own_ticket['id']}/dismiss/")
    assert blocked.status_code == 409

    TerritoryGame.objects.filter(pk=matched["match_id"]).update(
        status="finished", active_player=None, turns_completed=20
    )
    dismissed = client.post(f"/api/events/matchmaking/{own_ticket['id']}/dismiss/")
    assert dismissed.status_code == 200
    assert dismissed.json()["dismissed_at"] is not None
    assert client.get("/api/events/matchmaking/").json() == []

    new_ticket = client.post("/api/events/matchmaking/territory_control/join/")
    assert new_ticket.status_code == 201
    assert new_ticket.json()["status"] == MatchmakingStatus.WAITING
