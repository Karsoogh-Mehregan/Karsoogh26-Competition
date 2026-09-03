import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from events.exceptions import InvalidStartingCell, InvalidTarget, NotPlayersTurn
from events.models import TerritoryAction, TerritoryCell, TerritoryGameStatus, TerritoryTurn
from events.services import create_territory_game, play_territory_turn
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def players():
    return (
        Team.objects.create(code="alpha", name="Alpha"),
        Team.objects.create(code="beta", name="Beta"),
    )


@pytest.fixture
def game(players):
    return create_territory_game(*players, cell_value=lambda: 3)


def _start_both(game, players):
    play_territory_turn(game.pk, players[0], 0, 0)
    play_territory_turn(game.pk, players[1], 4, 4)
    game.refresh_from_db()


def test_creation_builds_fixed_five_by_five_board(game, players):
    cells = list(game.cells.all())
    assert len(cells) == 25
    assert {(cell.row, cell.column) for cell in cells} == {
        (row, column) for row in range(5) for column in range(5)
    }
    assert {cell.value for cell in cells} == {3}
    assert game.active_player == players[0]
    assert game.turns_completed == 0


def test_first_turn_is_free_boundary_start(game, players):
    play_territory_turn(game.pk, players[0], 0, 2)

    game.refresh_from_db()
    turn = TerritoryTurn.objects.get(game=game)
    assert game.player_one_score == 0
    assert game.player_one_started is True
    assert game.active_player == players[1]
    assert TerritoryCell.objects.get(game=game, row=0, column=2).owner == players[0]
    assert turn.action_type == TerritoryAction.STARTING_POSITION
    assert turn.dice_result is None
    assert turn.attacker_score_change == 0


def test_first_turn_rejects_inner_or_owned_cell(game, players):
    with pytest.raises(InvalidStartingCell):
        play_territory_turn(game.pk, players[0], 2, 2)

    play_territory_turn(game.pk, players[0], 0, 0)
    with pytest.raises(InvalidStartingCell):
        play_territory_turn(game.pk, players[1], 0, 0)


def test_turns_strictly_alternate(game, players):
    with pytest.raises(NotPlayersTurn):
        play_territory_turn(game.pk, players[1], 4, 4)


@pytest.mark.parametrize(
    ("roll", "expected_score", "expected_owner"),
    [(2, -4, None), (3, 2, "alpha"), (4, 3, "alpha")],
)
def test_neutral_capture_scoring(game, players, roll, expected_score, expected_owner):
    _start_both(game, players)

    play_territory_turn(game.pk, players[0], 0, 1, roll_die=lambda: roll)

    game.refresh_from_db()
    cell = TerritoryCell.objects.get(game=game, row=0, column=1)
    assert game.player_one_score == expected_score
    assert cell.owner_id == (players[0].pk if expected_owner else None)


def test_only_orthogonally_adjacent_targets_are_valid(game, players):
    _start_both(game, players)

    with pytest.raises(InvalidTarget):
        play_territory_turn(game.pk, players[0], 1, 1, roll_die=lambda: 6)

    with pytest.raises(InvalidTarget):
        play_territory_turn(game.pk, players[0], 4, 0, roll_die=lambda: 6)


def test_successful_attack_transfers_only_target_and_scores_both_players(game, players):
    _start_both(game, players)
    target = TerritoryCell.objects.get(game=game, row=0, column=1)
    target.owner = players[1]
    target.save(update_fields=["owner"])

    play_territory_turn(game.pk, players[0], 0, 1, roll_die=lambda: 3)

    game.refresh_from_db()
    target.refresh_from_db()
    turn = game.turns.get(number=3)
    assert target.owner == players[0]
    assert game.player_one_score == 3
    assert game.player_two_score == -3
    assert turn.action_type == TerritoryAction.OPPONENT_ATTACK
    assert turn.attacker_score_change == 3
    assert turn.defender_score_change == -3
    assert TerritoryCell.objects.get(game=game, row=4, column=4).owner == players[1]


def test_player_loses_immediately_after_losing_last_territory(game, players):
    _start_both(game, players)
    TerritoryCell.objects.filter(game=game, row=4, column=3).update(owner=players[0])

    play_territory_turn(game.pk, players[0], 4, 4, roll_die=lambda: 6)

    game.refresh_from_db()
    assert game.status == TerritoryGameStatus.FINISHED
    assert game.turns_completed == 3
    assert game.active_player is None
    assert game.winner == players[0]


def test_failed_attack_keeps_owner_and_only_penalizes_attacker(game, players):
    _start_both(game, players)
    target = TerritoryCell.objects.get(game=game, row=0, column=1)
    target.owner = players[1]
    target.save(update_fields=["owner"])

    play_territory_turn(game.pk, players[0], 0, 1, roll_die=lambda: 2)

    game.refresh_from_db()
    target.refresh_from_db()
    assert target.owner == players[1]
    assert game.player_one_score == -7
    assert game.player_two_score == 0


