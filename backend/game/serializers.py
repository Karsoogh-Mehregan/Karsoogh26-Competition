from django.utils import timezone
from rest_framework import serializers

from core.openapi import extend_schema_field
from game.design import ARCHETYPES
from game.models import (
    EntryAttempt,
    GameSettings,
    Level,
    MapDesign,
    Neighborhood,
    Node,
    Occupancy,
    Question,
    Submission,
)
from game.services import MENTOR_RELEASE_REASONS


class QuestionForTeamSerializer(serializers.ModelSerializer):
    attachment_url = serializers.SerializerMethodField()
    expires_at = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = (
            "code",
            "title",
            "body",
            "answer_type",
            "attachment_url",
            "expires_at",
            "remaining_seconds",
        )

    @extend_schema_field(str | None)
    def get_expires_at(self, obj: Question):
        return self.context.get("expires_at")

    @extend_schema_field(str | None)
    def get_attachment_url(self, obj: Question) -> str | None:
        if not obj.attachment:
            return None
        request = self.context.get("request")
        if request is None:
            return None
        return request.build_absolute_uri(f"/api/media/questions/{obj.pk}/")

    def get_remaining_seconds(self, obj: Question) -> int:
        expires_at = self.context.get("expires_at")
        if expires_at is None:
            return 0
        delta = expires_at - timezone.now()
        return max(0, int(delta.total_seconds()))


class SubmitAnswerSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField(required=False, allow_null=True)

    def validate(self, attrs):
        body = attrs.get("body", "")
        file = attrs.get("file")
        if not body.strip() and not file:
            raise serializers.ValidationError("Provide body or file.")
        return attrs


class QuestionForMentorSerializer(serializers.Serializer):
    code = serializers.CharField()
    title = serializers.CharField()
    body = serializers.CharField()
    answer_type = serializers.CharField()
    answer_key = serializers.CharField(allow_blank=True, allow_null=True)
    attachment_url = serializers.CharField(allow_null=True)


class SubmissionListSerializer(serializers.ModelSerializer):
    team_id = serializers.IntegerField(source="occupancy.team_id", read_only=True)
    team_code = serializers.CharField(source="occupancy.team.code", read_only=True)
    team_name = serializers.CharField(source="occupancy.team.name", read_only=True)
    node_code = serializers.CharField(source="occupancy.node.code", read_only=True)
    level = serializers.CharField(source="occupancy.node.level_id", read_only=True)
    question_id = serializers.IntegerField(source="occupancy.question_id", read_only=True)
    question_code = serializers.CharField(source="occupancy.question.code", read_only=True)
    question_title = serializers.CharField(source="occupancy.question.title", read_only=True)
    graded = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = (
            "id",
            "submitted_at",
            "team_id",
            "team_code",
            "team_name",
            "node_code",
            "level",
            "question_id",
            "question_code",
            "question_title",
            "graded",
        )

    def get_graded(self, obj: Submission) -> bool:
        return obj.occupancy.grade is not None


class SubmissionDetailSerializer(serializers.ModelSerializer):
    team_code = serializers.CharField(source="occupancy.team.code", read_only=True)
    team_name = serializers.CharField(source="occupancy.team.name", read_only=True)
    node_code = serializers.CharField(source="occupancy.node.code", read_only=True)
    level = serializers.CharField(source="occupancy.node.level_id", read_only=True)
    floor = serializers.IntegerField(source="occupancy.floor", read_only=True, allow_null=True)
    grade = serializers.IntegerField(source="occupancy.grade", read_only=True, allow_null=True)
    points = serializers.IntegerField(source="occupancy.points", read_only=True)
    question = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = (
            "id",
            "submitted_at",
            "submitted_by",
            "body",
            "file_url",
            "team_code",
            "team_name",
            "node_code",
            "level",
            "floor",
            "grade",
            "points",
            "question",
        )

    @extend_schema_field(QuestionForMentorSerializer)
    def get_question(self, obj: Submission) -> dict:
        question = obj.occupancy.question
        request = self.context.get("request")
        attachment_url = None
        if question.attachment and request is not None:
            attachment_url = request.build_absolute_uri(f"/api/media/questions/{question.pk}/")
        return {
            "code": question.code,
            "title": question.title,
            "body": question.body,
            "answer_type": question.answer_type,
            "answer_key": question.answer_key,
            "attachment_url": attachment_url,
        }

    @extend_schema_field(str | None)
    def get_file_url(self, obj: Submission) -> str | None:
        if not obj.file:
            return None
        request = self.context.get("request")
        if request is None:
            return None
        return request.build_absolute_uri(f"/api/media/submissions/{obj.pk}/")


class GradeSubmissionSerializer(serializers.Serializer):
    grade = serializers.IntegerField(min_value=0, max_value=100)


class SubmitCreatedSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    submitted_at = serializers.DateTimeField()


