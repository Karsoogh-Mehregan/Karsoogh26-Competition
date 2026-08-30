"""Claiming a start node's colour onto the team named in the URL."""

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


def _claim(client, code, node):
    return client.post(
        f"/api/teams/{code}/claim-start/",
        {"node": node},
        content_type="application/json",
    )


def test_claim_start_writes_color(auth_client, team):
    response = _claim(auth_client, team.code, "L1_0")
    assert response.status_code == 200
    assert response.json()["color"] == color_for_start("L1_0")
    team.refresh_from_db()
    assert team.color == color_for_start("L1_0")


def test_claim_start_is_idempotent_for_same_node(auth_client, team):
    first = _claim(auth_client, team.code, "L1_4")
    second = _claim(auth_client, team.code, "L1_4")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["color"] == second.json()["color"] == color_for_start("L1_4")


def test_claim_start_rejects_second_color(auth_client, team):
    _claim(auth_client, team.code, "L1_0")
    response = _claim(auth_client, team.code, "L1_8")
    assert response.status_code == 409
    team.refresh_from_db()
    assert team.color == color_for_start("L1_0")


def test_claim_start_rejects_taken_color(auth_client, team, other_team):
    other_team.color = color_for_start("L1_0")
    other_team.save()
    response = _claim(auth_client, team.code, "L1_0")
    assert response.status_code == 409
    team.refresh_from_db()
    assert team.color is None


def test_claim_start_rejects_non_start_node(auth_client, team):
    response = _claim(auth_client, team.code, "L1_1")
    assert response.status_code == 400


def test_claim_start_unknown_team_is_404(auth_client):
    response = _claim(auth_client, "nope", "L1_0")
    assert response.status_code == 404


def test_non_staff_mentor_can_claim_for_any_team(auth_client, user, other_team):
    assert user.is_staff is False
    assert user.team is None
    response = _claim(auth_client, other_team.code, "L1_0")
    assert response.status_code == 200
    other_team.refresh_from_db()
    assert other_team.color == color_for_start("L1_0")


def test_start_colors_are_unique():
    colors = {color_for_start(f"L1_{i * 4}") for i in range(48)}
    assert None not in colors
    assert len(colors) == 48
