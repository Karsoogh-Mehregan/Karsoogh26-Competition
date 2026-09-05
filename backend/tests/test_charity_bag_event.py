from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.utils import timezone

from core.boards import Board
from events.exceptions import (
    CharityBagAlreadyEntered,
    CharityBagBelowMinimum,
    CharityBagInsufficientBalance,
    CharityBagNotActive,
)
from events.models import (
    CharityBagEvent,
    CharityBagParticipation,
    CharityBagSide,
    CharityBagStatus,
)
from events.services import create_charity_bag, enter_charity_bag, sync_charity_bag
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def teams():
    return (
        Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100),
        Team.objects.create(board=Board.GIRLS, code="beta", name="Beta", balance=100),
        Team.objects.create(board=Board.GIRLS, code="gamma", name="Gamma", balance=100),
    )


@pytest.fixture
def active_event():
    now = timezone.now()
    return create_charity_bag(
        now - timedelta(seconds=5), now + timedelta(minutes=10), board=Board.GIRLS
    )


def _expire(event):
    CharityBagEvent.objects.filter(pk=event.pk).update(
        ends_at=timezone.now() - timedelta(seconds=1)
    )


def test_entry_immediately_deducts_stake(active_event, teams):
    entry = enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 20)

    teams[0].refresh_from_db()
    assert teams[0].balance == 80
    assert entry.amount == entry.stake_deducted == 20
    assert entry.final_payout == 0


def test_entry_requires_current_balance_and_happens_once(active_event, teams):
    with pytest.raises(CharityBagInsufficientBalance):
        enter_charity_bag(active_event.pk, teams[0], CharityBagSide.LIONS, 101)
    assert Team.objects.get(pk=teams[0].pk).balance == 100

    enter_charity_bag(active_event.pk, teams[0], CharityBagSide.LIONS, 50)
    with pytest.raises(CharityBagAlreadyEntered):
        enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 10)
    assert Team.objects.get(pk=teams[0].pk).balance == 50


def test_entry_respects_the_minimum_stake(teams):
    now = timezone.now()
    event = create_charity_bag(
        now - timedelta(seconds=5),
        now + timedelta(minutes=10),
        board=Board.GIRLS,
        minimum_stake=30,
    )

    with pytest.raises(CharityBagBelowMinimum):
        enter_charity_bag(event.pk, teams[0], CharityBagSide.MICE, 29)
    assert Team.objects.get(pk=teams[0].pk).balance == 100

    enter_charity_bag(event.pk, teams[0], CharityBagSide.MICE, 30)
    assert Team.objects.get(pk=teams[0].pk).balance == 70


def test_smaller_mice_account_wins_its_share_of_the_lions_account(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 10)
    enter_charity_bag(active_event.pk, teams[1], CharityBagSide.MICE, 30)
    enter_charity_bag(active_event.pk, teams[2], CharityBagSide.LIONS, 80)
    _expire(active_event)

    event = sync_charity_bag(active_event.pk)

    assert event.status == CharityBagStatus.FINISHED
    assert event.winning_side == CharityBagSide.MICE
    assert event.total_mice == 40
    assert event.total_lions == 80
    # 25% of the mice account takes 25% of the lions account, plus its own stake.
    assert event.participations.get(team=teams[0]).final_payout == 30
    assert event.participations.get(team=teams[1]).final_payout == 90
    assert event.participations.get(team=teams[2]).final_payout == 0
    assert Team.objects.get(pk=teams[0].pk).balance == 120
    assert Team.objects.get(pk=teams[1].pk).balance == 160
    assert Team.objects.get(pk=teams[2].pk).balance == 20


def test_lions_win_pays_double_the_share(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagSide.LIONS, 20)
    enter_charity_bag(active_event.pk, teams[1], CharityBagSide.MICE, 60)
    _expire(active_event)

    event = sync_charity_bag(active_event.pk)

    assert event.winning_side == CharityBagSide.LIONS
    # The single lion owns the whole lions account: 2 x 60 from the fund, plus its stake.
    assert event.participations.get(team=teams[0]).final_payout == 140
    assert Team.objects.get(pk=teams[0].pk).balance == 220
    assert Team.objects.get(pk=teams[1].pk).balance == 40


