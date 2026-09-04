from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection

from core.boards import Board
from events.exceptions import CentipedeInvalidAction, CentipedeNotActive, CentipedeNotParticipant
from events.models import CentipedeGame
from events.services import create_centipede_game, play_centipede_action
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def players():
    return (
        Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100),
        Team.objects.create(board=Board.GIRLS, code="beta", name="Beta", balance=100),
    )


@pytest.fixture
def game(players):
    return create_centipede_game(*players)


def balances(players):
    return [Team.objects.get(pk=p.pk).balance for p in players]


def test_entry_funds_pot_once(game, players):
    assert balances(players) == [0, 0]
    assert (game.pot, game.production_rounds, game.round_number) == (200, 0, 1)
    assert game.status == "active"
    assert game.active_player is None
    assert game.rules_version == 2


def test_insufficient_entry_is_atomic(players):
    Team.objects.filter(pk=players[1].pk).update(balance=99)
    with pytest.raises(CentipedeInvalidAction):
        create_centipede_game(*players)
    assert balances(players) == [100, 99]
    assert not CentipedeGame.objects.exists()


# Explicit payout expectations for every ordered pair at a 200-Glorium pot.
PAIRS = [
    ("produce", "produce", None),
    ("produce", "split", (0, 100)),
    ("produce", "steal", (0, 200)),
    ("produce", "preserve", (0, 40)),
    ("split", "produce", (100, 0)),
    ("split", "split", (100, 100)),
    ("split", "steal", (0, 200)),
    ("split", "preserve", (100, 40)),
    ("steal", "produce", (200, 0)),
    ("steal", "split", (200, 0)),
    ("steal", "steal", (0, 0)),
    ("steal", "preserve", (160, 40)),
    ("preserve", "produce", (40, 0)),
    ("preserve", "split", (40, 100)),
    ("preserve", "steal", (40, 160)),
    ("preserve", "preserve", (40, 40)),
]


@pytest.mark.parametrize(("first", "second", "expected"), PAIRS)
@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_all_choice_pairs_in_both_arrival_orders(game, players, first, second, expected, order):
    choices = [first, second]
    play_centipede_action(game.pk, players[order[0]], choices[order[0]], 1)
    assert balances(players) == [0, 0]
    game.refresh_from_db()
    assert game.status == "active"
    assert game.pot == 200
    play_centipede_action(game.pk, players[order[1]], choices[order[1]], 1)
    game.refresh_from_db()
    assert game.decisions.count() == 2
    if expected is None:
        assert game.status == "active"
        assert (game.pot, game.production_rounds, game.round_number) == (400, 1, 2)
        assert balances(players) == [0, 0]
    else:
        assert game.status == "finished"
        assert game.finished_at is not None
        assert (game.player_one_final_payout, game.player_two_final_payout) == expected
        assert balances(players) == list(expected)
        with pytest.raises(CentipedeNotActive):
            play_centipede_action(game.pk, players[order[1]], choices[order[1]], 1)
        assert balances(players) == list(expected)


def test_four_productions_disable_action_but_do_not_finish(game, players):
    for round_number in range(1, 5):
        for player in players:
            play_centipede_action(game.pk, player, "produce", round_number)
    game.refresh_from_db()
    assert (game.pot, game.round_number, game.production_rounds) == (1000, 5, 4)
    assert game.status == "active"
    for player in players:
        with pytest.raises(CentipedeInvalidAction):
            play_centipede_action(game.pk, player, "produce", 5)
    assert game.decisions.count() == 8
    play_centipede_action(game.pk, players[0], "steal", 5)
    play_centipede_action(game.pk, players[1], "preserve", 5)
    assert balances(players) == [800, 200]


def test_repeated_changed_and_stale_choices_are_rejected(game, players):
    play_centipede_action(game.pk, players[0], "produce", 1)
    for action in ["produce", "steal"]:
        with pytest.raises(CentipedeInvalidAction):
            play_centipede_action(game.pk, players[0], action, 1)
    play_centipede_action(game.pk, players[1], "produce", 1)
    with pytest.raises(CentipedeInvalidAction):
        play_centipede_action(game.pk, players[0], "produce", 1)
    assert game.decisions.count() == 2


