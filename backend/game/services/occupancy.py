from django.db import IntegrityError, transaction
from django.db.models import Q

from game.api_exceptions import Conflict
from game.models import Edge, Occupancy


def expandable_node_ids(team):
    """Holdings that may open a new neighbour: spawn, or already graded."""
    return (
        Occupancy.objects.active()
        .filter(team=team)
        .filter(Q(is_spawn=True) | Q(grade__isnull=False))
        .values_list("node_id", flat=True)
    )


def team_has_expandable_holding(team) -> bool:
    return expandable_node_ids(team).exists()


def is_adjacent_to_team(team, node) -> bool:
    """True if `node` shares an edge with a spawn or graded holding.

    An ungraded reservation does not unlock further neighbours. Direction on
    the map is display-only; adjacency here is undirected, matching the SPA.
    """
    held_ids = expandable_node_ids(team)
    return Edge.objects.filter(
        Q(a_id=node.pk, b_id__in=held_ids) | Q(b_id=node.pk, a_id__in=held_ids)
    ).exists()


@transaction.atomic
def enter_node(team, node, *, is_spawn: bool = False) -> Occupancy:
    """Take the next free slot on `node`, or return the team's existing holding."""
    existing = (
        Occupancy.objects.active()
        .select_for_update(of=("self",))
        .filter(team_id=team.pk, node_id=node.pk)
        .first()
    )
    if existing:
        return existing

    occupied = list(
        Occupancy.objects.active()
        .select_for_update(of=("self",))
        .filter(node_id=node.pk)
        .order_by("slot")
    )
    used = {row.slot for row in occupied}
    slot = next((index for index in range(1, node.level.capacity + 1) if index not in used), None)
    if slot is None:
        raise Conflict("ظرفیت این خانه پر است.")
    try:
        return Occupancy.objects.create(
            team=team,
            node=node,
            slot=slot,
            is_spawn=is_spawn,
        )
    except IntegrityError as exc:
        raise Conflict("این خانه در حال حاضر قابل رزرو نیست.") from exc
