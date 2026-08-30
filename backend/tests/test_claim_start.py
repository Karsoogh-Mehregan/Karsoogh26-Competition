"""Claiming a start node's colour onto the acting team."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from teams.models import Team
from teams.start_colors import color_for_start

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def user():
    mentor = User.objects.create_user("mentor", password="secret")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    return mentor


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha", balance=42)


@pytest.fixture
def other_team():
    return Team.objects.create(code="beta", name="Beta", balance=7)


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


def _act_as(client, code):
    response = client.post(
        "/api/auth/act-as/",
        {"team": code},
        content_type="application/json",
    )
    assert response.status_code == 200
    return response


def test_claim_start_writes_color(auth_client, team):
    _act_as(auth_client, team.code)
    response = auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_0"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["color"] == color_for_start("L1_0")
    team.refresh_from_db()
    assert team.color == color_for_start("L1_0")


def test_claim_start_is_idempotent_for_same_node(auth_client, team):
    _act_as(auth_client, team.code)
    first = auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_4"},
        content_type="application/json",
    )
    second = auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_4"},
        content_type="application/json",
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["color"] == second.json()["color"] == color_for_start("L1_4")


def test_claim_start_rejects_second_color(auth_client, team):
    _act_as(auth_client, team.code)
    auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_0"},
        content_type="application/json",
    )
    response = auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_8"},
        content_type="application/json",
    )
    assert response.status_code == 409
    team.refresh_from_db()
    assert team.color == color_for_start("L1_0")


def test_claim_start_rejects_taken_color(auth_client, team, other_team):
    other_team.color = color_for_start("L1_0")
    other_team.save()
    _act_as(auth_client, team.code)
    response = auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_0"},
        content_type="application/json",
    )
    assert response.status_code == 409
    team.refresh_from_db()
    assert team.color is None


def test_claim_start_rejects_non_start_node(auth_client, team):
    _act_as(auth_client, team.code)
    response = auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_1"},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_claim_start_requires_acting_team(auth_client):
    response = auth_client.post(
        "/api/teams/claim-start/",
        {"node": "L1_0"},
        content_type="application/json",
    )
    assert response.status_code == 409


def test_start_colors_are_unique():
    colors = {color_for_start(f"L1_{i * 4}") for i in range(48)}
    assert None not in colors
    assert len(colors) == 48