def test_disconnected_owned_cells_still_enable_adjacent_moves(game, players):
    _start_both(game, players)
    TerritoryCell.objects.filter(game=game, row=0, column=1).update(owner=players[1])
    TerritoryCell.objects.filter(game=game, row=0, column=2).update(owner=players[0])

    play_territory_turn(game.pk, players[0], 0, 3, roll_die=lambda: 6)

    assert TerritoryCell.objects.get(game=game, row=0, column=3).owner == players[0]


def test_twentieth_turn_finishes_game_and_selects_winner(game, players):
    _start_both(game, players)
    game.turns_completed = 19
    game.active_player = players[0]
    game.player_two_score = 2
    game.save()

    play_territory_turn(game.pk, players[0], 0, 1, roll_die=lambda: 6)

    game.refresh_from_db()
    assert game.status == TerritoryGameStatus.FINISHED
    assert game.turns_completed == 20
    assert game.turns_remaining == 0
    assert game.active_player is None
    assert game.winner == players[0]


def test_equal_scores_finish_as_draw(game, players):
    _start_both(game, players)
    game.turns_completed = 19
    game.active_player = players[0]
    game.player_two_score = 3
    game.save()

    play_territory_turn(game.pk, players[0], 0, 1, roll_die=lambda: 6)

    game.refresh_from_db()
    assert game.status == TerritoryGameStatus.FINISHED
    assert game.player_one_score == game.player_two_score == 3
    assert game.winner is None


def test_team_api_state_contains_board_players_and_previous_turn(client, game, players):
    user = User.objects.create_user("user-alpha", password="secret", team=players[0])
    client.force_login(user)
    response = client.post(
        f"/api/events/territory-control/games/{game.pk}/turns/",
        {"row": 0, "column": 0},
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["board"]) == 5
    assert all(len(row) == 5 for row in body["board"])
    assert body["players"] == [
        {
            "code": "alpha",
            "name": "Alpha",
            "color": None,
            "score": 0,
            "has_selected_start": True,
        },
        {
            "code": "beta",
            "name": "Beta",
            "color": None,
            "score": 0,
            "has_selected_start": False,
        },
    ]
    assert body["turns_completed"] == 1
    assert body["turns_remaining"] == 19
    assert body["previous_turn"]["action_type"] == "starting_position"
    assert body["previous_turn"]["dice_result"] is None


def test_turn_api_rejects_a_client_supplied_die(client, game, players):
    user = User.objects.create_user("user-alpha", password="secret", team=players[0])
    client.force_login(user)

    response = client.post(
        f"/api/events/territory-control/games/{game.pk}/turns/",
        {"row": 0, "column": 0, "dice_result": 6},
        content_type="application/json",
    )

    assert response.status_code == 400
    assert TerritoryTurn.objects.filter(game=game).count() == 0


def test_nonparticipant_cannot_read_or_move(client, game):
    outsider = Team.objects.create(code="gamma", name="Gamma")
    user = User.objects.create_user("user-gamma", password="secret", team=outsider)
    client.force_login(user)

    detail = client.get(f"/api/events/territory-control/games/{game.pk}/")
    move = client.post(
        f"/api/events/territory-control/games/{game.pk}/turns/",
        {"row": 0, "column": 0},
        content_type="application/json",
    )

    assert detail.status_code == 403
    assert move.status_code == 403


def test_mentor_creates_game_and_board_but_team_cannot(client, players):
    team_user = User.objects.create_user("user-alpha", password="secret", team=players[0])
    client.force_login(team_user)
    denied = client.post(
        "/api/events/territory-control/games/",
        {"player_one": "alpha", "player_two": "beta"},
        content_type="application/json",
    )
    assert denied.status_code == 403

    mentor = User.objects.create_user("mentor", password="secret")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(mentor)
    created = client.post(
        "/api/events/territory-control/games/",
        {"player_one": "alpha", "player_two": "beta"},
        content_type="application/json",
    )

    assert created.status_code == 201
    body = created.json()
    assert body["active_player"]["code"] == "alpha"
    assert {cell["value"] for row in body["board"] for cell in row} <= set(range(1, 6))


def test_team_list_only_contains_its_games(client, game, players):
    outsider = Team.objects.create(code="gamma", name="Gamma")
    other_game = create_territory_game(players[1], outsider, cell_value=lambda: 1)
    user = User.objects.create_user("user-alpha", password="secret", team=players[0])
    client.force_login(user)

    response = client.get("/api/events/territory-control/games/")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [game.pk]
    assert other_game.pk != game.pk
