from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.utils import timezone

from events.exceptions import (
    CharityBagAlreadyEntered,
    CharityBagInsufficientBalance,
    CharityBagNotActive,
)
from events.models import (
    CharityBagAction,
    CharityBagEvent,
    CharityBagStatus,
)
from events.services import create_charity_bag, enter_charity_bag, sync_charity_bag
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def teams():
    return (
        Team.objects.create(code="alpha", name="Alpha", balance=100),
        Team.objects.create(code="beta", name="Beta", balance=100),
    )


@pytest.fixture
def active_event():
    now = timezone.now()
    return create_charity_bag(now - timedelta(seconds=5), now + timedelta(minutes=5))


def _expire(event):
    CharityBagEvent.objects.filter(pk=event.pk).update(
        ends_at=timezone.now() - timedelta(seconds=1)
    )


def test_entry_immediately_deducts_stake(active_event, teams):
    entry = enter_charity_bag(active_event.pk, teams[0], CharityBagAction.CONTRIBUTE, 20)

    teams[0].refresh_from_db()
    assert teams[0].balance == 80
    assert entry.amount == entry.stake_deducted == 20
    assert entry.final_payout == 0


def test_entry_requires_current_balance_and_happens_once(active_event, teams):
    with pytest.raises(CharityBagInsufficientBalance):
        enter_charity_bag(active_event.pk, teams[0], CharityBagAction.REQUEST, 101)
    assert Team.objects.get(pk=teams[0].pk).balance == 100

    enter_charity_bag(active_event.pk, teams[0], CharityBagAction.REQUEST, 50)
    with pytest.raises(CharityBagAlreadyEntered):
        enter_charity_bag(active_event.pk, teams[0], CharityBagAction.CONTRIBUTE, 10)
    assert Team.objects.get(pk=teams[0].pk).balance == 50


def test_success_pays_requesters_twice_their_stake(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagAction.CONTRIBUTE, 30)
    enter_charity_bag(active_event.pk, teams[1], CharityBagAction.REQUEST, 20)
    _expire(active_event)

    event = sync_charity_bag(active_event.pk)

    teams[0].refresh_from_db()
    teams[1].refresh_from_db()
    assert event.status == CharityBagStatus.FINISHED
    assert event.charity_succeeded is True
    assert event.total_contributed == 30
    assert event.total_requested == 20
    assert teams[0].balance == 70
    assert teams[1].balance == 120
    assert event.participations.get(team=teams[1]).final_payout == 40


def test_failure_pays_contributors_twice_their_stake(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagAction.CONTRIBUTE, 20)
    enter_charity_bag(active_event.pk, teams[1], CharityBagAction.REQUEST, 30)
    _expire(active_event)

    event = sync_charity_bag(active_event.pk)

    teams[0].refresh_from_db()
    teams[1].refresh_from_db()
    assert event.charity_succeeded is False
    assert teams[0].balance == 120
    assert teams[1].balance == 70


def test_settlement_is_idempotent(active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagAction.CONTRIBUTE, 20)
    enter_charity_bag(active_event.pk, teams[1], CharityBagAction.REQUEST, 30)
    _expire(active_event)

    sync_charity_bag(active_event.pk)
    first_balances = list(Team.objects.order_by("pk").values_list("balance", flat=True))
    sync_charity_bag(active_event.pk)

    assert list(Team.objects.order_by("pk").values_list("balance", flat=True)) == first_balances


def test_closed_event_rejects_late_entry(active_event, teams):
    _expire(active_event)
    with pytest.raises(CharityBagNotActive):
        enter_charity_bag(active_event.pk, teams[0], CharityBagAction.CONTRIBUTE, 10)
    assert Team.objects.get(pk=teams[0].pk).balance == 100


def test_active_api_hides_totals_and_other_decisions(client, active_event, teams):
    enter_charity_bag(active_event.pk, teams[1], CharityBagAction.REQUEST, 20)
    user = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(user)

    response = client.get(f"/api/events/charity-bag/instances/{active_event.pk}/")

    assert response.status_code == 200
    body = response.json()
    assert body["total_contributed"] is None
    assert body["total_requested"] is None
    assert body["participations"] == []
    assert body["my_participation"] is None
    assert body["can_participate"] is True


def test_finished_api_exposes_audit_result(client, active_event, teams):
    enter_charity_bag(active_event.pk, teams[0], CharityBagAction.CONTRIBUTE, 20)
    enter_charity_bag(active_event.pk, teams[1], CharityBagAction.REQUEST, 30)
    _expire(active_event)
    sync_charity_bag(active_event.pk)
    user = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(user)

    response = client.get(f"/api/events/charity-bag/instances/{active_event.pk}/")

    assert response.status_code == 200
    body = response.json()
    assert body["charity_succeeded"] is False
    assert body["total_contributed"] == 20
    assert body["total_requested"] == 30
    assert len(body["participations"]) == 2


def test_participation_api_uses_authenticated_team(client, active_event, teams):
    user = User.objects.create_user("alpha", password="secret", team=teams[0])
    client.force_login(user)

    response = client.post(
        f"/api/events/charity-bag/instances/{active_event.pk}/participate/",
        {"action": "contribute", "amount": 25},
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
        {"duration_seconds": 300},
        content_type="application/json",
    )
    assert denied.status_code == 403

    mentor = User.objects.create_user("mentor", password="secret")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(mentor)
    created = client.post(
        "/api/events/charity-bag/instances/",
        {"duration_seconds": 300},
        content_type="application/json",
    )
    assert created.status_code == 201
    assert created.json()["status"] == "active"


def test_schedule_command_is_configurable_and_idempotent(settings):
    settings.CHARITY_BAG_SCHEDULE_TIMES = ["09:30", "12:30", "15:30"]
    settings.CHARITY_BAG_DURATION_SECONDS = 300

    call_command("schedule_charity_bags", date="2026-09-02")
    call_command("schedule_charity_bags", date="2026-09-02")

    assert CharityBagEvent.objects.count() == 3
    assert {
        int((event.ends_at - event.starts_at).total_seconds())
        for event in CharityBagEvent.objects.all()
    } == {300}
