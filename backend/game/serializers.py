from django.utils import timezone
from rest_framework import serializers

from core.openapi import extend_schema_field
from game.models import EntryAttempt, Occupancy, Question, Submission
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
    questions = EntryAttemptSerializer(many=True, read_only=True, source="attempts")


class EntryAnswerSerializer(serializers.Serializer):
    answer = serializers.IntegerField()


class EntryAnswerResultSerializer(EntrySheetSerializer):
    is_correct = serializers.BooleanField(read_only=True)
