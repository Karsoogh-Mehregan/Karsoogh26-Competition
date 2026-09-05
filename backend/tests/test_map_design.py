"""The Designer role and the map-design API.

A Designer changes how the board *looks* — never who holds what. The tests pin
that boundary from both sides: designers can write the design and nothing else,
and nobody else can write the design.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client

from core.boards import Board
from game.models import GameSettings, LevelConfig, MapDesign, Neighborhood, Node, Occupancy
from minesweeper.models import MinesweeperDifficulty, MinesweeperSettings
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()

DESIGN_URL = "/api/map/design/"


def node_url(code: str) -> str:
    return f"/api/map/nodes/{code}/"


@pytest.fixture
def team():
    return Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=400)


@pytest.fixture
def player(team):
    session = Client()
    session.force_login(User.objects.create_user("player", password="secret", team=team))
    return session


@pytest.fixture
def mentor():
    user = User.objects.create_user("mentor", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    session = Client()
    session.force_login(user)
    return session


@pytest.fixture
def designer():
    user = User.objects.create_user("designer", password="secret")
    user.groups.add(Group.objects.get(name="Designers"))
    session = Client()
    session.force_login(user)
    return session


@pytest.fixture
def nodes():
    easy = LevelConfig.objects.get(pk="easy")
    hard = LevelConfig.objects.get(pk="hard")
    return {
        "easy": Node.objects.create(board=Board.GIRLS, code="L2_0", level=easy),
        "hard": Node.objects.create(board=Board.GIRLS, code="L6_0", level=hard),
    }


def _patch(client, url, payload):
    return client.patch(url, payload, content_type="application/json")


# --- reading -----------------------------------------------------------------


def test_the_seed_gives_eight_sectors_and_a_settings_row():
    assert Neighborhood.objects.count() == 8
    assert sorted(Neighborhood.objects.values_list("index", flat=True)) == list(range(8))
    assert MapDesign.load().pk == 1


def test_any_logged_in_user_can_read_the_design(player, nodes):
    body = player.get(DESIGN_URL).json()
    assert body["road_style"] == "straight"
    assert body["tint_strength"] == 22
    assert len(body["neighborhoods"]) == 8
    by_code = {row["code"]: row for row in body["nodes"]}
    assert by_code["L6_0"] == {
        "code": "L6_0",
        "level": "hard",
        "capacity": 3,
        "archetype": "",
        "minesweeper": False,
        "gelled": False,
    }
    assert by_code["L2_0"]["capacity"] == 1


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [(True, True), (False, False)],
)
def test_design_reports_where_minesweeper_is_playable(player, nodes, enabled, expected):
    MinesweeperSettings.objects.create(
        node=nodes["hard"], difficulty_id=MinesweeperDifficulty.EASY, enabled=enabled
    )
    by_code = {row["code"]: row for row in player.get(DESIGN_URL).json()["nodes"]}
    assert by_code["L6_0"]["minesweeper"] is expected
    assert by_code["L2_0"]["minesweeper"] is False


def test_design_is_closed_to_anonymous_visitors(client):
    assert client.get(DESIGN_URL).status_code == 403


def test_me_reports_designer_status(designer, player):
    assert designer.get("/api/auth/me/").json()["is_designer"] is True
    assert player.get("/api/auth/me/").json()["is_designer"] is False


# --- who may write -------------------------------------------------------------


@pytest.mark.parametrize("who", ["player", "mentor"])
def test_only_designers_may_write(who, request, nodes):
    session = request.getfixturevalue(who)
    assert _patch(session, DESIGN_URL, {"road_style": "curved"}).status_code == 403
    assert _patch(session, node_url("L6_0"), {"archetype": "mint"}).status_code == 403


def test_a_designer_may_not_touch_the_game(designer):
    """The role is about looks only. The clock and the board stay out of reach."""
    assert _patch(designer, "/api/game/settings/", {"status": "running"}).status_code == 403


# --- map-wide settings -----------------------------------------------------------


def test_designer_changes_roads_and_strengths(designer):
    response = _patch(
        designer, DESIGN_URL, {"road_style": "dashed", "tint_strength": 20, "halo_strength": 0}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["road_style"], body["tint_strength"], body["halo_strength"]) == ("dashed", 20, 0)
    design = MapDesign.load()
    assert (design.road_style, design.tint_strength, design.halo_strength) == ("dashed", 20, 0)


def test_strengths_are_capped_at_100(designer):
    assert _patch(designer, DESIGN_URL, {"tint_strength": 101}).status_code == 400


def test_neighbourhoods_are_patched_by_index(designer):
    response = _patch(
        designer,
        DESIGN_URL,
        {"neighborhoods": [{"index": 3, "color": "#4c7f3b", "name": "سبزها"}]},
    )
    assert response.status_code == 200
    row = Neighborhood.objects.get(index=3)
    assert (row.color, row.name) == ("#4c7f3b", "سبزها")
    # Untouched fields survive a partial row.
    assert row.theme == "history"


def test_a_theme_may_be_swapped_in(designer):
    """Nine themes, eight sectors: the unbuilt theme is available but unassigned."""
    assert not Neighborhood.objects.filter(theme="unbuilt").exists()
    response = _patch(designer, DESIGN_URL, {"neighborhoods": [{"index": 7, "theme": "unbuilt"}]})
    assert response.status_code == 200
    assert Neighborhood.objects.get(index=7).theme == "unbuilt"


def test_a_bad_colour_is_rejected(designer):
    response = _patch(designer, DESIGN_URL, {"neighborhoods": [{"index": 0, "color": "red"}]})
    assert response.status_code == 400


def test_an_unknown_sector_is_404(designer):
    response = _patch(designer, DESIGN_URL, {"neighborhoods": [{"index": 8, "color": "#000000"}]})
    assert response.status_code == 404


# --- per-node pins -------------------------------------------------------------------


def test_designer_pins_and_unpins_a_building(designer, nodes):
    response = _patch(designer, node_url("L6_0"), {"archetype": "observatory"})
    assert response.status_code == 200
    assert response.json()["archetype"] == "observatory"
    assert Node.objects.get(code="L6_0").archetype == "observatory"

    response = _patch(designer, node_url("L6_0"), {"archetype": ""})
    assert response.status_code == 200
    assert Node.objects.get(code="L6_0").archetype == ""


def test_an_unknown_building_type_is_rejected(designer, nodes):
    assert _patch(designer, node_url("L6_0"), {"archetype": "castle"}).status_code == 400


def test_designer_moves_an_empty_node_between_levels(designer, nodes):
    response = _patch(designer, node_url("L2_0"), {"level": "medium"})
    assert response.status_code == 200
    body = response.json()
    assert (body["level"], body["capacity"]) == ("medium", 2)


def test_level_is_frozen_while_a_team_sits_on_the_node(designer, nodes, team):
    Occupancy.objects.create(node=nodes["hard"], team=team, slot=1)
    response = _patch(designer, node_url("L6_0"), {"level": "easy"})
    assert response.status_code == 409
    assert Node.objects.get(code="L6_0").level_id == "hard"


def test_pinning_is_allowed_while_occupied(designer, nodes, team):
    """Only the level touches the rules; the look may change any time."""
    Occupancy.objects.create(node=nodes["hard"], team=team, slot=1)
    assert _patch(designer, node_url("L6_0"), {"archetype": "mint"}).status_code == 200


def test_an_unknown_node_is_404(designer):
    assert _patch(designer, node_url("nope"), {"archetype": "mint"}).status_code == 404


# --- the design lock ------------------------------------------------------------------


@pytest.fixture
def design_locked():
    settings_row = GameSettings.load()
    settings_row.design_locked = True
    settings_row.save(update_fields=["design_locked"])
    return settings_row


def test_a_locked_design_refuses_every_write(designer, nodes, design_locked):
    assert _patch(designer, DESIGN_URL, {"road_style": "curved"}).status_code == 403
    assert _patch(designer, node_url("L6_0"), {"archetype": "mint"}).status_code == 403
    assert MapDesign.load().road_style == "straight"
    assert Node.objects.get(code="L6_0").archetype == ""


def test_a_locked_design_is_still_readable(player, nodes, design_locked):
    assert player.get(DESIGN_URL).status_code == 200


def test_the_lock_rides_on_the_game_state(player, design_locked):
    assert player.get("/api/game/state/").json()["design_locked"] is True


def test_unlocking_hands_the_designer_the_board_back(designer, nodes, design_locked):
    design_locked.design_locked = False
    design_locked.save(update_fields=["design_locked"])
    assert _patch(designer, DESIGN_URL, {"road_style": "curved"}).status_code == 200
