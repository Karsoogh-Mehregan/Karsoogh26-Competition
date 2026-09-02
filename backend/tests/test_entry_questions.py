"""The pre-game entry sheet and the spawn claim it gates."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from game.models import EntryAttempt, EntryQuestion, GameSettings, GameStatus, LevelConfig, Node
from teams.models import Team

pytestmark = pytest.mark.django_db

User = get_user_model()

SHEET_URL = "/api/entry/sheet/"


def _answer_url(code):
    return f"/api/entry/questions/{code}/answer/"


@pytest.fixture
def team():
    return Team.objects.create(code="alpha", name="Alpha", balance=500)


@pytest.fixture
def other_team():
    return Team.objects.create(code="beta", name="Beta", balance=500)


@pytest.fixture
def auth_client(client, team):
    client.force_login(User.objects.create_user("user-alpha", password="secret", team=team))
    return client


@pytest.fixture(autouse=True)
def running_game():
    settings = GameSettings.load()
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])
    return settings


@pytest.fixture(autouse=True)
def questions():
    """A pool of five, so a three-question sheet has something to choose from."""
    return [
        EntryQuestion.objects.create(
            code=f"q{index}",
            title=f"سؤال {index}",
            body=f"متن سؤال {index}",
            answer=index * 10,
        )
        for index in range(1, 6)
    ]


@pytest.fixture(autouse=True)
def spawn_starts():
    spawn = LevelConfig.objects.get(level="spawn")
    for code in ("L1_0", "L1_4"):
        Node.objects.get_or_create(code=code, defaults={"name": code, "level": spawn})


def _solve(client, sheet, count):
    """Answer the first `count` questions of a sheet correctly."""
    codes = [row["code"] for row in sheet["questions"][:count]]
    for code in codes:
        answer = EntryQuestion.objects.get(code=code).answer
        response = client.post(
            _answer_url(code), {"answer": answer}, content_type="application/json"
        )
        assert response.status_code == 200, response.content
    return response.json()


def _refresh(client, code):
    return client.post(f"/api/entry/questions/{code}/refresh/")


def _answer_wrong(client, code):
    wrong = EntryQuestion.objects.get(code=code).answer + 1
    return client.post(_answer_url(code), {"answer": wrong}, content_type="application/json")


def _claim(client, code, node="L1_0"):
    return client.post(
        f"/api/teams/{code}/claim-start/", {"node": node}, content_type="application/json"
    )


# --- reading the sheet -------------------------------------------------------


def test_sheet_draws_the_configured_number_of_questions(auth_client, team):
    response = auth_client.get(SHEET_URL)
    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == GameSettings.load().entry_question_count == 3
    assert len(body["questions"]) == 3
    assert [row["position"] for row in body["questions"]] == [1, 2, 3]
    assert EntryAttempt.objects.filter(team=team).count() == 3


def test_sheet_is_stable_across_reads(auth_client):
    first = auth_client.get(SHEET_URL).json()
    second = auth_client.get(SHEET_URL).json()
    assert [row["code"] for row in first["questions"]] == [
        row["code"] for row in second["questions"]
    ]


def test_sheet_never_leaks_the_correct_answer(auth_client):
    """`answer` on a row is the team's own submission, never the key."""
    body = auth_client.get(SHEET_URL).json()

    for row in body["questions"]:
        assert set(row) == {
            "position",
            "code",
            "title",
            "body",
            "answer",
            "is_correct",
            "answered_at",
        }
        assert row["answer"] is None


def test_sheet_starts_unqualified(auth_client):
    body = auth_client.get(SHEET_URL).json()
    assert body["correct_count"] == 0
    assert body["required_correct"] == 2
    assert body["qualified"] is False
    assert body["can_claim_start"] is False
    assert body["draft_order"] is None


def test_sheet_needs_a_running_game(client, team):
    settings = GameSettings.load()
    settings.status = GameStatus.PAUSED
    settings.save(update_fields=["status"])
    client.force_login(User.objects.create_user("paused-user", password="secret", team=team))

    assert client.get(SHEET_URL).status_code == 403


def test_sheet_is_closed_to_users_without_a_team(client):
    mentor = User.objects.create_user("mentor", password="secret")
    mentor.groups.add(Group.objects.get(name="Mentors"))
    client.force_login(mentor)

    assert client.get(SHEET_URL).status_code == 403


def test_sheet_reports_a_pool_too_small_to_fill(auth_client):
    EntryQuestion.objects.update(is_active=False)
    EntryQuestion.objects.filter(code="q1").update(is_active=True)

    response = auth_client.get(SHEET_URL)
    assert response.status_code == 409
    assert not EntryAttempt.objects.exists()


