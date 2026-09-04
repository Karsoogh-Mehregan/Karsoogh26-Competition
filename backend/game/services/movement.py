from django.db import IntegrityError, transaction
from django.db.models import Q

from game.models import GRANTED_SOURCES, Edge, GameSettings, Level, Node, Occupancy
from teams.ledger import InsufficientFunds, apply_balance_change
from teams.models import BalanceReason, Team
from teams.start_colors import color_for_start

from .events import BOARD_NODE_CLAIMED, BOARD_SPAWN_CLAIMED, publish_on_commit
from .mentor import Conflict
from .questions import assign_question, release_expired_attempts


def is_reachable(node: Node, held_ids: set[int]) -> bool:
    """A directed edge a -> b is one-way; undirected rows are normalised a.id < b.id."""
    if not held_ids:
        return False
    return Edge.objects.filter(
        Q(a_id__in=held_ids, b_id=node.pk) | Q(b_id__in=held_ids, a_id=node.pk, directed=False)
    ).exists()


def expandable_node_ids(team: Team) -> set[int]:
    """Everything the team can move *from* right now.

    A reservation only opens its neighbours once it is graded; spawns start
    open. A granted seat — an item takeover or a won duel — expands reach the
    same way a grade does, without a grade. A toll gate the team has beaten
    expands too, and it is the only way onto the ring beyond it — the roads
    through a gate are one-way.

    The minesweeper import is local on purpose: `minesweeper` depends on `game`,
    so a module-level import here would close the loop.
    """
    from minesweeper.crossings import cleared_node_ids

    held = set(
        Occupancy.objects.active()
        .filter(team=team)
        .filter(Q(is_spawn=True) | Q(grade__isnull=False) | Q(source__in=GRANTED_SOURCES))
        .values_list("node_id", flat=True)
    )
    return held | cleared_node_ids(team)


def team_can_access_node(team: Team, node: Node) -> bool:
    """True if `node` is an expandable source or a neighbour of one.

    A cleared gate is in the set itself, which is what lets a team walk back
    onto one it has already beaten.
    """
    expandable = expandable_node_ids(team)
    return node.pk in expandable or is_reachable(node, expandable)


def _reserve(team: Team, node: Node) -> Occupancy:
    if node.level_id == Level.TOLL:
        raise Conflict("عبور از عوارضی با بازی مین‌روب انجام می‌شود، نه با سؤال.")
    held_ids = expandable_node_ids(team)
    if held_ids:
        if not is_reachable(node, held_ids):
            raise Conflict("این خانه به هیچ‌کدام از خانه‌های فعلی تیم متصل نیست.")
    elif Occupancy.objects.active().filter(team=team).exists():
        raise Conflict("تا وقتی این خانه نمره نداشته باشد نمی‌توان همسایه را رزرو کرد.")
    elif team.color is None or color_for_start(node.code) != team.color:
        raise Conflict("اولین حرکت تیم باید روی خانهٔ شروع خودش باشد.")

    level = node.level
    taken = {
        occupancy.slot
        for occupancy in Occupancy.objects.active()
        .filter(node_id=node.pk)
        .select_for_update(of=("self",))
        .order_by("pk")
    }
    slot = next((s for s in range(1, level.capacity + 1) if s not in taken), None)
    if slot is None:
        raise Conflict("ظرفیت این خانه پر شده است.")

    if level.entry_cost:
        try:
            apply_balance_change(
                team,
                -level.entry_cost,
                reason=BalanceReason.ENTRY,
                detail=node.code,
            )
        except InsufficientFunds:
            raise Conflict("موجودی تیم برای ورود به این خانه کافی نیست.")

    try:
        holding = Occupancy.objects.create(
            node=node,
            team=team,
            slot=slot,
            is_spawn=level.pk == Level.SPAWN,
        )
    except IntegrityError as exc:
        raise Conflict("این خانه هم‌زمان توسط تیم دیگری گرفته شد.") from exc

    holding.node = node
    holding.team = team
    return holding


@transaction.atomic
def claim_spawn(team: Team, node: Node) -> Occupancy:
    """Seat a team on its start node, free of charge and without a question.

    Colour ownership is the caller's rule; this only takes the single spawn slot.
    """
    holding = Occupancy.objects.active().filter(team=team, node=node).first()
    if holding is not None:
        return holding
    try:
        holding = Occupancy.objects.create(team=team, node=node, slot=1, is_spawn=True)
    except IntegrityError as exc:
        raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.") from exc
    publish_on_commit(BOARD_SPAWN_CLAIMED, {"team": team.code, "node": node.code})
    return holding


@transaction.atomic
def claim_node(team: Team, node: Node) -> Occupancy:
    """Reserve a node for the team and start its attempt in one move.

    Reserving is not owning: the floor is captured when the attempt is graded.
    A node already reserved by this team is topped up with a question instead of
    being charged again.
    """
    if not GameSettings.load().is_running:
        raise Conflict("بازی در حال اجرا نیست.")

    release_expired_attempts()

    holdings = list(
        Occupancy.objects.active()
        .select_related("node__level", "team")
        .filter(team=team, node=node)
        .order_by("pk")
    )
    if any(row.source in GRANTED_SOURCES for row in holdings):
        raise Conflict("این خانه بدون سؤال در اختیار تیم است و سؤال نمی‌گیرد.")
    holding = holdings[0] if holdings else None
    if holding is None:
        holding = _reserve(team, node)
    elif holding.question_assigned_at is not None:
        raise Conflict("سؤال قبلاً به این تیم تخصیص داده شده است.")

    assign_question(holding)
    holding.refresh_from_db()
    publish_on_commit(BOARD_NODE_CLAIMED, {"team": team.code, "node": node.code})
    return holding