class GradeResultSerializer(serializers.Serializer):
    occupancy_id = serializers.IntegerField()
    grade = serializers.IntegerField(allow_null=True)
    grade_multiplier = serializers.DecimalField(max_digits=4, decimal_places=3, allow_null=True)
    points = serializers.IntegerField()
    released_at = serializers.DateTimeField(allow_null=True)
    release_reason = serializers.CharField(allow_blank=True)


class OccupancyQuestionResponseSerializer(serializers.Serializer):
    occupancy_id = serializers.IntegerField()
    expires_at = serializers.DateTimeField()
    remaining_seconds = serializers.IntegerField()
    question = QuestionForTeamSerializer()


def remaining_seconds_for(expires_at) -> int:
    if expires_at is None:
        return 0
    delta = expires_at - timezone.now()
    return max(0, int(delta.total_seconds()))


def attempt_status_for(occupancy: Occupancy) -> str:
    if occupancy.grade is not None:
        return "graded"
    if occupancy.question_id is None:
        return "no_question"
    if hasattr(occupancy, "submission"):
        return "answered"
    if occupancy.is_expired:
        return "expired"
    return "open"


class AttemptSubmissionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    submitted_at = serializers.DateTimeField()


class ActiveAttemptSerializer(serializers.ModelSerializer):
    node_code = serializers.CharField(source="node.code", read_only=True)
    node_name = serializers.CharField(source="node.name", read_only=True)
    level = serializers.CharField(source="node.level_id", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    remaining_seconds = serializers.SerializerMethodField()
    question = serializers.SerializerMethodField()
    submission = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Occupancy
        fields = (
            "id",
            "node_code",
            "node_name",
            "level",
            "slot",
            "floor",
            "is_spawn",
            "grade",
            "expires_at",
            "remaining_seconds",
            "is_expired",
            "question",
            "submission",
            "status",
        )
        read_only_fields = fields

    def get_remaining_seconds(self, obj: Occupancy) -> int:
        return remaining_seconds_for(obj.expires_at)

    @extend_schema_field(QuestionForTeamSerializer(allow_null=True))
    def get_question(self, obj: Occupancy):
        if obj.question_id is None:
            return None
        serializer = QuestionForTeamSerializer(
            obj.question,
            context={**self.context, "expires_at": obj.expires_at},
        )
        return serializer.data

    @extend_schema_field(AttemptSubmissionSerializer(allow_null=True))
    def get_submission(self, obj: Occupancy):
        if not hasattr(obj, "submission"):
            return None
        return AttemptSubmissionSerializer(obj.submission).data

    def get_status(self, obj: Occupancy) -> str:
        return attempt_status_for(obj)


def occupancy_for_user(pk: int, user) -> Occupancy:
    try:
        return Occupancy.objects.select_related("team", "question", "node__level").get(pk=pk)
    except Occupancy.DoesNotExist as exc:
        from rest_framework.exceptions import NotFound

        raise NotFound("Occupancy not found.") from exc


class TeamSummarySerializer(serializers.Serializer):
    code = serializers.SlugField(read_only=True)
    name = serializers.CharField(read_only=True)
    balance = serializers.IntegerField(read_only=True)


class NodeSummarySerializer(serializers.Serializer):
    code = serializers.SlugField(read_only=True)
    name = serializers.CharField(read_only=True)
    level = serializers.CharField(source="level_id", read_only=True)


class HoldingSerializer(serializers.ModelSerializer):
    team = TeamSummarySerializer(read_only=True)
    node = NodeSummarySerializer(read_only=True)
    points = serializers.IntegerField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Occupancy
        fields = (
            "id",
            "team",
            "node",
            "slot",
            "floor",
            "grade",
            "grade_multiplier",
            "points",
            "question_id",
            "question_assigned_at",
            "expires_at",
            "is_expired",
            "entered_at",
            "released_at",
            "release_reason",
        )
        read_only_fields = fields


class AssignQuestionSerializer(serializers.Serializer):
    """No input — the team and node come from the URL."""


class GradeSerializer(serializers.Serializer):
    grade = serializers.IntegerField(min_value=0, max_value=100)


class ReleaseSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(
        choices=[(reason.value, reason.label) for reason in MENTOR_RELEASE_REASONS]
    )


class GameStateSerializer(serializers.Serializer):
    """What every logged-in client needs to draw the clock and the stage bar.

    `server_time` is the point of the whole thing: contest clients disagree
    about the wall clock, so the SPA derives one offset from this and shows the
    same countdown to everyone.
    """

    status = serializers.CharField(read_only=True)
    status_display = serializers.CharField(read_only=True)
    is_running = serializers.BooleanField(read_only=True)
    server_time = serializers.DateTimeField(read_only=True)
    started_at = serializers.DateTimeField(read_only=True, allow_null=True)
    # The raw ledger, so the client can tick locally and freeze on its own when
    # the game is not running instead of waiting for the next poll.
    accumulated_seconds = serializers.IntegerField(read_only=True)
    running_since = serializers.DateTimeField(read_only=True, allow_null=True)
    duration_seconds = serializers.IntegerField(read_only=True)
    elapsed_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    remaining_seconds = serializers.IntegerField(read_only=True, allow_null=True)
    leaderboard_public = serializers.BooleanField(read_only=True)


class GameSettingsSerializer(serializers.ModelSerializer):
    """The mentor-editable knobs. `started_at` is stamped by the model, not set."""

    class Meta:
        model = GameSettings
        fields = (
            "status",
            "leaderboard_public",
            "duration_minutes",
            "initial_balance",
        )


class GameRestartSerializer(serializers.Serializer):
    """Confirmation is required in the body, not just in the UI.

    A restart deletes every move of the contest, so it must not be reachable by
    a stray POST to a URL somebody had open.
    """

    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("برای بازنشانی بازی باید تأیید کنید.")
        return value


class GameRestartResultSerializer(serializers.Serializer):
    occupancies = serializers.IntegerField(read_only=True)
    submissions = serializers.IntegerField(read_only=True)
    entry_attempts = serializers.IntegerField(read_only=True)
    teams = serializers.IntegerField(read_only=True)


class EntryAttemptSerializer(serializers.ModelSerializer):
    """One row of a team's entry sheet.

    `answer` is the team's own submission, echoed back; the correct answer
    lives on EntryQuestion and is never listed here.
    """

    code = serializers.CharField(source="question.code", read_only=True)
    title = serializers.CharField(source="question.title", read_only=True)
    body = serializers.CharField(source="question.body", read_only=True)

    class Meta:
        model = EntryAttempt
        fields = ("position", "code", "title", "body", "answer", "is_correct", "answered_at")
        read_only_fields = fields


class EntrySheetSerializer(serializers.Serializer):
    required_correct = serializers.IntegerField(read_only=True)
    correct_count = serializers.IntegerField(read_only=True)
    answered_count = serializers.IntegerField(read_only=True)
    total_count = serializers.IntegerField(read_only=True)
    qualified = serializers.BooleanField(read_only=True)
    grace_over = serializers.BooleanField(read_only=True)
    grace_ends_at = serializers.DateTimeField(read_only=True, allow_null=True)
    can_claim_start = serializers.BooleanField(read_only=True)
    draft_order = serializers.IntegerField(read_only=True, allow_null=True)
    retries_used = serializers.IntegerField(read_only=True)
    retries_left = serializers.IntegerField(read_only=True)
    questions = EntryAttemptSerializer(many=True, read_only=True, source="attempts")


class EntryAnswerSerializer(serializers.Serializer):
    answer = serializers.IntegerField()


class EntryAnswerResultSerializer(EntrySheetSerializer):
    is_correct = serializers.BooleanField(read_only=True)


# ---- map design ---------------------------------------------------------------


class NeighborhoodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Neighborhood
        fields = ("index", "name", "theme", "color")
        read_only_fields = ("index",)


class NeighborhoodPatchSerializer(NeighborhoodSerializer):
    """One row of a bulk PATCH: `index` picks the row, the rest are optional."""

    index = serializers.IntegerField(min_value=0)

    class Meta(NeighborhoodSerializer.Meta):
        read_only_fields = ()
        extra_kwargs = {
            "name": {"required": False},
            "theme": {"required": False},
            "color": {"required": False},
        }


class NodeDesignSerializer(serializers.ModelSerializer):
    """What the renderer needs per node, and what a Designer may change on one.

    `level` is the backend's word, not the map JSON's: a Designer may move a node
    between tiers, and the SVG map must follow the server, not its baked-in type.
    """

    level = serializers.ChoiceField(choices=Level.choices, source="level_id")
    capacity = serializers.IntegerField(source="level.capacity", read_only=True)
    archetype = serializers.ChoiceField(choices=ARCHETYPES, allow_blank=True, required=False)

    class Meta:
        model = Node
        fields = ("code", "level", "capacity", "archetype")
        read_only_fields = ("code",)


class MapDesignSerializer(serializers.ModelSerializer):
    neighborhoods = NeighborhoodSerializer(many=True, read_only=True)
    nodes = NodeDesignSerializer(many=True, read_only=True)

    class Meta:
        model = MapDesign
        fields = ("road_style", "tint_strength", "halo_strength", "neighborhoods", "nodes")


class MapDesignPatchSerializer(serializers.ModelSerializer):
    """The writable half. Neighbourhoods are patched in bulk, addressed by index."""

    neighborhoods = NeighborhoodPatchSerializer(many=True, required=False)
    tint_strength = serializers.IntegerField(min_value=0, max_value=100, required=False)
    halo_strength = serializers.IntegerField(min_value=0, max_value=100, required=False)

    class Meta:
        model = MapDesign
        fields = ("road_style", "tint_strength", "halo_strength", "neighborhoods")
