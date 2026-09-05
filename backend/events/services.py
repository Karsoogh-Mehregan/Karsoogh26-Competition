import secrets
from collections.abc import Callable
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from core.boards import require_same_board
from teams.ledger import apply_balance_change
from teams.models import BalanceReason, Team

from .exceptions import (
    AuctionError,
    CentipedeInvalidAction,
    CentipedeNotActive,
    CentipedeNotParticipant,
    CentipedeNotPlayersTurn,
    CentipedeSamePlayer,
    CharityBagAlreadyEntered,
    CharityBagBelowMinimum,
    CharityBagInsufficientBalance,
    CharityBagInvalidWindow,
    CharityBagNotActive,
    EventUnavailable,
    GameAlreadyFinished,
    InvalidStartingCell,
    InvalidTarget,
    MatchmakingError,
    NotParticipant,
    NotPlayersTurn,
    OlympicsInvalidConfiguration,
    OlympicsInvalidResult,
    OlympicsInvalidState,
    OlympicsInvalidWinner,
    OlympicsSamePlayer,
    PigError,
    SamePlayer,
    WheelError,
)
from .models import (
    BOARD_SIZE,
    TOTAL_TURNS,
    AuctionBid,
    AuctionEvent,
    AuctionPair,
    AuctionStatus,
    CentipedeAction,
    CentipedeDecision,
    CentipedeGame,
    CentipedeStatus,
    CharityBagEvent,
    CharityBagParticipation,
    CharityBagSide,
    CharityBagStatus,
    EventCode,
    EventConfiguration,
    MatchmakingStatus,
    MatchmakingTicket,
    OlympicsMatch,
    OlympicsMiniGame,
    OlympicsOutcome,
    OlympicsPlayerRun,
    OlympicsResult,
    OlympicsStatus,
    PigActionReceipt,
    PigEvent,
    PigEventStatus,
    PigGame,
    PigGameStatus,
    PigRoll,
    TerritoryAction,
    TerritoryCell,
    TerritoryGame,
    TerritoryGameStatus,
    TerritoryTurn,
    WheelDeliveryStatus,
    WheelEvent,
    WheelPrize,
    WheelPrizeType,
    WheelSpin,
    WheelStatus,
)

MATCHMAKING_EVENT_CODES = {
    EventCode.TERRITORY_CONTROL,
    EventCode.CENTIPEDE,
    EventCode.OLYMPICS_COIN,
    EventCode.OLYMPICS_MARBLE,
}

TIMED_EVENT_DEFAULTS = {
    EventCode.CHARITY_BAG: 1800,
    EventCode.LIMITED_AUCTION: 1800,
}


def ensure_event_configurations() -> list[EventConfiguration]:
    existing = {item.code: item for item in EventConfiguration.objects.all()}
    missing = [
        EventConfiguration(
            code=code,
            duration_seconds=TIMED_EVENT_DEFAULTS.get(code),
        )
        for code, _label in EventCode.choices
        if code not in existing
    ]
    if missing:
        EventConfiguration.objects.bulk_create(missing, ignore_conflicts=True)
    return list(EventConfiguration.objects.order_by("code"))


def require_event_enabled(code: str) -> EventConfiguration:
    configuration, _ = EventConfiguration.objects.get_or_create(
        code=code,
        defaults={"duration_seconds": TIMED_EVENT_DEFAULTS.get(code)},
    )
    if not configuration.enabled:
        raise EventUnavailable("این رویداد توسط مدیر غیرفعال شده است.")
    return configuration


def _create_matchmaking_game(
    event_code: str, player_one: Team, player_two: Team, configuration: EventConfiguration
) -> int:
    if event_code == EventCode.TERRITORY_CONTROL:
        return create_territory_game(player_one, player_two).pk
    if event_code == EventCode.CENTIPEDE:
        try:
            return create_centipede_game(player_one, player_two).pk
        except CentipedeInvalidAction as exc:
            raise MatchmakingError(str(exc)) from exc
    if event_code == EventCode.OLYMPICS_COIN:
        return create_olympics_match(OlympicsMiniGame.COIN_NEAR_WALL, player_one, player_two).pk
    if event_code == EventCode.OLYMPICS_MARBLE:
        scoring_zones = configuration.settings.get("scoring_zones")
        if not scoring_zones:
            raise MatchmakingError("مناطق امتیازی تیله هنوز توسط مدیر تنظیم نشده‌اند.")
        return create_olympics_match(
            OlympicsMiniGame.MARBLE_TARGET,
            player_one,
            player_two,
            scoring_zones,
        ).pk
    raise MatchmakingError("این رویداد مسابقه دونفره خودکار ندارد.")


@transaction.atomic
def join_matchmaking(event_code: str, team: Team) -> MatchmakingTicket:
    if event_code not in MATCHMAKING_EVENT_CODES:
        raise MatchmakingError("این رویداد از صف همتایابی پشتیبانی نمی‌کند.")
    configuration = require_event_enabled(event_code)
    if event_code == EventCode.CENTIPEDE and Team.objects.get(pk=team.pk).balance < 100:
        raise MatchmakingError("برای ورود به هزارپا به ۱۰۰ گلوریوم نیاز دارید.")
    active_match = (
        MatchmakingTicket.objects.select_for_update()
        .filter(
            event_code=event_code,
            team=team,
            status=MatchmakingStatus.MATCHED,
            dismissed_at__isnull=True,
        )
        .first()
    )
    if active_match:
        raise MatchmakingError("ابتدا از مسابقه قبلی خارج شوید، سپس دوباره وارد صف شوید.")
    current = (
        MatchmakingTicket.objects.select_for_update()
        .filter(event_code=event_code, team=team, status=MatchmakingStatus.WAITING)
        .first()
    )
    if current:
        return current
    opponent = (
        MatchmakingTicket.objects.select_for_update()
        .filter(
            event_code=event_code,
            status=MatchmakingStatus.WAITING,
            team__board=team.board,
        )
        .exclude(team=team)
        .order_by("created_at")
        .first()
    )
    if opponent is None:
        return MatchmakingTicket.objects.create(event_code=event_code, team=team)

    match_id = _create_matchmaking_game(event_code, opponent.team, team, configuration)
    now = timezone.now()
    opponent.status = MatchmakingStatus.MATCHED
    opponent.matched_team = team
    opponent.match_id = match_id
    opponent.matched_at = now
    opponent.save(update_fields=["status", "matched_team", "match_id", "matched_at"])
    return MatchmakingTicket.objects.create(
        event_code=event_code,
        team=team,
        status=MatchmakingStatus.MATCHED,
        matched_team=opponent.team,
        match_id=match_id,
        matched_at=now,
    )


