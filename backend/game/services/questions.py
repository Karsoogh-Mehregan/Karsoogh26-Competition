from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from game.exceptions import (
    AlreadyGraded,
    AlreadySubmitted,
    GameNotRunning,
    InvalidAnswerPayload,
    MissingFloor,
    NoQuestionAvailable,
    NotTeamMember,
    OccupancyNotActive,
    SubmissionWindowClosed,
)
from game.models import (
    AnswerType,
    FloorReward,
    GameSettings,
    GradeMultiplier,
    Occupancy,
    Question,
    ReleaseReason,
    Submission,
    TeamQuestion,
    _round_half_up,
)


def assign_question(occupancy: Occupancy) -> Question:
    """Draw a random unused question for the occupancy's node level.

    Idempotent: if the occupancy already has a question, returns it.
    """
    occupancy = Occupancy.objects.select_related("node__level", "team").get(pk=occupancy.pk)

    if occupancy.released_at is not None:
        raise OccupancyNotActive("Occupancy is released.")

    if occupancy.question_id is not None:
        return occupancy.question

    with transaction.atomic():
        occupancy = Occupancy.objects.select_for_update().select_related(
            "node__level", "team"
        ).get(pk=occupancy.pk)
        if occupancy.question_id is not None:
            return occupancy.question
        if occupancy.released_at is not None:
            raise OccupancyNotActive("Occupancy is released.")

        served_ids = TeamQuestion.objects.filter(team=occupancy.team).values_list(
            "question_id", flat=True
        )
        question = (
            Question.objects.filter(
                level=occupancy.node.level,
                is_active=True,
            )
            .exclude(id__in=served_ids)
            .order_by("?")
            .first()
        )
        if question is None:
            raise NoQuestionAvailable("No unused questions remain for this level.")

        now = timezone.now()
        settings_row = GameSettings.load()
        expires_at = now + timedelta(minutes=settings_row.attempt_ttl_minutes)

        TeamQuestion.objects.create(
            team=occupancy.team,
            question=question,
            occupancy=occupancy,
        )
        occupancy.question = question
        occupancy.question_assigned_at = now
        occupancy.expires_at = expires_at
        occupancy.save(
            update_fields=["question", "question_assigned_at", "expires_at"],
        )

    return question


def submit_answer(
    occupancy: Occupancy,
    user,
    *,
    body: str = "",
    file=None,
) -> Submission:
    """Record a one-shot answer for an active occupancy."""
    if user.team_id is None:
        raise NotTeamMember("User is not on a team.")

    occupancy = Occupancy.objects.select_related(
        "question",
        "team",
    ).get(pk=occupancy.pk)

    if occupancy.team_id != user.team_id:
        raise NotTeamMember("Occupancy belongs to another team.")

    if occupancy.released_at is not None:
        raise OccupancyNotActive("Occupancy is released.")

    if not GameSettings.load().is_running:
        raise GameNotRunning("Game is not running.")

    if occupancy.question_id is None:
        raise OccupancyNotActive("No question has been assigned.")

    now = timezone.now()
    if occupancy.expires_at is not None and occupancy.expires_at <= now:
        raise SubmissionWindowClosed("Answer window has expired.")

    body = body or ""
    _validate_answer_payload(occupancy.question, body=body, file=file)

    try:
        with transaction.atomic():
            return Submission.objects.create(
                occupancy=occupancy,
                body=body,
                file=file or "",
                submitted_by=user,
            )
    except IntegrityError as exc:
        if Submission.objects.filter(occupancy=occupancy).exists():
            raise AlreadySubmitted("A submission already exists for this occupancy.") from exc
        raise


def _validate_answer_payload(question: Question, *, body: str, file) -> None:
    has_body = bool(body.strip())
    has_file = bool(file)

    if question.answer_type == AnswerType.FILE:
        if not has_file:
            raise InvalidAnswerPayload("This question requires a file upload.")
        return

    if not has_body:
        raise InvalidAnswerPayload("This question requires a text answer.")
    if has_file:
        raise InvalidAnswerPayload("This question does not accept file uploads.")

    if question.answer_type == AnswerType.NUMERIC:
        try:
            float(body.strip())
        except ValueError as exc:
            raise InvalidAnswerPayload("Answer must be numeric.") from exc


def grade_submission(submission: Submission, grade: int) -> Occupancy:
    """Apply a mentor grade to the occupancy tied to a submission."""
    if grade < 0 or grade > 100:
        raise ValueError("Grade must be between 0 and 100.")

    submission = Submission.objects.select_related(
        "occupancy__node__level",
        "occupancy__team",
    ).get(pk=submission.pk)
    occupancy = submission.occupancy

    if occupancy.grade is not None:
        raise AlreadyGraded("Occupancy has already been graded.")

    if occupancy.floor is None:
        raise MissingFloor("Occupancy has no floor assigned.")

    factor = GradeMultiplier.factor_for(grade)
    floor_reward = FloorReward.objects.get(
        level=occupancy.node.level,
        floor=occupancy.floor,
    )
    points = _round_half_up(floor_reward.points * factor)

    now = timezone.now()
    occupancy.grade = grade
    occupancy.grade_multiplier = factor
    occupancy.points_awarded = points

    if grade == 0:
        occupancy.released_at = now
        occupancy.release_reason = ReleaseReason.ZERO_GRADE

    occupancy.save(
        update_fields=[
            "grade",
            "grade_multiplier",
            "points_awarded",
            "released_at",
            "release_reason",
        ],
    )
    return occupancy