def test_absent_teams_pay_the_minimum_into_the_losing_account(teams):
    now = timezone.now()
    event = create_charity_bag(
        now - timedelta(seconds=5),
        now + timedelta(minutes=10),
        board=Board.GIRLS,
        minimum_stake=10,
    )
    enter_charity_bag(event.pk, teams[0], CharityBagSide.MICE, 20)
    enter_charity_bag(event.pk, teams[1], CharityBagSide.LIONS, 60)

    event = sync_charity_bag(event.pk, now=now + timedelta(minutes=11))

    # Gamma sat it out: 10 leaves its balance and joins the losing lions account.
    assert event.absent_penalty_total == 10
    assert event.total_lions == 70
    assert event.winning_side == CharityBagSide.MICE
    assert Team.objects.get(pk=teams[2].pk).balance == 90
    assert event.participations.get(team=teams[0]).final_payout == 90
    assert Team.objects.get(pk=teams[0].pk).balance == 170


def test_absent_teams_are_not_fined_when_nobody_wins(teams):
    now = timezone.now()
    event = create_charity_bag(
        now - timedelta(seconds=5),
        now + timedelta(minutes=10),
        board=Board.GIRLS,
        minimum_stake=10,
    )
    enter_charity_bag(event.pk, teams[0], CharityBagSide.MICE, 20)
    enter_charity_bag(event.pk, teams[1], CharityBagSide.LIONS, 20)

    event = sync_charity_bag(event.pk, now=now + timedelta(minutes=11))

    assert event.winning_side is None
    assert event.absent_penalty_total == 0
    assert Team.objects.get(pk=teams[2].pk).balance == 100


def test_an_absent_team_never_pays_more_than_it_holds(teams):
    now = timezone.now()
    Team.objects.filter(pk=teams[2].pk).update(balance=4)
    event = create_charity_bag(
        now - timedelta(seconds=5),
        now + timedelta(minutes=10),
        board=Board.GIRLS,
        minimum_stake=10,
    )
    enter_charity_bag(event.pk, teams[0], CharityBagSide.MICE, 20)
    enter_charity_bag(event.pk, teams[1], CharityBagSide.LIONS, 60)

    event = sync_charity_bag(event.pk, now=now + timedelta(minutes=11))

    assert event.absent_penalty_total == 4
    assert Team.objects.get(pk=teams[2].pk).balance == 0


def test_absent_teams_on_the_other_board_are_untouched(teams):
    now = timezone.now()
    other = Team.objects.create(board=Board.BOYS, code="delta", name="Delta", balance=100)
    event = create_charity_bag(
        now - timedelta(seconds=5),
        now + timedelta(minutes=10),
        board=Board.GIRLS,
        minimum_stake=10,
    )
    enter_charity_bag(event.pk, teams[0], CharityBagSide.MICE, 20)
    enter_charity_bag(event.pk, teams[1], CharityBagSide.LIONS, 60)

    sync_charity_bag(event.pk, now=now + timedelta(minutes=11))

    assert Team.objects.get(pk=other.pk).balance == 100


def test_equal_accounts_refund_every_stake(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 40)
    enter_charity_bag(active_event.pk, teams[1], CharityBagSide.LIONS, 40)
    _expire(active_event)

    event = sync_charity_bag(active_event.pk)

    assert event.winning_side is None
    assert Team.objects.get(pk=teams[0].pk).balance == 100
    assert Team.objects.get(pk=teams[1].pk).balance == 100


def test_an_empty_account_refunds_every_stake(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 40)
    enter_charity_bag(active_event.pk, teams[1], CharityBagSide.MICE, 10)
    _expire(active_event)

    event = sync_charity_bag(active_event.pk)

    assert event.winning_side is None
    assert event.total_mice == 50
    assert event.total_lions == 0
    assert Team.objects.get(pk=teams[0].pk).balance == 100
    assert Team.objects.get(pk=teams[1].pk).balance == 100