@transaction.atomic
def cancel_matchmaking(event_code: str, team: Team) -> MatchmakingTicket:
    ticket = (
        MatchmakingTicket.objects.select_for_update()
        .filter(event_code=event_code, team=team, status=MatchmakingStatus.WAITING)
        .first()
    )
    if ticket is None:
        raise MatchmakingError("صف فعالی برای لغو وجود ندارد.")
    ticket.status = MatchmakingStatus.CANCELLED
    ticket.save(update_fields=["status"])
    return ticket


def _match_is_finished(ticket: MatchmakingTicket) -> bool:
    if ticket.match_id is None:
        return False
    if ticket.event_code == EventCode.TERRITORY_CONTROL:
        return TerritoryGame.objects.filter(
            pk=ticket.match_id, status=TerritoryGameStatus.FINISHED
        ).exists()
    if ticket.event_code == EventCode.CENTIPEDE:
        return CentipedeGame.objects.filter(
            pk=ticket.match_id, status=CentipedeStatus.FINISHED
        ).exists()
    if ticket.event_code in {EventCode.OLYMPICS_COIN, EventCode.OLYMPICS_MARBLE}:
        return OlympicsMatch.objects.filter(
            pk=ticket.match_id, status=OlympicsStatus.FINISHED
        ).exists()
    return False


@transaction.atomic
def dismiss_matchmaking(ticket_id: int, team: Team) -> MatchmakingTicket:
    ticket = MatchmakingTicket.objects.select_for_update().get(pk=ticket_id, team=team)
    if ticket.status != MatchmakingStatus.MATCHED:
        raise MatchmakingError("این بلیت به مسابقه فعالی متصل نیست.")
    if ticket.dismissed_at is not None:
        return ticket
    if not _match_is_finished(ticket):
        raise MatchmakingError("تا پایان مسابقه نمی‌توانید از آن خارج شوید.")
    ticket.dismissed_at = timezone.now()
    ticket.save(update_fields=["dismissed_at"])
    return ticket


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
    require_same_board(player_one, player_two)

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


@transaction.atomic
def create_charity_bag(
    starts_at,
    ends_at,
    *,
    board: str,
    minimum_stake: int = 0,
    freeze_seconds: int = 180,
) -> CharityBagEvent:
    if ends_at <= starts_at:
        raise CharityBagInvalidWindow("زمان پایان رویداد باید بعد از زمان شروع باشد.")
    now = timezone.now()
    status = CharityBagStatus.ACTIVE if starts_at <= now < ends_at else CharityBagStatus.SCHEDULED
    event = CharityBagEvent.objects.create(
        board=board,
        starts_at=starts_at,
        ends_at=ends_at,
        status=status,
        minimum_stake=minimum_stake,
        freeze_seconds=freeze_seconds,
    )
    if now >= ends_at:
        return sync_charity_bag(event.pk, now=now)
    return event


def charity_bag_totals(event: CharityBagEvent, *, now=None) -> dict:
    """Per-side totals as the players may see them: live, frozen, or final."""
    if event.status == CharityBagStatus.FINISHED:
        return {
            CharityBagSide.MICE: event.total_mice,
            CharityBagSide.LIONS: event.total_lions,
            "frozen": True,
        }
    now = now or timezone.now()
    freeze_at = event.freeze_at
    frozen = now >= freeze_at
    rows = [
        entry
        for entry in event.participations.all()
        if not frozen or entry.submitted_at < freeze_at
    ]
    return {
        CharityBagSide.MICE: sum(
            entry.amount for entry in rows if entry.side == CharityBagSide.MICE
        ),
        CharityBagSide.LIONS: sum(
            entry.amount for entry in rows if entry.side == CharityBagSide.LIONS
        ),
        "frozen": frozen,
    }


def _charge_absent_teams(event: CharityBagEvent, seated_team_ids: list[int]) -> int:
    """Fine every team on the board that skipped a compulsory round.

    Taking part is compulsory, so a team that sat the round out pays the
    minimum stake — capped at what it actually holds — and that money is poured
    into the losing account, where the winners share it out. It is only charged
    when there *is* a winner: with a tie, or an account nobody joined, every
    stake is refunded and there is nobody to hand a fine to.
    """
    if not event.minimum_stake:
        return 0

    absent = (
        Team.objects.select_for_update(of=("self",))
        .filter(board=event.board)
        .exclude(pk__in=seated_team_ids)
        .order_by("pk")
    )
    penalties = 0
    for team in absent:
        charge = min(event.minimum_stake, team.balance)
        if charge <= 0:
            continue
        apply_balance_change(
            team,
            -charge,
            reason=BalanceReason.EVENT,
            detail=f"Charity Bag #{event.pk}: absent penalty",
        )
        penalties += charge
    return penalties


def _settle_locked_charity_bag(event: CharityBagEvent, now) -> None:
    participations = list(
        CharityBagParticipation.objects.select_for_update(of=("self",))
        .filter(event=event)
        .select_related("team")
        .order_by("team_id")
    )
    team_ids = [entry.team_id for entry in participations]
    if team_ids:
        list(Team.objects.select_for_update(of=("self",)).filter(pk__in=team_ids).order_by("pk"))

    totals = {
        side: sum(entry.amount for entry in participations if entry.side == side)
        for side in CharityBagSide.values
    }
    mice = totals[CharityBagSide.MICE]
    lions = totals[CharityBagSide.LIONS]

    winning_side = None
    if mice and lions and mice != lions:
        winning_side = CharityBagSide.MICE if mice < lions else CharityBagSide.LIONS

    # The fines land in the losing account after the winner is known, so they
    # swell the prize without ever deciding which account was the smaller one.
    penalties = _charge_absent_teams(event, team_ids) if winning_side else 0
    losing_side = (
        None
        if winning_side is None
        else (CharityBagSide.LIONS if winning_side == CharityBagSide.MICE else CharityBagSide.MICE)
    )
    if losing_side is not None:
        totals[losing_side] += penalties

    for entry in participations:
        if winning_side is None:
            payout = entry.amount
        elif entry.side == winning_side:
            multiplier = 2 if winning_side == CharityBagSide.LIONS else 1
            payout = (
                entry.amount
                + entry.amount * totals[losing_side] * multiplier // totals[winning_side]
            )
        else:
            payout = 0
        if payout:
            apply_balance_change(
                entry.team,
                payout,
                reason=BalanceReason.EVENT,
                detail=f"Charity Bag #{event.pk}: payout",
            )
        entry.final_payout = payout
        entry.settled_at = now
        entry.save(update_fields=["final_payout", "settled_at"])

    event.total_mice = totals[CharityBagSide.MICE]
    event.total_lions = totals[CharityBagSide.LIONS]
    event.absent_penalty_total = penalties
    event.winning_side = winning_side
    event.status = CharityBagStatus.FINISHED
    event.settled_at = now
    event.save(
        update_fields=[
            "total_mice",
            "total_lions",
            "absent_penalty_total",
            "winning_side",
            "status",
            "settled_at",
            "updated_at",
        ]
    )


