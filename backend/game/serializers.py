from django.utils import timezone
from rest_framework import serializers

from game.models import Occupancy, Question, Submission


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

    def get_expires_at(self, obj: Question):
        return self.context.get("expires_at")

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


class SubmissionListSerializer(serializers.ModelSerializer):
    team_code = serializers.CharField(source="occupancy.team.code", read_only=True)
    team_name = serializers.CharField(source="occupancy.team.name", read_only=True)
    node_code = serializers.CharField(source="occupancy.node.code", read_only=True)
    level = serializers.CharField(source="occupancy.node.level_id", read_only=True)
    question_code = serializers.CharField(source="occupancy.question.code", read_only=True)
    question_title = serializers.CharField(source="occupancy.question.title", read_only=True)
    graded = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = (
            "id",
            "submitted_at",
            "team_code",
            "team_name",
            "node_code",
            "level",
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
    points_awarded = serializers.IntegerField(
        source="occupancy.points_awarded", read_only=True
    )
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
            "points_awarded",
            "question",
        )

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

    def get_file_url(self, obj: Submission) -> str | None:
        if not obj.file:
            return None
        request = self.context.get("request")
        if request is None:
            return None
        return request.build_absolute_uri(f"/api/media/submissions/{obj.pk}/")


class GradeSubmissionSerializer(serializers.Serializer):
    grade = serializers.IntegerField(min_value=0, max_value=100)


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