def test_settlement_is_idempotent(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 20)
    enter_charity_bag(active_event.pk, teams[1], CharityBagSide.LIONS, 30)
    _expire(active_event)

    sync_charity_bag(active_event.pk)
    first_balances = list(Team.objects.order_by("pk").values_list("balance", flat=True))
    sync_charity_bag(active_event.pk)

    assert list(Team.objects.order_by("pk").values_list("balance", flat=True)) == first_balances


def test_closed_event_rejects_late_entry(active_event, teams):
    _expire(active_event)
    with pytest.raises(CharityBagNotActive):
        enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 10)
    assert Team.objects.get(pk=teams[0].pk).balance == 100


def test_active_api_shows_account_totals_but_hides_other_decisions(client, active_event, teams):
    enter_charity_bag(active_event.pk, teams[1], CharityBagSide.LIONS, 20)
    user = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(user)

    response = client.get(f"/api/events/charity-bag/instances/{active_event.pk}/")

    assert response.status_code == 200
    body = response.json()
    assert body["total_mice"] == 0
    assert body["total_lions"] == 20
    assert body["totals_frozen"] is False
    assert body["participations"] == []
    assert body["my_participation"] is None
    assert body["can_participate"] is True


def test_totals_freeze_in_the_final_minutes(client, teams):
    now = timezone.now()
    event = create_charity_bag(
        now - timedelta(minutes=8), now + timedelta(minutes=2), board=Board.GIRLS
    )
    enter_charity_bag(event.pk, teams[0], CharityBagSide.MICE, 25)
    CharityBagParticipation.objects.filter(event=event).update(
        submitted_at=now - timedelta(minutes=7)
    )
    enter_charity_bag(event.pk, teams[1], CharityBagSide.MICE, 40)
    user = User.objects.create_user("alpha", password="secret", team=teams[2])
    client.force_login(user)

    body = client.get(f"/api/events/charity-bag/instances/{event.pk}/").json()

    assert body["totals_frozen"] is True
    assert body["total_mice"] == 25


def test_finished_api_exposes_audit_result(client, active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagSide.MICE, 20)
    enter_charity_bag(active_event.pk, teams[1], CharityBagSide.LIONS, 30)
    _expire(active_event)
    sync_charity_bag(active_event.pk)
    user = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(user)

    response = client.get(f"/api/events/charity-bag/instances/{active_event.pk}/")

    assert response.status_code == 200
    body = response.json()
    assert body["winning_side"] == "mice"
    assert body["total_mice"] == 20
    assert body["total_lions"] == 30
    assert len(body["participations"]) == 2


def test_participation_api_uses_authenticated_team(client, active_event, teams):
    user = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(user)

    response = client.post(
        f"/api/events/charity-bag/instances/{active_event.pk}/participate/",
        {"side": "mice", "amount": 25},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["my_participation"]["amount"] == 25
    assert Team.objects.get(pk=teams[0].pk).balance == 75


def test_only_mentor_can_create_an_instance(client, teams):
    team_user = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(team_user)
    denied = client.post(
        "/api/events/charity-bag/instances/",
        {"board": Board.GIRLS, "duration_seconds": 600},
        content_type="application/json",
    )
    assert denied.status_code == 403

    mentor = User.objects.create_user("mentor", password="secret")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(mentor)
    created = client.post(
        "/api/events/charity-bag/instances/",
        {"board": Board.GIRLS, "duration_seconds": 600, "minimum_stake": 15},
        content_type="application/json",
    )
    assert created.status_code == 201
    assert created.json()["status"] == "active"
    assert created.json()["minimum_stake"] == 15


def test_schedule_command_is_configurable_and_idempotent(settings):
    settings.CHARITY_BAG_SCHEDULE_TIMES = ["14:30", "15:30", "17:30"]
    settings.CHARITY_BAG_DURATION_SECONDS = 600

    call_command("schedule_charity_bags", date="2026-09-02")
    call_command("schedule_charity_bags", date="2026-09-02")

    # One instance per slot per board: both contests run the same schedule.
    assert CharityBagEvent.objects.count() == 3 * len(Board.values)
    assert {
        int((event.ends_at - event.starts_at).total_seconds())
        for event in CharityBagEvent.objects.all()
    } == {600}