def test_a_three_question_pool_gives_every_team_the_same_sheet(client, team, other_team):
    EntryQuestion.objects.exclude(code__in=("q1", "q2", "q3")).delete()

    client.force_login(User.objects.create_user("a", password="secret", team=team))
    first = client.get(SHEET_URL).json()
    client.force_login(User.objects.create_user("b", password="secret", team=other_team))
    second = client.get(SHEET_URL).json()

    assert {row["code"] for row in first["questions"]} == {"q1", "q2", "q3"}
    assert {row["code"] for row in second["questions"]} == {"q1", "q2", "q3"}


# --- answering ---------------------------------------------------------------


def test_correct_answer_is_marked_immediately(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    expected = EntryQuestion.objects.get(code=code).answer

    response = auth_client.post(
        _answer_url(code), {"answer": expected}, content_type="application/json"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_correct"] is True
    assert body["correct_count"] == 1
    assert body["answered_count"] == 1
    row = next(item for item in body["questions"] if item["code"] == code)
    assert row["is_correct"] is True
    assert row["answer"] == expected


def test_wrong_answer_is_marked_wrong_and_spends_the_question(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    wrong = EntryQuestion.objects.get(code=code).answer + 1

    body = auth_client.post(
        _answer_url(code), {"answer": wrong}, content_type="application/json"
    ).json()
    assert body["is_correct"] is False
    assert body["correct_count"] == 0
    assert body["answered_count"] == 1


def test_each_question_is_one_shot(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    correct = EntryQuestion.objects.get(code=code).answer

    auth_client.post(_answer_url(code), {"answer": correct + 1}, content_type="application/json")
    retry = auth_client.post(
        _answer_url(code), {"answer": correct}, content_type="application/json"
    )
    assert retry.status_code == 409
    assert EntryAttempt.objects.get(question__code=code).is_correct is False


def test_answering_a_question_off_the_sheet_is_404(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    served = {row["code"] for row in sheet["questions"]}
    missing = next(code for code in ("q1", "q2", "q3", "q4", "q5") if code not in served)

    response = auth_client.post(
        _answer_url(missing), {"answer": 1}, content_type="application/json"
    )
    assert response.status_code == 404


def test_answer_must_be_an_integer(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]

    response = auth_client.post(
        _answer_url(code), {"answer": "چهل"}, content_type="application/json"
    )
    assert response.status_code == 400


def test_clearing_the_sheet_qualifies_and_stamps_draft_order(auth_client, team):
    sheet = auth_client.get(SHEET_URL).json()
    body = _solve(auth_client, sheet, 2)

    assert body["qualified"] is True
    assert body["can_claim_start"] is True
    assert body["draft_order"] == 1
    team.refresh_from_db()
    assert team.draft_order == 1


def test_draft_order_follows_finishing_order(client, team, other_team):
    client.force_login(User.objects.create_user("a", password="secret", team=team))
    _solve(client, client.get(SHEET_URL).json(), 2)

    client.force_login(User.objects.create_user("b", password="secret", team=other_team))
    _solve(client, client.get(SHEET_URL).json(), 2)

    team.refresh_from_db()
    other_team.refresh_from_db()
    assert (team.draft_order, other_team.draft_order) == (1, 2)


# --- the gate on claim-start -------------------------------------------------


def test_claim_start_is_blocked_before_the_sheet_is_cleared(auth_client, team):
    auth_client.get(SHEET_URL)
    response = _claim(auth_client, team.code)

    assert response.status_code == 409
    team.refresh_from_db()
    assert team.color is None


def test_one_correct_answer_is_not_enough(auth_client, team):
    _solve(auth_client, auth_client.get(SHEET_URL).json(), 1)
    assert _claim(auth_client, team.code).status_code == 409


def test_claim_start_opens_once_the_sheet_is_cleared(auth_client, team):
    _solve(auth_client, auth_client.get(SHEET_URL).json(), 2)

    response = _claim(auth_client, team.code)
    assert response.status_code == 200
    team.refresh_from_db()
    assert team.color is not None


def test_grace_window_opens_the_map_for_everyone(auth_client, team, running_game):
    running_game.started_at = timezone.now() - timedelta(
        minutes=running_game.entry_grace_minutes + 1
    )
    running_game.save(update_fields=["started_at"])

    body = auth_client.get(SHEET_URL).json()
    assert body["qualified"] is False
    assert body["grace_over"] is True
    assert body["can_claim_start"] is True
    assert _claim(auth_client, team.code).status_code == 200


def test_grace_is_still_closed_inside_the_window(auth_client, team, running_game):
    running_game.started_at = timezone.now() - timedelta(minutes=1)
    running_game.save(update_fields=["started_at"])

    assert auth_client.get(SHEET_URL).json()["grace_over"] is False
    assert _claim(auth_client, team.code).status_code == 409


def test_running_stamps_started_at_once():
    settings = GameSettings.load()
    assert settings.started_at is not None
    first = settings.started_at

    settings.status = GameStatus.PAUSED
    settings.save(update_fields=["status"])
    settings.status = GameStatus.RUNNING
    settings.save(update_fields=["status"])

    settings.refresh_from_db()
    assert settings.started_at == first


# --- swapping a question the team got wrong ----------------------------------


def test_refresh_replaces_a_wrong_question_at_the_same_position(auth_client, team):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    _answer_wrong(auth_client, code)

    response = _refresh(auth_client, code)
    assert response.status_code == 200
    body = response.json()

    replacement = body["questions"][0]
    assert replacement["position"] == 1
    assert replacement["code"] != code
    assert replacement["answered_at"] is None
    assert replacement["is_correct"] is None
    assert body["total_count"] == 3
    assert body["answered_count"] == 0
    assert body["refreshes_used"] == 1
    assert body["refreshes_left"] == 2


def test_refresh_retires_the_old_row_instead_of_deleting_it(auth_client, team):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    _answer_wrong(auth_client, code)
    _refresh(auth_client, code)

    retired = EntryAttempt.objects.get(team=team, question__code=code)
    assert retired.replaced_at is not None
    assert retired.is_correct is False
    assert EntryAttempt.objects.filter(team=team).count() == 4
    assert EntryAttempt.objects.current().filter(team=team).count() == 3


def test_a_discarded_question_never_comes_back(auth_client, team):
    """Five questions, three on the sheet: every swap must draw an unseen one."""
    seen = set()
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    seen.add(code)

    for _ in range(2):
        _answer_wrong(auth_client, code)
        body = _refresh(auth_client, code).json()
        code = body["questions"][0]["code"]
        assert code not in seen
        seen.add(code)


def test_refresh_lets_a_team_still_qualify(auth_client, team):
    sheet = auth_client.get(SHEET_URL).json()
    first, second = (row["code"] for row in sheet["questions"][:2])

    _answer_wrong(auth_client, first)
    assert _claim(auth_client, team.code).status_code == 409

    replacement = _refresh(auth_client, first).json()["questions"][0]["code"]
    _solve(auth_client, {"questions": [{"code": replacement}, {"code": second}]}, 2)

    team.refresh_from_db()
    assert team.draft_order == 1
    assert _claim(auth_client, team.code).status_code == 200


def test_refresh_needs_an_answer_first(auth_client):
    sheet = auth_client.get(SHEET_URL).json()

    response = _refresh(auth_client, sheet["questions"][0]["code"])
    assert response.status_code == 409


def test_a_correct_answer_is_not_swappable(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    _solve(auth_client, sheet, 1)

    assert _refresh(auth_client, code).status_code == 409


def test_refresh_of_a_question_off_the_sheet_is_404(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    served = {row["code"] for row in sheet["questions"]}
    missing = next(code for code in ("q1", "q2", "q3", "q4", "q5") if code not in served)

    assert _refresh(auth_client, missing).status_code == 404


def test_a_retired_question_is_off_the_sheet(auth_client):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    _answer_wrong(auth_client, code)
    _refresh(auth_client, code)

    assert _refresh(auth_client, code).status_code == 404
    assert _answer_wrong(auth_client, code).status_code == 404


def test_refreshes_are_capped(auth_client, running_game):
    running_game.entry_max_refreshes = 1
    running_game.save(update_fields=["entry_max_refreshes"])

    sheet = auth_client.get(SHEET_URL).json()
    first, second = (row["code"] for row in sheet["questions"][:2])

    _answer_wrong(auth_client, first)
    assert _refresh(auth_client, first).json()["refreshes_left"] == 0

    _answer_wrong(auth_client, second)
    assert _refresh(auth_client, second).status_code == 409


def test_refreshing_is_off_when_the_cap_is_zero(auth_client, running_game):
    running_game.entry_max_refreshes = 0
    running_game.save(update_fields=["entry_max_refreshes"])

    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    _answer_wrong(auth_client, code)

    assert sheet["refreshes_left"] == 0
    assert _refresh(auth_client, code).status_code == 409


def test_refresh_reports_an_exhausted_pool(auth_client, running_game):
    EntryQuestion.objects.exclude(code__in=("q1", "q2", "q3")).delete()

    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    _answer_wrong(auth_client, code)

    response = _refresh(auth_client, code)
    assert response.status_code == 409
    # Nothing was spent on a swap that could not happen.
    assert auth_client.get(SHEET_URL).json()["refreshes_used"] == 0


def test_refresh_needs_a_running_game(auth_client, running_game):
    sheet = auth_client.get(SHEET_URL).json()
    code = sheet["questions"][0]["code"]
    _answer_wrong(auth_client, code)

    running_game.status = GameStatus.PAUSED
    running_game.save(update_fields=["status"])
    assert _refresh(auth_client, code).status_code == 403
