import secrets
from collections.abc import Callable

from django.db import transaction
from django.db.models import Q

from teams.models import Team

from .exceptions import (
    GameAlreadyFinished,
    InvalidStartingCell,
    InvalidTarget,
    NotParticipant,
    NotPlayersTurn,
    SamePlayer,
)
from .models import (
    BOARD_SIZE,
    TOTAL_TURNS,
    TerritoryAction,
    TerritoryCell,
    TerritoryGame,
    TerritoryGameStatus,
    TerritoryTurn,
)


def _random_cell_value() -> int:
    return secrets.randbelow(5) + 1


def _roll_die() -> int:
    return secrets.randbelow(6) + 1


@transaction.atomic
def create_territory_game(
    player_one: Team,
    player_two: Team,
    *,
    cell_value: Callable[[], int] = _random_cell_value,
) -> TerritoryGame:
    if player_one.pk == player_two.pk:
        raise SamePlayer("یک تیم نمی‌تواند هر دو بازیکن مسابقه باشد.")

    game = TerritoryGame.objects.create(
        player_one=player_one,
        player_two=player_two,
        active_player=player_one,
    )
    values = [cell_value() for _ in range(BOARD_SIZE * BOARD_SIZE)]
    if any(
        not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5
        for value in values
    ):
        raise ValueError("Cell value generator must return an integer from 1 to 5.")
    TerritoryCell.objects.bulk_create(
        [
            TerritoryCell(
                game=game,
                row=index // BOARD_SIZE,
                column=index % BOARD_SIZE,
                value=value,
            )
            for index, value in enumerate(values)
        ]
    )
    return game


def _is_boundary(row: int, column: int) -> bool:
    edge = BOARD_SIZE - 1
    return row in (0, edge) or column in (0, edge)


def _is_adjacent_to_territory(game: TerritoryGame, team: Team, row: int, column: int) -> bool:
    neighbours = Q()
    if row > 0:
        neighbours |= Q(row=row - 1, column=column)
    if row < BOARD_SIZE - 1:
        neighbours |= Q(row=row + 1, column=column)
    if column > 0:
        neighbours |= Q(row=row, column=column - 1)
    if column < BOARD_SIZE - 1:
        neighbours |= Q(row=row, column=column + 1)
    return TerritoryCell.objects.filter(game=game, owner=team).filter(neighbours).exists()


def _change_score(game: TerritoryGame, team_id: int, delta: int) -> None:
    if team_id == game.player_one_id:
        game.player_one_score += delta
    elif team_id == game.player_two_id:
        game.player_two_score += delta
    else:
        raise NotParticipant("این تیم در این مسابقه حضور ندارد.")


def _mark_started(game: TerritoryGame, team_id: int) -> None:
    if team_id == game.player_one_id:
        game.player_one_started = True
    elif team_id == game.player_two_id:
        game.player_two_started = True
    else:
        raise NotParticipant("این تیم در این مسابقه حضور ندارد.")


def _other_player_id(game: TerritoryGame, team_id: int) -> int:
    if team_id == game.player_one_id:
        return game.player_two_id
    if team_id == game.player_two_id:
        return game.player_one_id
    raise NotParticipant("این تیم در این مسابقه حضور ندارد.")


@transaction.atomic
def play_territory_turn(
    game_id: int,
    acting_team: Team,
    row: int,
    column: int,
    *,
    roll_die: Callable[[], int] = _roll_die,
) -> TerritoryGame:
    """Resolve one decision while holding the match row lock.

    A player's first decision is an automatic, zero-point starting placement, so it is
    recorded without a die. Every capture or attack after that uses a backend-generated die.
    """
    game = (
        TerritoryGame.objects.select_for_update(of=("self",))
        .select_related("player_one", "player_two", "active_player", "winner")
        .get(pk=game_id)
    )
    other_player_id = _other_player_id(game, acting_team.pk)

    if game.status == TerritoryGameStatus.FINISHED or game.turns_completed >= TOTAL_TURNS:
        raise GameAlreadyFinished("این مسابقه تمام شده است.")
    if game.active_player_id != acting_team.pk:
        raise NotPlayersTurn("اکنون نوبت این تیم نیست.")

    cell = TerritoryCell.objects.select_for_update(of=("self",)).get(
        game=game,
        row=row,
        column=column,
    )
    previous_owner_id = cell.owner_id
    attacker_delta = 0
    defender_delta = 0
    dice_result = None

    if not game.has_started(acting_team.pk):
        if not _is_boundary(row, column) or cell.owner_id is not None:
            raise InvalidStartingCell("خانه شروع باید خالی و روی مرز صفحه باشد.")
        action_type = TerritoryAction.STARTING_POSITION
        success = True
        cell.owner = acting_team
        _mark_started(game, acting_team.pk)
    else:
        if cell.owner_id == acting_team.pk:
            raise InvalidTarget("نمی‌توان خانه‌ای را که از قبل متعلق به تیم است هدف گرفت.")
        if not _is_adjacent_to_territory(game, acting_team, row, column):
            raise InvalidTarget("خانه هدف باید مجاور عمودی یا افقی قلمرو تیم باشد.")

        dice_result = roll_die()
        if (
            not isinstance(dice_result, int)
            or isinstance(dice_result, bool)
            or not 1 <= dice_result <= 6
        ):
            raise ValueError("Dice generator must return an integer from 1 to 6.")

        if cell.owner_id is None:
            action_type = TerritoryAction.NEUTRAL_CAPTURE
            success = dice_result >= cell.value
            if dice_result < cell.value:
                attacker_delta = -(7 - cell.value)
            elif dice_result == cell.value:
                attacker_delta = cell.value - 1
                cell.owner = acting_team
            else:
                attacker_delta = cell.value
                cell.owner = acting_team
        else:
            if cell.owner_id != other_player_id:
                raise InvalidTarget("مالک خانه هدف یکی از بازیکنان این مسابقه نیست.")
            action_type = TerritoryAction.OPPONENT_ATTACK
            success = dice_result >= cell.value
            if success:
                attacker_delta = cell.value
                defender_delta = -cell.value
                cell.owner = acting_team
            else:
                attacker_delta = -(10 - cell.value)

        _change_score(game, acting_team.pk, attacker_delta)
        if defender_delta:
            _change_score(game, other_player_id, defender_delta)

    if cell.owner_id != previous_owner_id:
        cell.save(update_fields=["owner"])

    game.turns_completed += 1
    if game.turns_completed == TOTAL_TURNS:
        game.status = TerritoryGameStatus.FINISHED
        game.active_player = None
        if game.player_one_score > game.player_two_score:
            game.winner_id = game.player_one_id
        elif game.player_two_score > game.player_one_score:
            game.winner_id = game.player_two_id
        else:
            game.winner = None
    else:
        game.active_player_id = other_player_id

    game.save()
    TerritoryTurn.objects.create(
        game=game,
        number=game.turns_completed,
        acting_player=acting_team,
        target_row=row,
        target_column=column,
        target_value=cell.value,
        action_type=action_type,
        dice_result=dice_result,
        success=success,
        attacker_score_change=attacker_delta,
        defender_score_change=defender_delta,
        previous_owner_id=previous_owner_id,
        new_owner_id=cell.owner_id,
    )
    return game
