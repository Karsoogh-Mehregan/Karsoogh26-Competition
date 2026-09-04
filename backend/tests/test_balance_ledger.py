import importlib

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command

from core.boards import Board
from game.models import GameSettings
from teams.ledger import InsufficientFunds, apply_balance_change
from teams.models import BalanceEvent, BalanceReason, Team

_seed = importlib.import_module("teams.migrations.0004_seed_balance_events")

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_apply_balance_change_writes_an_event():
    team = Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=100)

    apply_balance_change(team, -20, reason=BalanceReason.ENTRY, detail="L2_1")

    team.refresh_from_db()
    event = BalanceEvent.objects.get()
    assert team.balance == 80
    assert event.delta == -20
    assert event.balance_after == 80
    assert event.reason == BalanceReason.ENTRY
    assert event.detail == "L2_1"


def test_a_debit_that_exceeds_the_wallet_is_refused():
    team = Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=10)

    with pytest.raises(InsufficientFunds):
        apply_balance_change(team, -20, reason=BalanceReason.ENTRY)

    team.refresh_from_db()
    assert team.balance == 10
    assert BalanceEvent.objects.count() == 0


def test_history_failure_rolls_back_wallet_even_without_outer_transaction(monkeypatch):
    team = Team.objects.create(board=Board.GIRLS, code="rollback", name="Rollback", balance=100)

    def fail(**kwargs):
        raise RuntimeError("history unavailable")

    monkeypatch.setattr(BalanceEvent.objects, "create", fail)
    with pytest.raises(RuntimeError, match="history unavailable"):
        apply_balance_change(team, -20, reason=BalanceReason.EVENT)
    team.refresh_from_db()
    assert team.balance == 100
    assert not BalanceEvent.objects.exists()


def test_seed_copies_existing_balances_without_touching_the_wallet():
    kept = Team.objects.create(board=Board.GIRLS, code="kept", name="Kept", balance=400)
    empty = Team.objects.create(board=Board.GIRLS, code="empty", name="Empty", balance=0)
    already = Team.objects.create(board=Board.GIRLS, code="logged", name="Logged", balance=50)
    BalanceEvent.objects.create(
        team=already,
        delta=50,
        balance_after=50,
        reason=BalanceReason.GRADE,
        detail="L3_1",
    )

    _seed.seed_existing_balances(apps, None)

    kept.refresh_from_db()
    empty.refresh_from_db()
    already.refresh_from_db()
    assert kept.balance == 400
    assert empty.balance == 0
    assert already.balance == 50
    assert list(
        BalanceEvent.objects.filter(team=kept).values_list("reason", "delta", "balance_after")
    ) == [(BalanceReason.INITIAL, 400, 400)]
    assert not BalanceEvent.objects.filter(team=empty).exists()
    assert BalanceEvent.objects.filter(team=already).count() == 1


def test_team_can_read_its_own_balance_events(client):
    team = Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=80)
    other = Team.objects.create(board=Board.GIRLS, code="beta", name="Beta", balance=10)
    apply_balance_change(team, -20, reason=BalanceReason.ENTRY, detail="L2_1")
    apply_balance_change(other, 5, reason=BalanceReason.GRADE, detail="L1_0")
    user = User.objects.create_user("user-alpha", password="secret", team=team)
    client.force_login(user)

    own = client.get("/api/teams/alpha/balance-events/")
    other_resp = client.get("/api/teams/beta/balance-events/")

    assert own.status_code == 200
    payload = own.json()
    assert len(payload) == 1
    assert payload[0]["delta"] == -20
    assert payload[0]["reason"] == "entry"
    assert payload[0]["reason_label"] == "رزرو خانه"
    assert payload[0]["detail"] == "L2_1"
    assert other_resp.status_code == 403


def test_create_team_users_fund_writes_an_initial_event():
    team = Team.objects.create(board=Board.GIRLS, code="alpha", name="Alpha", balance=0)
    initial = GameSettings.load().initial_balance

    call_command("create_team_users", "--fund")

    team.refresh_from_db()
    event = BalanceEvent.objects.get(team=team)
    assert team.balance == initial
    assert event.reason == BalanceReason.INITIAL
    assert event.delta == initial
    assert event.balance_after == initial
