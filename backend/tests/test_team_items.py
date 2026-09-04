"""Current-team inventory list API."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from teams.models import ItemType, Team, TeamItem

pytestmark = pytest.mark.django_db

User = get_user_model()

ITEMS_URL = "/api/teams/me/items/"


@pytest.fixture
def alpha():
    return Team.objects.create(code="alpha", name="Alpha")


@pytest.fixture
def beta():
    return Team.objects.create(code="beta", name="Beta")


def test_team_member_sees_only_own_items(client, alpha, beta):
    TeamItem.objects.create(team=alpha, item_type=ItemType.GEL, quantity=5)
    TeamItem.objects.create(team=alpha, item_type=ItemType.FAKE_DOCUMENT, quantity=1)
    TeamItem.objects.create(team=beta, item_type=ItemType.GILARI_100, quantity=2)
    user = User.objects.create_user("user-alpha", password="secret", team=alpha)
    client.force_login(user)

    response = client.get(ITEMS_URL)

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "item_type": ItemType.FAKE_DOCUMENT,
            "quantity": 1,
            "display_name": ItemType.FAKE_DOCUMENT.label,
        },
        {
            "item_type": ItemType.GEL,
            "quantity": 5,
            "display_name": ItemType.GEL.label,
        },
    ]


def test_empty_inventory_is_an_empty_list(client, alpha):
    user = User.objects.create_user("user-alpha", password="secret", team=alpha)
    client.force_login(user)

    response = client.get(ITEMS_URL)

    assert response.status_code == 200
    assert response.json() == []


def test_mentor_without_a_team_cannot_read_inventory(client):
    user = User.objects.create_user("mentor", password="secret")
    user.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(user)

    assert client.get(ITEMS_URL).status_code == 403


def test_anonymous_cannot_read_inventory(client):
    assert client.get(ITEMS_URL).status_code == 403