def test_invalid_actions_and_outsider(game, players):
    outsider = Team.objects.create(board=Board.GIRLS, code="outsider", name="Outsider")
    with pytest.raises(CentipedeNotParticipant):
        play_centipede_action(game.pk, outsider, "steal", 1)
    for action in ["take", "continue", "invalid"]:
        with pytest.raises(CentipedeInvalidAction):
            play_centipede_action(game.pk, players[0], action, 1)
    assert not game.decisions.exists()


def test_pending_choice_hidden_on_all_api_surfaces(client, game, players):
    users = [User.objects.create_user(p.code, password="secret", team=p) for p in players]
    client.force_login(users[0])
    path = f"/api/events/centipede/games/{game.pk}/"
    response = client.post(
        path + "actions/", {"action": "steal", "round_number": 1}, content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["history"] == []
    assert response.json()["players"][0]["has_chosen"] is True
    client.force_login(users[1])
    assert client.get(path).json()["history"] == []
    assert client.get("/api/events/centipede/games/").json()[0]["history"] == []
    response = client.post(
        path + "actions/",
        {"action": "preserve", "round_number": 1},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert [d["action"] for d in response.json()["history"]] == ["steal", "preserve"]
    assert [p["final_payout"] for p in response.json()["players"]] == [160, 40]


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "steal"},
        {"action": "steal", "round_number": 1, "pot": 9999},
        {"action": "invalid", "round_number": 1},
    ],
)
def test_api_rejects_missing_round_and_client_economy(client, game, players, payload):
    client.force_login(User.objects.create_user("alpha", password="secret", team=players[0]))
    response = client.post(
        f"/api/events/centipede/games/{game.pk}/actions/", payload, content_type="application/json"
    )
    assert response.status_code == 400
    assert not game.decisions.exists()


def test_permissions_and_mentor_creation(client, players):
    outsider = Team.objects.create(board=Board.GIRLS, code="outside", name="Outside")
    client.force_login(User.objects.create_user("outside", password="secret", team=outsider))
    assert (
        client.post(
            "/api/events/centipede/games/", {"player_one": "alpha", "player_two": "beta"}
        ).status_code
        == 403
    )
    mentor = User.objects.create_user("mentor", password="secret")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(mentor)
    response = client.post(
        "/api/events/centipede/games/", {"player_one": "alpha", "player_two": "beta"}
    )
    assert response.status_code == 201
    path = f"/api/events/centipede/games/{response.json()['id']}/"
    assert client.post(path + "actions/", {"action": "steal", "round_number": 1}).status_code == 403
    client.force_login(User.objects.get(username="outside"))
    assert client.get(path).status_code == 403
    assert client.get("/api/events/centipede/games/").json() == []
    assert client.post(path + "actions/", {"action": "steal", "round_number": 1}).status_code == 403


def test_legacy_game_keeps_original_rules_and_balances(players):
    game = CentipedeGame.objects.create(
        rules_version=1, player_one=players[0], player_two=players[1], active_player=players[0]
    )
    play_centipede_action(game.pk, players[0], "take", 1)
    assert balances(players) == [150, 100]


@pytest.mark.postgres_only
@pytest.mark.django_db(transaction=True)
def test_simultaneous_finishing_requests_pay_once(players):
    game = create_centipede_game(*players)
    play_centipede_action(game.pk, players[0], "preserve", 1)
    barrier = Barrier(2)

    def finish(_):
        barrier.wait(timeout=10)
        try:
            play_centipede_action(game.pk, players[1], "steal", 1)
            return "paid"
        except CentipedeNotActive:
            return "rejected"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(finish, range(2)))
    assert sorted(outcomes) == ["paid", "rejected"]
    assert balances(players) == [40, 160]
    assert game.decisions.count() == 2
