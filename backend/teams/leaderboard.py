"""Rankings, and the freeze snapshot those rankings are taken from.

One ranking per contest. Freeze captures both boards at the moment a game god
flips the switch, so a girls team never sees a boys snapshot. Organisers have
no team and always read live numbers; competing teams see the snapshot.
"""

from core.boards import Board

from .models import Team


def ranked_rows(board: str) -> list[dict]:
    teams = Team.objects.filter(board=board).order_by("-balance", "code")
    return [
        {"rank": rank, "code": team.code, "name": team.name, "balance": team.balance}
        for rank, team in enumerate(teams, start=1)
    ]


def snapshot_all_boards() -> dict[str, list[dict]]:
    return {board: ranked_rows(board) for board, _label in Board.choices}


def sees_frozen_snapshot(user) -> bool:
    """Competing teams see the freeze; organisers have no team and stay live."""
    return bool(getattr(user, "team_id", None))