@transaction.atomic
def sync_charity_bag(event_id: int, *, now=None) -> CharityBagEvent:
    now = now or timezone.now()
    event = CharityBagEvent.objects.select_for_update(of=("self",)).get(pk=event_id)

    if event.status == CharityBagStatus.FINISHED:
        return event
    if event.status == CharityBagStatus.SCHEDULED and event.starts_at <= now < event.ends_at:
        event.status = CharityBagStatus.ACTIVE
        event.save(update_fields=["status", "updated_at"])
    if now >= event.ends_at and event.status in {
        CharityBagStatus.SCHEDULED,
        CharityBagStatus.ACTIVE,
    }:
        event.status = CharityBagStatus.RESOLVING
        event.settlement_started_at = now
        event.save(update_fields=["status", "settlement_started_at", "updated_at"])
    if event.status == CharityBagStatus.RESOLVING:
        _settle_locked_charity_bag(event, now)
    return event


def sync_due_charity_bags(*, now=None) -> None:
    now = now or timezone.now()
    ids = (
        CharityBagEvent.objects.exclude(status=CharityBagStatus.FINISHED)
        .filter(Q(starts_at__lte=now) | Q(status=CharityBagStatus.RESOLVING))
        .values_list("pk", flat=True)
    )
    for event_id in ids:
        sync_charity_bag(event_id, now=now)


@transaction.atomic
def enter_charity_bag(
    event_id: int,
    team: Team,
    side: str,
    amount: int,
) -> CharityBagParticipation:
    now = timezone.now()
    event = CharityBagEvent.objects.select_for_update(of=("self",)).get(pk=event_id)
    require_same_board(event, team)

    if event.status == CharityBagStatus.SCHEDULED and event.starts_at <= now < event.ends_at:
        event.status = CharityBagStatus.ACTIVE
        event.save(update_fields=["status", "updated_at"])
    if now >= event.ends_at:
        if event.status != CharityBagStatus.FINISHED:
            if event.status != CharityBagStatus.RESOLVING:
                event.status = CharityBagStatus.RESOLVING
                event.settlement_started_at = now
                event.save(update_fields=["status", "settlement_started_at", "updated_at"])
            _settle_locked_charity_bag(event, now)
        raise CharityBagNotActive("مهلت شرکت در مؤسسه خیریه تمام شده است.")
    if event.status != CharityBagStatus.ACTIVE or now < event.starts_at:
        raise CharityBagNotActive("مؤسسه خیریه در حال حاضر فعال نیست.")
    if CharityBagParticipation.objects.filter(event=event, team=team).exists():
        raise CharityBagAlreadyEntered("این تیم قبلاً در این نوبت خیریه شرکت کرده است.")

    locked_team = Team.objects.select_for_update(of=("self",)).get(pk=team.pk)
    if amount <= 0 or amount > locked_team.balance:
        raise CharityBagInsufficientBalance("مبلغ باید مثبت و حداکثر برابر موجودی فعلی تیم باشد.")
    if amount < event.minimum_stake:
        raise CharityBagBelowMinimum(f"حداقل مبلغ این نوبت {event.minimum_stake} گیلریوم است.")

    apply_balance_change(
        locked_team, -amount, reason=BalanceReason.EVENT, detail=f"Charity Bag #{event.pk}: entry"
    )
    return CharityBagParticipation.objects.create(
        event=event,
        team=locked_team,
        side=side,
        amount=amount,
        stake_deducted=amount,
    )


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
    opponent_has_no_territory = (
        game.player_one_started
        and game.player_two_started
        and not TerritoryCell.objects.filter(game=game, owner_id=other_player_id).exists()
    )
    if opponent_has_no_territory:
        game.status = TerritoryGameStatus.FINISHED
        game.active_player = None
        game.winner = acting_team
    elif game.turns_completed == TOTAL_TURNS:
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


@transaction.atomic
def create_centipede_game(player_one: Team, player_two: Team) -> CentipedeGame:
    """Fund a shared pot atomically, locking both balances in a stable order."""
    if player_one.pk == player_two.pk:
        raise CentipedeSamePlayer("دو بازیکن بازی هزارپا باید دو تیم متفاوت باشند.")
    require_same_board(player_one, player_two)
    players = list(
        Team.objects.select_for_update()
        .filter(pk__in=[player_one.pk, player_two.pk])
        .order_by("pk")
    )
    if len(players) != 2 or any(player.balance < 100 for player in players):
        raise CentipedeInvalidAction("هر بازیکن برای ورود به هزارپا به ۱۰۰ گلوریوم نیاز دارد.")
    for player in players:
        apply_balance_change(player, -100, reason=BalanceReason.EVENT, detail="Centipede: entry")
    return CentipedeGame.objects.create(
        player_one=player_one,
        player_two=player_two,
        active_player=None,
    )


