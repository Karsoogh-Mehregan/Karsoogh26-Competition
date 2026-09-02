from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from events.exceptions import (
    OlympicsInvalidConfiguration,
    OlympicsInvalidResult,
    OlympicsInvalidState,
    OlympicsInvalidWinner,
    OlympicsSamePlayer,
)
from events.models import (
    OlympicsMiniGame,
    OlympicsOutcome,
    OlympicsResult,
    OlympicsStatus,
)
from events.services import (
    create_olympics_match,
    record_olympics_result,
    start_olympics_match,
)
from teams.models import Team

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def players():
    return (
        Team.objects.create(code="alpha", name="Alpha", balance=500),
        Team.objects.create(code="beta", name="Beta", balance=500),
    )


@pytest.fixture
def mentor():
    user = User.objects.create_user("mentor", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    return user


@pytest.fixture
def zones():
    return [
        {"code": "outer", "label": "Outer", "score": 1},
        {"code": "middle", "label": "Middle", "score": 3},
        {"code": "center", "label": "Center", "score": 5},
    ]


def active_match(mini_game, players, zones=None):
    match = create_olympics_match(mini_game, *players, scoring_zones=zones)
    return start_olympics_match(match.pk)


def test_create_match_supports_both_mini_games_and_requires_distinct_players(players, zones):
    coin = create_olympics_match(OlympicsMiniGame.COIN_NEAR_WALL, *players)
    marble = create_olympics_match(OlympicsMiniGame.MARBLE_TARGET, *players, scoring_zones=zones)

    assert coin.status == OlympicsStatus.CREATED
    assert coin.scoring_zones == []
    assert marble.scoring_zones == zones
    with pytest.raises(OlympicsSamePlayer):
        create_olympics_match(OlympicsMiniGame.COIN_NEAR_WALL, players[0], players[0])
    with pytest.raises(OlympicsInvalidConfiguration):
        create_olympics_match(OlympicsMiniGame.MARBLE_TARGET, *players)


def test_start_is_single_use_and_sets_timestamp(players):
    match = create_olympics_match(OlympicsMiniGame.COIN_NEAR_WALL, *players)

    started = start_olympics_match(match.pk)

    assert started.status == OlympicsStatus.ACTIVE
    assert started.started_at is not None
    with pytest.raises(OlympicsInvalidState):
        start_olympics_match(match.pk)


def test_coin_result_can_use_operator_declared_winner_without_measurements(players, mentor):
    match = active_match(OlympicsMiniGame.COIN_NEAR_WALL, players)

    record_olympics_result(
        match.pk,
        request_id=uuid4(),
        recorded_by=mentor,
        winner=players[1],
    )

    match.refresh_from_db()
    result = match.results.get()
    assert match.status == OlympicsStatus.FINISHED
    assert match.winner == players[1]
    assert result.outcome == OlympicsOutcome.PLAYER_TWO
    assert result.player_one_best_distance is None


def test_coin_measurements_are_audited_and_determine_winner(players, mentor):
    match = active_match(OlympicsMiniGame.COIN_NEAR_WALL, players)

    record_olympics_result(
        match.pk,
        request_id=uuid4(),
        recorded_by=mentor,
        winner=players[0],
        player_one_best_distance=Decimal("8.00"),
        player_two_best_distance=Decimal("9.00"),
    )

    result = OlympicsResult.objects.get(match=match)
    assert result.player_one_best_distance == Decimal("8.00")
    assert result.player_two_best_distance == Decimal("9.00")
    assert result.outcome == OlympicsOutcome.PLAYER_ONE


def test_equal_coin_distances_require_tiebreak_then_second_round_can_finish(players, mentor):
    match = active_match(OlympicsMiniGame.COIN_NEAR_WALL, players)
    record_olympics_result(
        match.pk,
        request_id=uuid4(),
        recorded_by=mentor,
        is_tie=True,
        player_one_best_distance=Decimal("7.50"),
        player_two_best_distance=Decimal("7.50"),
    )

    match.refresh_from_db()
    assert match.status == OlympicsStatus.TIEBREAK
    assert match.winner is None

    record_olympics_result(
        match.pk,
        request_id=uuid4(),
        recorded_by=mentor,
        winner=players[1],
        player_one_best_distance=Decimal("5.00"),
        player_two_best_distance=Decimal("4.25"),
    )
    match.refresh_from_db()
    assert match.status == OlympicsStatus.FINISHED
    assert match.winner == players[1]
    assert list(match.results.values_list("round_number", flat=True)) == [1, 2]


def test_coin_rejects_winner_that_conflicts_with_measurement_or_tie(players, mentor):
    match = active_match(OlympicsMiniGame.COIN_NEAR_WALL, players)
    with pytest.raises(OlympicsInvalidWinner):
        record_olympics_result(
            match.pk,
            request_id=uuid4(),
            recorded_by=mentor,
            winner=players[1],
            player_one_best_distance=Decimal("3.00"),
            player_two_best_distance=Decimal("4.00"),
        )
    with pytest.raises(OlympicsInvalidResult):
        record_olympics_result(
            match.pk,
            request_id=uuid4(),
            recorded_by=mentor,
            winner=players[0],
            player_one_best_distance=Decimal("3.00"),
            player_two_best_distance=Decimal("3.00"),
        )


def test_marble_scores_zones_and_raw_scores_on_backend(players, mentor, zones):
    match = active_match(OlympicsMiniGame.MARBLE_TARGET, players, zones)

    record_olympics_result(
        match.pk,
        request_id=uuid4(),
        recorded_by=mentor,
        player_one_attempts=["middle", "center", 0, 3],
        player_two_attempts=["outer", "middle", "middle", 1],
    )

    match.refresh_from_db()
    result = match.results.get()
    assert result.player_one_total == 11
    assert result.player_two_total == 8
    assert result.player_one_attempts[0] == {"value": "middle", "score": 3}
    assert match.winner == players[0]


def test_marble_tie_requires_flexible_tiebreak_round(players, mentor, zones):
    match = active_match(OlympicsMiniGame.MARBLE_TARGET, players, zones)
    record_olympics_result(
        match.pk,
        request_id=uuid4(),
        recorded_by=mentor,
        is_tie=True,
        player_one_attempts=[1, 3, 5, 0],
        player_two_attempts=[3, 1, 0, 5],
    )

    match.refresh_from_db()
    assert match.status == OlympicsStatus.TIEBREAK

    record_olympics_result(
        match.pk,
        request_id=uuid4(),
        recorded_by=mentor,
        player_one_attempts=["center"],
        player_two_attempts=["outer"],
    )
    match.refresh_from_db()
    assert match.winner == players[0]
    assert match.results.get(round_number=2).player_one_total == 5


def test_marble_rejects_wrong_count_and_unknown_zone(players, mentor, zones):
    match = active_match(OlympicsMiniGame.MARBLE_TARGET, players, zones)
    with pytest.raises(OlympicsInvalidResult):
        record_olympics_result(
            match.pk,
            request_id=uuid4(),
            recorded_by=mentor,
            player_one_attempts=[1],
            player_two_attempts=[1],
        )
    with pytest.raises(OlympicsInvalidResult):
        record_olympics_result(
            match.pk,
            request_id=uuid4(),
            recorded_by=mentor,
            player_one_attempts=["unknown"] * 4,
            player_two_attempts=["outer"] * 4,
        )


def test_result_request_is_idempotent_and_finished_match_rejects_new_result(players, mentor):
    match = active_match(OlympicsMiniGame.COIN_NEAR_WALL, players)
    request_id = uuid4()
    record_olympics_result(match.pk, request_id=request_id, recorded_by=mentor, winner=players[0])
    record_olympics_result(match.pk, request_id=request_id, recorded_by=mentor, winner=players[0])

    assert OlympicsResult.objects.filter(match=match).count() == 1
    with pytest.raises(OlympicsInvalidState):
        record_olympics_result(
            match.pk,
            request_id=uuid4(),
            recorded_by=mentor,
            winner=players[0],
        )
    assert list(Team.objects.order_by("code").values_list("balance", flat=True)) == [500, 500]


def test_api_operator_flow_and_full_audit_response(client, players, mentor):
    client.force_login(mentor)
    created = client.post(
        "/api/events/olympics/matches/",
        {
            "mini_game": "marble_target",
            "player_one": "alpha",
            "player_two": "beta",
            "scoring_zones": [
                {"code": "one", "label": "One", "score": 1},
                {"code": "five", "label": "Five", "score": 5},
            ],
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    match_id = created.json()["id"]
    assert client.post(f"/api/events/olympics/matches/{match_id}/start/").status_code == 200

    result = client.post(
        f"/api/events/olympics/matches/{match_id}/results/",
        {
            "request_id": str(uuid4()),
            "player_one_attempts": ["five", "one", 0, "one"],
            "player_two_attempts": ["one", "one", 0, "one"],
        },
        content_type="application/json",
    )

    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "finished"
    assert body["winner"]["code"] == "alpha"
    assert body["results"][0]["player_one_total"] == 7
    assert body["results"][0]["recorded_by"] == "mentor"
    assert body["tiebreak_occurred"] is False


def test_only_mentor_operates_but_participant_can_read(client, players):
    match = create_olympics_match(OlympicsMiniGame.COIN_NEAR_WALL, *players)
    player_user = User.objects.create_user("alpha", password="secret", team=players[0])
    client.force_login(player_user)

    assert client.get(f"/api/events/olympics/matches/{match.pk}/").status_code == 200
    assert client.post(f"/api/events/olympics/matches/{match.pk}/start/").status_code == 403
    assert (
        client.post(
            f"/api/events/olympics/matches/{match.pk}/results/",
            {"request_id": str(uuid4()), "winner": "alpha"},
            content_type="application/json",
        ).status_code
        == 403
    )

    outsider = Team.objects.create(code="gamma", name="Gamma")
    outsider_user = User.objects.create_user("gamma", password="secret", team=outsider)
    client.force_login(outsider_user)
    assert client.get(f"/api/events/olympics/matches/{match.pk}/").status_code == 403


def test_team_list_contains_only_its_physical_matches(client, players):
    outsider = Team.objects.create(code="gamma", name="Gamma")
    own = create_olympics_match(OlympicsMiniGame.COIN_NEAR_WALL, *players)
    create_olympics_match(OlympicsMiniGame.COIN_NEAR_WALL, players[1], outsider)
    user = User.objects.create_user("alpha", password="secret", team=players[0])
    client.force_login(user)

    response = client.get("/api/events/olympics/matches/")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [own.pk]
