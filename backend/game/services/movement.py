from django.db import IntegrityError, transaction
from django.db.models import F, Q

from game.models import Edge, GameSettings, Level, Node, Occupancy
from teams.models import Team
from teams.start_colors import color_for_start

from .mentor import Conflict
from .questions import assign_question, release_expired_attempts


def is_reachable(node: Node, held_ids: set[int]) -> bool:
    """A directed edge a -> b is one-way; undirected rows are normalised a.id < b.id."""
    if not held_ids:
        return False
    return Edge.objects.filter(
        Q(a_id__in=held_ids, b_id=node.pk) | Q(b_id__in=held_ids, a_id=node.pk, directed=False)
    ).exists()


def _expandable_node_ids(team: Team) -> set[int]:
    """A reservation only opens its neighbours once it is graded; spawns start open."""
    return set(
        Occupancy.objects.active()
        .filter(team=team)
        .filter(Q(is_spawn=True) | Q(grade__isnull=False))
        .values_list("node_id", flat=True)
    )


def _reserve(team: Team, node: Node) -> Occupancy:
    if Occupancy.objects.active().filter(team=team).exists():
        held_ids = _expandable_node_ids(team)
        if not held_ids:
            raise Conflict("تا وقتی این خانه نمره نداشته باشد نمی‌توان همسایه را رزرو کرد.")
        if not is_reachable(node, held_ids):
            raise Conflict("این خانه به هیچ‌کدام از خانه‌های فعلی تیم متصل نیست.")
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
        paid = Team.objects.filter(pk=team.pk, balance__gte=level.entry_cost).update(
            balance=F("balance") - level.entry_cost
        )
        if not paid:
            raise Conflict("موجودی تیم برای ورود به این خانه کافی نیست.")
        team.refresh_from_db(fields=["balance"])

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
        return Occupancy.objects.create(team=team, node=node, slot=1, is_spawn=True)
    except IntegrityError as exc:
        raise Conflict("این خانهٔ شروع قبلاً گرفته شده است.") from exc


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

    holding = (
        Occupancy.objects.active()
        .select_related("node__level", "team")
        .filter(team=team, node=node)
        .first()
    )
    if holding is None:
        holding = _reserve(team, node)
    elif holding.question_assigned_at is not None:
        raise Conflict("سؤال قبلاً به این تیم تخصیص داده شده است.")

    assign_question(holding)
    holding.refresh_from_db()
    return holding