@transaction.atomic
def play_centipede_action(
    game_id: int,
    acting_team: Team,
    action: str,
    round_number: int,
) -> CentipedeGame:
    game = CentipedeGame.objects.select_for_update().get(pk=game_id)
    if acting_team.pk not in (game.player_one_id, game.player_two_id):
        raise CentipedeNotParticipant("این تیم بازیکن این بازی نیست.")
    if game.status != CentipedeStatus.ACTIVE:
        raise CentipedeNotActive("این بازی تمام شده است.")
    if round_number != game.round_number:
        raise CentipedeInvalidAction("این تصمیم مربوط به دور قبلی است؛ صفحه را تازه کنید.")
    if game.rules_version == 1:
        return _play_legacy_centipede_action(game_id, acting_team, action)
    if action not in ("produce", "split", "steal", "preserve"):
        raise CentipedeInvalidAction("تصمیم معتبر نیست.")
    if action == "produce" and game.production_rounds >= 4:
        raise CentipedeInvalidAction("چهار مرحله تولید انجام شده؛ گزینه دیگری انتخاب کنید.")
    if game.decisions.filter(round_number=round_number, actor=acting_team).exists():
        raise CentipedeInvalidAction("تصمیم این دور قبلاً ثبت شده است.")
    game.actions_completed += 1
    CentipedeDecision.objects.create(
        game=game,
        actor=acting_team,
        action=action,
        sequence=game.actions_completed,
        round_number=round_number,
        displayed_reward=game.pot,
    )
    choices = dict(
        game.decisions.filter(round_number=round_number).values_list("actor_id", "action")
    )
    if len(choices) == 2:
        first, second = choices[game.player_one_id], choices[game.player_two_id]
        if first == second == "produce":
            game.production_rounds += 1
            game.round_number += 1
            game.pot += 200
        else:

            def share(own, other):
                if own == "preserve":
                    return game.pot // 5
                if own == "steal":
                    return (
                        0
                        if other == "steal"
                        else game.pot - (game.pot // 5 if other == "preserve" else 0)
                    )
                if own == "split" and other != "steal":
                    return game.pot // 2
                return 0

            game.player_one_final_payout = share(first, second)
            game.player_two_final_payout = share(second, first)
            players = list(
                Team.objects.select_for_update()
                .filter(pk__in=[game.player_one_id, game.player_two_id])
                .order_by("pk")
            )
            payouts = {
                game.player_one_id: game.player_one_final_payout,
                game.player_two_id: game.player_two_final_payout,
            }
            for player in players:
                apply_balance_change(
                    player,
                    payouts[player.pk],
                    reason=BalanceReason.EVENT,
                    detail=f"Centipede #{game.pk}: payout",
                )
            game.status = CentipedeStatus.FINISHED
            game.finished_at = timezone.now()
            if game.player_one_final_payout != game.player_two_final_payout:
                game.winner_id = (
                    game.player_one_id
                    if game.player_one_final_payout > game.player_two_final_payout
                    else game.player_two_id
                )
    game.save()
    return game


@transaction.atomic
def _play_legacy_centipede_action(
    game_id: int,
    acting_team: Team,
    action: str,
) -> CentipedeGame:
    if action not in (CentipedeAction.TAKE, CentipedeAction.CONTINUE):
        raise CentipedeInvalidAction("تصمیم بازی باید TAKE یا CONTINUE باشد.")

    game = (
        CentipedeGame.objects.select_for_update(of=("self",))
        .select_related("player_one", "player_two", "active_player")
        .get(pk=game_id)
    )
    if acting_team.pk not in (game.player_one_id, game.player_two_id):
        raise CentipedeNotParticipant("این تیم بازیکن این بازی هزارپا نیست.")
    if game.status != CentipedeStatus.ACTIVE:
        raise CentipedeNotActive("این بازی هزارپا فعال نیست.")
    if game.active_player_id != acting_team.pk:
        raise CentipedeNotPlayersTurn("اکنون نوبت این تیم نیست.")

    is_player_one = acting_team.pk == game.player_one_id
    displayed_reward = game.player_one_reward if is_player_one else game.player_two_reward
    action_round = game.round_number
    game.actions_completed += 1

    if action == CentipedeAction.TAKE:
        now = timezone.now()
        locked_team = Team.objects.select_for_update(of=("self",)).get(pk=acting_team.pk)
        apply_balance_change(
            locked_team,
            displayed_reward,
            reason=BalanceReason.EVENT,
            detail=f"Centipede #{game.pk}: payout",
        )
        game.status = CentipedeStatus.FINISHED
        game.active_player = None
        game.winner = acting_team
        game.finished_at = now
        if is_player_one:
            game.player_one_final_payout = displayed_reward
        else:
            game.player_two_final_payout = displayed_reward
    elif is_player_one:
        game.active_player_id = game.player_two_id
    else:
        game.player_one_reward *= 2
        game.player_two_reward *= 2
        game.round_number += 1
        game.active_player_id = game.player_one_id

    game.save()
    CentipedeDecision.objects.create(
        game=game,
        sequence=game.actions_completed,
        round_number=action_round,
        actor=acting_team,
        action=action,
        displayed_reward=displayed_reward,
    )
    return game


def _validate_scoring_zones(scoring_zones: list[dict]) -> list[dict]:
    if not scoring_zones:
        raise OlympicsInvalidConfiguration("برای تیله هدف حداقل یک منطقه امتیازی تعریف کنید.")
    normalized = []
    seen_codes = set()
    for zone in scoring_zones:
        if not isinstance(zone, dict):
            raise OlympicsInvalidConfiguration("ساختار منطقه امتیازی معتبر نیست.")
        code = str(zone.get("code", "")).strip()
        label = str(zone.get("label", "")).strip()
        score = zone.get("score")
        if (
            not code
            or not label
            or isinstance(score, bool)
            or not isinstance(score, int)
            or score < 0
        ):
            raise OlympicsInvalidConfiguration(
                "هر منطقه باید کد، عنوان و امتیاز نامنفی داشته باشد."
            )
        if code in seen_codes:
            raise OlympicsInvalidConfiguration("کد مناطق امتیازی باید یکتا باشد.")
        seen_codes.add(code)
        normalized.append({"code": code, "label": label, "score": score})
    return normalized


@transaction.atomic
def create_olympics_match(
    mini_game: str,
    player_one: Team,
    player_two: Team,
    scoring_zones: list[dict] | None = None,
) -> OlympicsMatch:
    if player_one.pk == player_two.pk:
        raise OlympicsSamePlayer("دو شرکت‌کننده مسابقه باید متفاوت باشند.")
    require_same_board(player_one, player_two)
    if mini_game not in OlympicsMiniGame.values:
        raise OlympicsInvalidConfiguration("نوع مینی‌گیم معتبر نیست.")
    zones = scoring_zones or []
    if mini_game == OlympicsMiniGame.MARBLE_TARGET:
        zones = _validate_scoring_zones(zones)
    elif zones:
        raise OlympicsInvalidConfiguration("سکه نزدیک دیوار منطقه امتیازی ندارد.")
    return OlympicsMatch.objects.create(
        mini_game=mini_game,
        player_one=player_one,
        player_two=player_two,
        scoring_zones=zones,
    )


@transaction.atomic
def start_olympics_match(match_id: int) -> OlympicsMatch:
    match = OlympicsMatch.objects.select_for_update(of=("self",)).get(pk=match_id)
    if match.status != OlympicsStatus.CREATED:
        raise OlympicsInvalidState("فقط مسابقه ساخته‌شده را می‌توان آغاز کرد.")
    match.status = OlympicsStatus.ACTIVE
    match.started_at = timezone.now()
    match.save(update_fields=["status", "started_at", "updated_at"])
    return match


def _marble_attempts(attempts: list, scoring_zones: list[dict]) -> tuple[list[dict], int]:
    zone_scores = {zone["code"]: zone["score"] for zone in scoring_zones}
    valid_scores = set(zone_scores.values()) | {0}
    normalized = []
    for attempt in attempts:
        if isinstance(attempt, str):
            if attempt not in zone_scores:
                raise OlympicsInvalidResult(f"منطقه امتیازی «{attempt}» تعریف نشده است.")
            score = zone_scores[attempt]
        elif isinstance(attempt, int) and not isinstance(attempt, bool):
            if attempt not in valid_scores:
                raise OlympicsInvalidResult("امتیاز ثبت‌شده با مناطق این مسابقه سازگار نیست.")
            score = attempt
        else:
            raise OlympicsInvalidResult("هر تلاش باید کد منطقه یا امتیاز نامنفی معتبر باشد.")
        normalized.append({"value": attempt, "score": score})
    return normalized, sum(item["score"] for item in normalized)


@transaction.atomic
def record_olympics_result(
    match_id: int,
    *,
    request_id,
    recorded_by,
    winner: Team | None = None,
    is_tie: bool = False,
    player_one_best_distance=None,
    player_two_best_distance=None,
    player_one_attempts: list | None = None,
    player_two_attempts: list | None = None,
) -> OlympicsMatch:
    match = OlympicsMatch.objects.select_for_update(of=("self",)).get(pk=match_id)
    existing_result = OlympicsResult.objects.filter(request_id=request_id).first()
    if existing_result is not None:
        if existing_result.match_id == match.pk:
            return match
        raise OlympicsInvalidResult("شناسه ثبت نتیجه قبلاً برای مسابقه دیگری استفاده شده است.")
    if match.status not in (
        OlympicsStatus.ACTIVE,
        OlympicsStatus.WAITING_FOR_RESULT,
        OlympicsStatus.TIEBREAK,
    ):
        raise OlympicsInvalidState("این مسابقه آماده ثبت نتیجه نیست.")
    if winner is not None and winner.pk not in (match.player_one_id, match.player_two_id):
        raise OlympicsInvalidWinner("برنده باید یکی از دو شرکت‌کننده مسابقه باشد.")

    round_number = match.results.count() + 1
    outcome = OlympicsOutcome.TIE
    p1_attempts: list[dict] = []
    p2_attempts: list[dict] = []
    p1_total = p2_total = None
    p1_distance = player_one_best_distance
    p2_distance = player_two_best_distance

    if match.mini_game == OlympicsMiniGame.COIN_NEAR_WALL:
        if player_one_attempts or player_two_attempts:
            raise OlympicsInvalidResult("برای بازی سکه فقط برنده یا فاصله بهترین سکه را ثبت کنید.")
        if (p1_distance is None) != (p2_distance is None):
            raise OlympicsInvalidResult("فاصله بهترین سکه را برای هر دو شرکت‌کننده وارد کنید.")
        calculated_winner = None
        if p1_distance is not None:
            if p1_distance < 0 or p2_distance < 0:
                raise OlympicsInvalidResult("فاصله سکه نمی‌تواند منفی باشد.")
            if p1_distance < p2_distance:
                calculated_winner = match.player_one
            elif p2_distance < p1_distance:
                calculated_winner = match.player_two
            if (calculated_winner is None) != is_tie:
                raise OlympicsInvalidResult("نتیجه اعلام‌شده با فاصله‌های ثبت‌شده سازگار نیست.")
            if calculated_winner is not None and winner != calculated_winner:
                raise OlympicsInvalidWinner("برنده اعلام‌شده با نزدیک‌ترین سکه سازگار نیست.")
        elif is_tie:
            if winner is not None:
                raise OlympicsInvalidWinner("نتیجه مساوی نمی‌تواند برنده داشته باشد.")
        elif winner is None:
            raise OlympicsInvalidWinner("برنده یا تساوی مسابقه سکه را مشخص کنید.")
    else:
        if p1_distance is not None or p2_distance is not None:
            raise OlympicsInvalidResult("فاصله سکه برای بازی تیله قابل ثبت نیست.")
        raw_one = player_one_attempts or []
        raw_two = player_two_attempts or []
        required_count = 4 if round_number == 1 else None
        if not raw_one or len(raw_one) != len(raw_two):
            raise OlympicsInvalidResult(
                "تعداد تلاش‌های دو شرکت‌کننده باید برابر و بیشتر از صفر باشد."
            )
        if required_count and len(raw_one) != required_count:
            raise OlympicsInvalidResult("در دور اصلی هر شرکت‌کننده باید چهار تیله ثبت کند.")
        p1_attempts, p1_total = _marble_attempts(raw_one, match.scoring_zones)
        p2_attempts, p2_total = _marble_attempts(raw_two, match.scoring_zones)
        calculated_winner = None
        if p1_total > p2_total:
            calculated_winner = match.player_one
        elif p2_total > p1_total:
            calculated_winner = match.player_two
        if (calculated_winner is None) != is_tie:
            raise OlympicsInvalidResult("نتیجه اعلام‌شده با مجموع امتیازها سازگار نیست.")
        if calculated_winner is not None and winner is not None and winner != calculated_winner:
            raise OlympicsInvalidWinner("برنده اعلام‌شده با مجموع امتیازها سازگار نیست.")
        winner = calculated_winner

    if is_tie:
        winner = None
        match.status = OlympicsStatus.TIEBREAK
    else:
        outcome = (
            OlympicsOutcome.PLAYER_ONE
            if winner.pk == match.player_one_id
            else OlympicsOutcome.PLAYER_TWO
        )
        match.status = OlympicsStatus.FINISHED
        match.winner = winner
        match.finished_at = timezone.now()

    OlympicsResult.objects.create(
        match=match,
        request_id=request_id,
        round_number=round_number,
        player_one_attempts=p1_attempts,
        player_two_attempts=p2_attempts,
        player_one_total=p1_total,
        player_two_total=p2_total,
        player_one_best_distance=p1_distance,
        player_two_best_distance=p2_distance,
        outcome=outcome,
        recorded_by=recorded_by,
    )
    match.save(update_fields=["status", "winner", "finished_at", "updated_at"])
    return match


@transaction.atomic
def submit_olympics_player_run(
    match_id: int,
    team: Team,
    *,
    round_number: int,
    attempts: list | None = None,
    best_distance=None,
) -> OlympicsMatch:
    match = OlympicsMatch.objects.select_for_update(of=("self",)).get(pk=match_id)
    if match.status not in {
        OlympicsStatus.ACTIVE,
        OlympicsStatus.WAITING_FOR_RESULT,
        OlympicsStatus.TIEBREAK,
    }:
        raise OlympicsInvalidState("این مسابقه آماده پرتاب نیست.")
    if team.pk not in (match.player_one_id, match.player_two_id):
        raise OlympicsInvalidResult("این تیم در مسابقه حضور ندارد.")

    if round_number != match.results.count() + 1:
        raise OlympicsInvalidState("این نتیجه متعلق به دور فعلی نیست.")
    values = attempts or []
    if match.mini_game == OlympicsMiniGame.COIN_NEAR_WALL:
        if best_distance is None or best_distance < 0 or values:
            raise OlympicsInvalidResult("نتیجه سکه باید فقط شامل فاصله بهترین سکه باشد.")
    else:
        required_count = 4 if round_number == 1 else None
        if not values or (required_count and len(values) != required_count):
            raise OlympicsInvalidResult("در دور اصلی هر بازیکن باید چهار تیله پرتاب کند.")
        allowed_scores = {0, *(zone["score"] for zone in match.scoring_zones)}
        if any(type(value) is not int or value not in allowed_scores for value in values):
            raise OlympicsInvalidResult("امتیاز تیله با مناطق این مسابقه سازگار نیست.")
        if best_distance is not None:
            raise OlympicsInvalidResult("برای تیله فاصله ثبت نمی‌شود.")

    existing = OlympicsPlayerRun.objects.filter(
        match=match, team=team, round_number=round_number
    ).first()
    if existing:
        if existing.attempts != values or existing.best_distance != best_distance:
            raise OlympicsInvalidResult("پرتاب‌های ثبت‌شده قابل تغییر نیستند.")
        return match
    OlympicsPlayerRun.objects.create(
        match=match,
        team=team,
        round_number=round_number,
        attempts=values,
        best_distance=best_distance,
    )
    if (
        OlympicsPlayerRun.objects.filter(match=match, round_number=round_number).count() == 2
        and match.status != OlympicsStatus.WAITING_FOR_RESULT
    ):
        match.status = OlympicsStatus.WAITING_FOR_RESULT
        match.save(update_fields=["status", "updated_at"])
    return match


@transaction.atomic
def create_auction_event(
    *,
    board: str,
    duration_seconds: int = 600,
    reward: int = 1000,
    opening_bid: int = 10,
    now=None,
) -> AuctionEvent:
    if duration_seconds <= 0 or reward <= 0 or opening_bid <= 0:
        raise AuctionError("مدت، جایزه و پیشنهاد آغازین باید مثبت باشند.")
    now = now or timezone.now()
    teams = list(
        Team.objects.select_for_update(of=("self",))
        .filter(board=board)
        .order_by("-balance", "code")
    )
    if not teams:
        raise AuctionError("برای شروع حراج حداقل یک تیم لازم است.")
    snapshot = [
        {"rank": index, "code": team.code, "name": team.name, "balance": team.balance}
        for index, team in enumerate(teams, start=1)
    ]
    event = AuctionEvent.objects.create(
        board=board,
        status=AuctionStatus.ACTIVE,
        reward=reward,
        opening_bid=opening_bid,
        duration_seconds=duration_seconds,
        ranking_snapshot=snapshot,
        starts_at=now,
        ends_at=now + timedelta(seconds=duration_seconds),
    )
    for offset in range(0, len(teams), 2):
        first = teams[offset]
        second = teams[offset + 1] if offset + 1 < len(teams) else None
        automatic = second is None
        AuctionPair.objects.create(
            event=event,
            team_one=first,
            team_two=second,
            rank_one=offset + 1,
            rank_two=offset + 2 if second else None,
            status=AuctionStatus.FINISHED if automatic else AuctionStatus.ACTIVE,
            automatic_award=automatic,
            winner=first if automatic else None,
            settled_at=now if automatic else None,
        )
        if automatic:
            apply_balance_change(
                first,
                reward,
                reason=BalanceReason.EVENT,
                detail=f"Auction #{event.pk}: automatic award",
            )
    if all(pair.automatic_award for pair in event.pairs.all()):
        event.status = AuctionStatus.FINISHED
        event.settled_at = now
        event.save(update_fields=["status", "settled_at", "updated_at"])
    return event


def _settle_locked_auction(event: AuctionEvent, now) -> AuctionEvent:
    if event.status == AuctionStatus.FINISHED:
        return event
    pairs = list(
        AuctionPair.objects.select_for_update(of=("self",))
        .select_related("highest_bidder")
        .filter(event=event)
    )
    winner_ids = [pair.highest_bidder_id for pair in pairs if pair.highest_bidder_id]
    if winner_ids:
        list(Team.objects.select_for_update(of=("self",)).filter(pk__in=winner_ids))
    for pair in pairs:
        if pair.status == AuctionStatus.FINISHED:
            continue
        pair.status = AuctionStatus.FINISHED
        pair.winner_id = pair.highest_bidder_id
        pair.settled_at = now
        pair.save(update_fields=["status", "winner", "settled_at"])
        if pair.winner_id:
            apply_balance_change(
                pair.highest_bidder,
                event.reward,
                reason=BalanceReason.EVENT,
                detail=f"Auction #{event.pk}: payout",
            )
    event.status = AuctionStatus.FINISHED
    event.settled_at = now
    event.save(update_fields=["status", "settled_at", "updated_at"])
    return event


@transaction.atomic
def settle_auction_event(event_id: int, *, now=None) -> AuctionEvent:
    now = now or timezone.now()
    event = AuctionEvent.objects.select_for_update(of=("self",)).get(pk=event_id)
    if event.status == AuctionStatus.FINISHED:
        return event
    if now < event.ends_at:
        raise AuctionError("زمان حراج هنوز تمام نشده است.")
    return _settle_locked_auction(event, now)


@transaction.atomic
def place_auction_bid(
    pair_id: int, team: Team, amount: int, request_id, *, now=None
) -> AuctionPair:
    now = now or timezone.now()
    existing = AuctionBid.objects.filter(request_id=request_id).select_related("pair").first()
    if existing:
        if existing.team_id == team.pk and existing.pair_id == pair_id:
            return existing.pair
        raise AuctionError("شناسه این پیشنهاد قبلاً استفاده شده است.")
    pair = (
        AuctionPair.objects.select_for_update(of=("self",)).select_related("event").get(pk=pair_id)
    )
    event = AuctionEvent.objects.select_for_update(of=("self",)).get(pk=pair.event_id)
    if event.status != AuctionStatus.ACTIVE or pair.status != AuctionStatus.ACTIVE:
        raise AuctionError("این حراج فعال نیست.")
    if now >= event.ends_at:
        _settle_locked_auction(event, now)
        raise AuctionError("مهلت حراج تمام شده است.")
    if team.pk not in (pair.team_one_id, pair.team_two_id):
        raise AuctionError("این تیم عضو این حراج نیست.")
    if not isinstance(amount, int) or isinstance(amount, bool):
        raise AuctionError("پیشنهاد باید عدد صحیح باشد.")
    if amount < event.opening_bid or amount <= pair.highest_bid:
        raise AuctionError("پیشنهاد باید از بالاترین پیشنهاد فعلی بیشتر باشد.")
    current_commitment = pair.team_one_bid if team.pk == pair.team_one_id else pair.team_two_bid
    delta = amount - current_commitment
    locked_team = Team.objects.select_for_update(of=("self",)).get(pk=team.pk)
    if delta > locked_team.balance:
        raise AuctionError("موجودی آزاد تیم برای این پیشنهاد کافی نیست.")
    apply_balance_change(
        locked_team, -delta, reason=BalanceReason.EVENT, detail=f"Auction #{event.pk}: bid"
    )
    if team.pk == pair.team_one_id:
        pair.team_one_bid = amount
    else:
        pair.team_two_bid = amount
    pair.highest_bid = amount
    pair.highest_bidder = team
    pair.save(update_fields=["team_one_bid", "team_two_bid", "highest_bid", "highest_bidder"])
    AuctionBid.objects.create(
        pair=pair,
        request_id=request_id,
        sequence=pair.bids.count() + 1,
        team=team,
        amount=amount,
        committed_delta=delta,
    )
    return pair


def _validate_wheel_prizes(prizes: list[dict]) -> list[dict]:
    if not prizes:
        raise WheelError("حداقل یک جایزه لازم است.")
    codes = set()
    grand_count = 0
    normalized = []
    for prize in prizes:
        code = str(prize.get("code", "")).strip()
        prize_type = prize.get("prize_type")
        name = str(prize.get("display_name", "")).strip()
        weight = prize.get("weight")
        amount = prize.get("glorium_amount", 0)
        stock = prize.get("stock")
        if not code or code in codes or not name:
            raise WheelError("کد و نام جایزه باید پر و کدها یکتا باشند.")
        if prize_type not in WheelPrizeType.values:
            raise WheelError("نوع جایزه معتبر نیست.")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            raise WheelError("وزن هر جایزه باید عدد صحیح مثبت باشد.")
        if prize_type == WheelPrizeType.GLORIUM and amount <= 0:
            raise WheelError("جایزه گلوریوم باید مبلغ مثبت داشته باشد.")
        if prize_type != WheelPrizeType.GLORIUM and amount:
            raise WheelError("فقط جایزه گلوریوم می‌تواند مبلغ گلوریوم داشته باشد.")
        if stock is not None and stock < 0:
            raise WheelError("موجودی کالا نمی‌تواند منفی باشد.")
        grand_count += prize_type == WheelPrizeType.GRAND_PRIZE
        codes.add(code)
        normalized.append(
            {
                "code": code,
                "prize_type": prize_type,
                "display_name": name,
                "glorium_amount": amount,
                "reward_data": prize.get("reward_data", {}),
                "weight": weight,
                "stock": stock,
                "available": prize.get("available", True),
            }
        )
    if grand_count != 1:
        raise WheelError("گردونه باید دقیقاً یک جایزه بزرگ داشته باشد.")
    return normalized


@transaction.atomic
def create_wheel_event(*, board: str, spin_cost: int = 10, prizes: list[dict]) -> WheelEvent:
    if spin_cost <= 0:
        raise WheelError("هزینه چرخاندن باید مثبت باشد.")
    normalized = _validate_wheel_prizes(prizes)
    event = WheelEvent.objects.create(board=board, spin_cost=spin_cost)
    WheelPrize.objects.bulk_create([WheelPrize(event=event, **prize) for prize in normalized])
    return event


@transaction.atomic
def start_wheel_event(event_id: int) -> WheelEvent:
    event = WheelEvent.objects.select_for_update(of=("self",)).get(pk=event_id)
    if event.status != WheelStatus.SCHEDULED:
        raise WheelError("فقط گردونه زمان‌بندی‌شده را می‌توان شروع کرد.")
    event.status = WheelStatus.ACTIVE
    event.started_at = timezone.now()
    event.save(update_fields=["status", "started_at", "updated_at"])
    return event


@transaction.atomic
def stop_wheel_event(event_id: int, *, cancelled: bool = False) -> WheelEvent:
    event = WheelEvent.objects.select_for_update(of=("self",)).get(pk=event_id)
    if event.status not in (WheelStatus.SCHEDULED, WheelStatus.ACTIVE):
        raise WheelError("این گردونه قبلاً بسته شده است.")
    event.status = WheelStatus.CANCELLED if cancelled else WheelStatus.FINISHED
    event.finished_at = timezone.now()
    event.save(update_fields=["status", "finished_at", "updated_at"])
    return event


def _weighted_prize(prizes: list[WheelPrize], randbelow: Callable[[int], int]) -> WheelPrize:
    total = sum(prize.weight for prize in prizes)
    ticket = randbelow(total)
    for prize in prizes:
        if ticket < prize.weight:
            return prize
        ticket -= prize.weight
    raise RuntimeError("Weighted selection failed.")


@transaction.atomic
def spin_wheel(event_id: int, team: Team, request_id, *, randbelow=secrets.randbelow) -> WheelSpin:
    existing = WheelSpin.objects.filter(request_id=request_id).first()
    if existing:
        if existing.event_id == event_id and existing.team_id == team.pk:
            return existing
        raise WheelError("شناسه این چرخش قبلاً استفاده شده است.")
    event = WheelEvent.objects.select_for_update(of=("self",)).get(pk=event_id)
    require_same_board(event, team)
    if event.status != WheelStatus.ACTIVE:
        raise WheelError("گردونه فعال نیست.")
    prizes = list(WheelPrize.objects.select_for_update(of=("self",)).filter(event=event))
    candidates = [
        prize
        for prize in prizes
        if prize.available and not prize.claimed and (prize.stock is None or prize.stock > 0)
    ]
    if not candidates:
        raise WheelError("هیچ جایزه قابل انتخابی باقی نمانده است.")
    locked_team = Team.objects.select_for_update(of=("self",)).get(pk=team.pk)
    if locked_team.balance < event.spin_cost:
        raise WheelError("موجودی تیم برای چرخاندن گردونه کافی نیست.")
    prize = _weighted_prize(candidates, randbelow)
    apply_balance_change(
        locked_team, -event.spin_cost, reason=BalanceReason.EVENT, detail=f"Wheel #{event.pk}: spin"
    )
    event.total_collected += event.spin_cost
    payout = 0
    delivery = WheelDeliveryStatus.NOT_APPLICABLE
    if prize.prize_type == WheelPrizeType.GLORIUM:
        payout = prize.glorium_amount
        apply_balance_change(
            locked_team, payout, reason=BalanceReason.EVENT, detail=f"Wheel #{event.pk}: payout"
        )
    elif prize.prize_type == WheelPrizeType.MERCHANDISE:
        delivery = WheelDeliveryStatus.PENDING
        if prize.stock is not None:
            prize.stock -= 1
            if prize.stock == 0:
                prize.available = False
            prize.save(update_fields=["stock", "available"])
    else:
        prize.claimed = True
        prize.available = False
        prize.save(update_fields=["claimed", "available"])
        event.status = WheelStatus.GRAND_PRIZE_CLAIMED
        event.grand_prize_winner = team
        event.finished_at = timezone.now()
    event.save(
        update_fields=[
            "total_collected",
            "status",
            "grand_prize_winner",
            "finished_at",
            "updated_at",
        ]
    )
    return WheelSpin.objects.create(
        event=event,
        request_id=request_id,
        team=team,
        spin_cost=event.spin_cost,
        prize=prize,
        prize_type=prize.prize_type,
        prize_name=prize.display_name,
        glorium_payout=payout,
        delivery_status=delivery,
    )


@transaction.atomic
def deliver_wheel_prize(spin_id: int) -> WheelSpin:
    spin = WheelSpin.objects.select_for_update(of=("self",)).get(pk=spin_id)
    if spin.delivery_status == WheelDeliveryStatus.DELIVERED:
        return spin
    if spin.delivery_status != WheelDeliveryStatus.PENDING:
        raise WheelError("این چرخش جایزه کالای در انتظار تحویل ندارد.")
    spin.delivery_status = WheelDeliveryStatus.DELIVERED
    spin.delivered_at = timezone.now()
    spin.save(update_fields=["delivery_status", "delivered_at"])
    return spin


@transaction.atomic
def create_pig_event(*, board: str, max_pot: int, entry_fee: int = 200) -> PigEvent:
    if max_pot <= 0 or entry_fee <= 0:
        raise PigError("ورودی و سقف دیگ باید مثبت باشند.")
    return PigEvent.objects.create(board=board, max_pot=max_pot, entry_fee=entry_fee)


@transaction.atomic
def finish_pig_event(event_id: int) -> PigEvent:
    event = PigEvent.objects.select_for_update(of=("self",)).get(pk=event_id)
    if event.status == PigEventStatus.FINISHED:
        return event
    event.status = PigEventStatus.FINISHED
    event.finished_at = timezone.now()
    event.save(update_fields=["status", "finished_at"])
    return event


@transaction.atomic
def start_pig_game(event_id: int, team: Team) -> PigGame:
    event = PigEvent.objects.select_for_update(of=("self",)).get(pk=event_id)
    require_same_board(event, team)
    if event.status != PigEventStatus.ACTIVE:
        raise PigError("رویداد بازی خوک فعال نیست.")
    if PigGame.objects.filter(event=event, team=team, status=PigGameStatus.ACTIVE).exists():
        raise PigError("این تیم یک بازی فعال دارد.")
    locked_team = Team.objects.select_for_update(of=("self",)).get(pk=team.pk)
    if locked_team.balance < event.entry_fee:
        raise PigError("موجودی تیم برای پرداخت ورودی کافی نیست.")
    apply_balance_change(
        locked_team, -event.entry_fee, reason=BalanceReason.EVENT, detail=f"Pig #{event.pk}: entry"
    )
    return PigGame.objects.create(
        event=event,
        team=team,
        entry_fee=event.entry_fee,
        max_pot=event.max_pot,
    )


@transaction.atomic
def play_pig_action(
    game_id: int,
    team: Team,
    action: str,
    request_id,
    *,
    roll_die: Callable[[], int] = _roll_die,
) -> PigGame:
    game = PigGame.objects.select_for_update(of=("self",)).get(pk=game_id)
    existing = PigActionReceipt.objects.filter(request_id=request_id).first()
    if existing:
        if existing.game_id == game.pk:
            return game
        raise PigError("شناسه این اقدام قبلاً استفاده شده است.")
    if game.team_id != team.pk:
        raise PigError("این بازی متعلق به این تیم نیست.")
    if game.status != PigGameStatus.ACTIVE:
        raise PigError("این بازی دیگر فعال نیست.")
    if action not in ("roll", "cash_out"):
        raise PigError("اقدام باید ROLL یا CASH_OUT باشد.")
    if action == "cash_out" and game.pot == 0:
        raise PigError("قبل از برداشت باید حداقل یک تاس موفق داشته باشید.")

    PigActionReceipt.objects.create(game=game, request_id=request_id, action=action)
    if action == "cash_out":
        locked_team = Team.objects.select_for_update(of=("self",)).get(pk=team.pk)
        apply_balance_change(
            locked_team, game.pot, reason=BalanceReason.EVENT, detail=f"Pig #{game.pk}: payout"
        )
        game.final_payout = game.pot
        game.status = PigGameStatus.FINISHED_CASHED_OUT
        game.finished_at = timezone.now()
        game.save(update_fields=["final_payout", "status", "finished_at"])
        return game

    dice = roll_die()
    if not isinstance(dice, int) or isinstance(dice, bool) or not 1 <= dice <= 6:
        raise ValueError("Dice generator must return an integer from 1 to 6.")
    game.rolls_count += 1
    amount_added = 0 if dice == 1 else dice * 10
    if dice == 1:
        game.pot = 0
        game.status = PigGameStatus.FINISHED_ROLLED_ONE
        game.finished_at = timezone.now()
    else:
        game.pot = min(game.pot + amount_added, game.max_pot)
        if game.pot >= game.max_pot:
            locked_team = Team.objects.select_for_update(of=("self",)).get(pk=team.pk)
            apply_balance_change(
                locked_team, game.pot, reason=BalanceReason.EVENT, detail=f"Pig #{game.pk}: payout"
            )
            game.final_payout = game.pot
            game.status = PigGameStatus.FINISHED_MAX_POT
            game.finished_at = timezone.now()
    PigRoll.objects.create(
        game=game,
        request_id=request_id,
        number=game.rolls_count,
        dice_result=dice,
        amount_added=amount_added,
        pot_after=game.pot,
    )
    game.save(
        update_fields=[
            "rolls_count",
            "pot",
            "status",
            "final_payout",
            "finished_at",
        ]
    )
    return game
