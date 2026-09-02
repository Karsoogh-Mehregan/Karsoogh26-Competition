import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from events.exceptions import (
    CentipedeInvalidAction,
    CentipedeNotActive,
    CentipedeNotParticipant,
    CentipedeNotPlayersTurn,
)
from events.models import CentipedeAction, CentipedeDecision, CentipedeStatus
from events.services import create_centipede_game, play_centipede_action
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def players():
    return (
        Team.objects.create(code="alpha", name="Alpha", balance=100),
        Team.objects.create(code="beta", name="Beta", balance=100),
    )


@pytest.fixture
def game(players):
    return create_centipede_game(*players)


def test_game_starts_with_finalized_player_order_and_rewards(game, players):
    assert game.status == CentipedeStatus.ACTIVE
    assert game.round_number == 1
    assert game.player_one == players[0]
    assert game.player_two == players[1]
    assert game.active_player == players[0]
    assert game.player_one_reward == 50
    assert game.player_two_reward == 200


def test_player_one_can_take_initial_reward(game, players):
    play_centipede_action(game.pk, players[0], CentipedeAction.TAKE)

    game.refresh_from_db()
    players[0].refresh_from_db()
    players[1].refresh_from_db()
    assert game.status == CentipedeStatus.FINISHED
    assert game.winner == players[0]
    assert game.active_player is None
    assert game.player_one_final_payout == 50
    assert game.player_two_final_payout == 0
    assert players[0].balance == 150
    assert players[1].balance == 100


def test_player_one_continue_passes_turn_without_doubling(game, players):
    play_centipede_action(game.pk, players[0], CentipedeAction.CONTINUE)

    game.refresh_from_db()
    decision = CentipedeDecision.objects.get(game=game)
    assert game.round_number == 1
    assert game.active_player == players[1]
    assert game.player_one_reward == 50
    assert game.player_two_reward == 200
    assert decision.sequence == 1
    assert decision.round_number == 1
    assert decision.displayed_reward == 50


def test_two_continues_double_rewards_and_restart_with_player_one(game, players):
    play_centipede_action(game.pk, players[0], CentipedeAction.CONTINUE)
    play_centipede_action(game.pk, players[1], CentipedeAction.CONTINUE)

    game.refresh_from_db()
    assert game.round_number == 2
    assert game.active_player == players[0]
    assert game.player_one_reward == 100
    assert game.player_two_reward == 400
    assert list(game.decisions.values_list("action", flat=True)) == ["continue", "continue"]


def test_player_two_takes_only_own_current_reward(game, players):
    play_centipede_action(game.pk, players[0], CentipedeAction.CONTINUE)
    play_centipede_action(game.pk, players[1], CentipedeAction.CONTINUE)
    play_centipede_action(game.pk, players[0], CentipedeAction.CONTINUE)
    play_centipede_action(game.pk, players[1], CentipedeAction.TAKE)

    game.refresh_from_db()
    players[0].refresh_from_db()
    players[1].refresh_from_db()
    assert game.winner == players[1]
    assert game.player_one_final_payout == 0
    assert game.player_two_final_payout == 400
    assert players[0].balance == 100
    assert players[1].balance == 500


def test_repeated_finish_request_never_pays_twice(game, players):
    play_centipede_action(game.pk, players[0], CentipedeAction.TAKE)

    with pytest.raises(CentipedeNotActive):
        play_centipede_action(game.pk, players[0], CentipedeAction.TAKE)

    assert Team.objects.get(pk=players[0].pk).balance == 150
    assert CentipedeDecision.objects.filter(game=game).count() == 1


def test_turn_participant_and_action_are_authoritative(game, players):
    outsider = Team.objects.create(code="gamma", name="Gamma", balance=100)
    with pytest.raises(CentipedeNotParticipant):
        play_centipede_action(game.pk, outsider, CentipedeAction.CONTINUE)
    with pytest.raises(CentipedeNotPlayersTurn):
        play_centipede_action(game.pk, players[1], CentipedeAction.CONTINUE)
    with pytest.raises(CentipedeInvalidAction):
        play_centipede_action(game.pk, players[0], "double")


def test_api_returns_complete_state_and_history(client, game, players):
    user = User.objects.create_user("alpha", password="secret", team=players[0])
    client.force_login(user)

    response = client.post(
        f"/api/events/centipede/games/{game.pk}/actions/",
        {"action": "continue"},
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["round_number"] == 1
    assert body["active_player"]["code"] == "beta"
    assert body["players"] == [
        {
            "code": "alpha",
            "name": "Alpha",
            "color": None,
            "position": 1,
            "current_reward": 50,
            "final_payout": 0,
        },
        {
            "code": "beta",
            "name": "Beta",
            "color": None,
            "position": 2,
            "current_reward": 200,
            "final_payout": 0,
        },
    ]
    assert body["history"][0]["action"] == "continue"
    assert body["history"][0]["displayed_reward"] == 50


def test_api_rejects_client_reward_fields(client, game, players):
    user = User.objects.create_user("alpha", password="secret", team=players[0])
    client.force_login(user)

    response = client.post(
        f"/api/events/centipede/games/{game.pk}/actions/",
        {"action": "take", "reward": 999999},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert Team.objects.get(pk=players[0].pk).balance == 100
    assert game.decisions.count() == 0


def test_nonparticipant_cannot_read_or_act(client, game):
    outsider = Team.objects.create(code="gamma", name="Gamma")
    user = User.objects.create_user("gamma", password="secret", team=outsider)
    client.force_login(user)

    detail = client.get(f"/api/events/centipede/games/{game.pk}/")
    action = client.post(
        f"/api/events/centipede/games/{game.pk}/actions/",
        {"action": "continue"},
        content_type="application/json",
    )

    assert detail.status_code == 403
    assert action.status_code == 403


def test_mentor_creates_ordered_game_but_team_cannot(client, players):
    team_user = User.objects.create_user("alpha", password="secret", team=players[0])
    client.force_login(team_user)
    denied = client.post(
        "/api/events/centipede/games/",
        {"player_one": "alpha", "player_two": "beta"},
        content_type="application/json",
    )
    assert denied.status_code == 403

    mentor = User.objects.create_user("mentor", password="secret")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(mentor)
    created = client.post(
        "/api/events/centipede/games/",
        {"player_one": "beta", "player_two": "alpha"},
        content_type="application/json",
    )

    assert created.status_code == 201
    assert created.json()["players"][0]["code"] == "beta"
    assert created.json()["active_player"]["code"] == "beta"


def test_team_list_contains_only_its_games(client, game, players):
    outsider = Team.objects.create(code="gamma", name="Gamma")
    other_game = create_centipede_game(players[1], outsider)
    user = User.objects.create_user("alpha", password="secret", team=players[0])
    client.force_login(user)

    response = client.get("/api/events/centipede/games/")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [game.pk]
    assert other_game.pk != game.pk
