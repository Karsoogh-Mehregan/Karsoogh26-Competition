from django import forms
from django.contrib import admin

from accounts.permissions import MENTOR_PERM
from notifications.services import users_with_perm

from .models import (
    Edge,
    EntryAttempt,
    EntryQuestion,
    FloorReward,
    GameSettings,
    GradeMultiplier,
    LevelConfig,
    MapDesign,
    Neighborhood,
    Node,
    Occupancy,
    Question,
    Submission,
    TeamQuestion,
)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        """Offer only actual mentors (explicit grant, not has_perm)."""
        super().__init__(*args, **kwargs)
        mentors = self.fields.get("mentors")
        if mentors is not None:
            mentors.queryset = users_with_perm(MENTOR_PERM).filter(is_active=True)
            mentors.help_text = (
                "Only users holding act_as_mentor. Empty = submissions go to every mentor queue."
            )


class ActiveFilter(admin.SimpleListFilter):
    title = "active"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return [("1", "Active"), ("0", "Released")]

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(released_at__isnull=True)
        if self.value() == "0":
            return queryset.filter(released_at__isnull=False)
        return queryset


class FloorRewardInline(admin.TabularInline):
    model = FloorReward
    extra = 0


@admin.register(LevelConfig)
class LevelConfigAdmin(admin.ModelAdmin):
    list_display = (
        "level",
        "capacity",
        "entry_cost",
        "attempt_ttl_minutes",
    )
    inlines = [FloorRewardInline]


@admin.register(FloorReward)
class FloorRewardAdmin(admin.ModelAdmin):
    list_display = (
        "level",
        "floor",
        "points",
        "networth",
        "duel_cost",
        "buyout_cost",
    )
    list_editable = ("points", "networth", "duel_cost", "buyout_cost")
    list_filter = ("level",)
    list_select_related = ("level",)


@admin.register(GradeMultiplier)
class GradeMultiplierAdmin(admin.ModelAdmin):
    list_display = ("grade", "factor")
    ordering = ("grade",)


class OccupancyInline(admin.TabularInline):
    model = Occupancy
    extra = 0
    can_delete = False
    fields = ("team", "slot", "floor", "grade", "points", "is_spawn")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(released_at__isnull=True)


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "board", "level", "archetype", "gelled")
    list_filter = ("board", "level", "archetype", "gelled")
    search_fields = ("code", "name")
    list_select_related = ("level",)
    inlines = [OccupancyInline]


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ("a", "b", "directed")
    list_filter = ("directed",)
    autocomplete_fields = ("a", "b")
    list_select_related = ("a", "b")


@admin.register(Occupancy)
class OccupancyAdmin(admin.ModelAdmin):
    list_display = (
        "node",
        "team",
        "slot",
        "floor",
        "grade",
        "points",
        "is_spawn",
        "entered_at",
        "released_at",
    )
    list_filter = (ActiveFilter, "is_spawn", "release_reason", "node__level")
    list_select_related = ("node", "node__level", "team")
    search_fields = ("node__code", "team__code")
    autocomplete_fields = ("node", "team")

    # The change form stays fully read-only — an occupancy is a ledger row the
    # game writes, not a form to edit after the fact. The add form is the one
    # exception: an organiser sometimes has to seat a team by hand (a duel or
    # buyout settled off the board, a botched migration), so every meaningful
    # field is editable there. `points` and `entered_at` are computed/auto and
    # never editable, so they only appear on the change form.
    _CHANGE_READONLY = (
        "node",
        "team",
        "slot",
        "floor",
        "grade",
        "grade_multiplier",
        "points",
        "question",
        "question_assigned_at",
        "is_spawn",
        "source",
        "expires_at",
        "entered_at",
        "released_at",
        "release_reason",
    )
    _ADD_FIELDS = (
        "node",
        "team",
        "slot",
        "floor",
        "grade",
        "grade_multiplier",
        "question",
        "question_assigned_at",
        "is_spawn",
        "source",
        "expires_at",
        "released_at",
        "release_reason",
    )

    def get_readonly_fields(self, request, obj=None):
        # Adding: nothing read-only, so the whole add form is editable.
        return () if obj is None else self._CHANGE_READONLY

    def get_fields(self, request, obj=None):
        return self._ADD_FIELDS if obj is None else self._CHANGE_READONLY


@admin.register(GameSettings)
class GameSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "status",
        "started_at",
        "duration_minutes",
        "accumulated_seconds",
        "initial_balance",
        "entry_question_count",
        "entry_required_correct",
        "entry_grace_minutes",
        "entry_max_retries",
        "leaderboard_public",
        "leaderboard_frozen",
        "design_locked",
    )
    readonly_fields = (
        "started_at",
        "accumulated_seconds",
        "running_since",
        "leaderboard_snapshot",
    )

    def has_add_permission(self, request):
        return not GameSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionForm
    list_display = (
        "code",
        "title",
        "level",
        "mentor_list",
        "answer_type",
        "max_grade",
        "is_active",
        "created_at",
    )
    list_filter = ("level", "answer_type", "is_active", "mentors")
    search_fields = ("code", "title", "mentors__username")
    list_select_related = ("level",)
    filter_horizontal = ("mentors",)

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "level",
                    "code",
                    "title",
                    "body",
                    "attachment",
                    "answer_type",
                    "max_grade",
                    "mentors",
                    "is_active",
                )
            },
        ),
        ("Mentor reference", {"fields": ("answer_key",), "classes": ("collapse",)}),
    )

    class Media:
        js = ("game/admin/question_code_title.js",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("mentors")

    @admin.display(description="mentors")
    def mentor_list(self, obj):
        return "، ".join(m.get_username() for m in obj.mentors.all()) or "—"


@admin.register(TeamQuestion)
class TeamQuestionAdmin(admin.ModelAdmin):
    list_display = ("team", "question", "occupancy", "assigned_at")
    list_filter = ("question__level",)
    search_fields = ("team__code", "question__code")
    list_select_related = ("team", "question", "occupancy")
    readonly_fields = ("team", "question", "occupancy", "assigned_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "occupancy",
        "submitted_at",
        "submitted_by",
        "has_file",
    )
    list_filter = ("occupancy__node__level", "occupancy__team")
    search_fields = ("occupancy__team__code", "occupancy__node__code")
    list_select_related = ("occupancy__team", "occupancy__node", "submitted_by")
    readonly_fields = (
        "occupancy",
        "body",
        "file",
        "submitted_at",
        "submitted_by",
    )

    @admin.display(boolean=True, description="file")
    def has_file(self, obj):
        return bool(obj.file)

    def has_add_permission(self, request):
        return False


@admin.register(EntryQuestion)
class EntryQuestionAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "answer", "is_active", "served", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "title")

    @admin.display(description="served")
    def served(self, obj):
        return obj.attempts.count()


@admin.register(EntryAttempt)
class EntryAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "team",
        "position",
        "question",
        "answer",
        "is_correct",
        "answered_at",
        "superseded_at",
    )
    list_filter = ("is_correct", "question")
    search_fields = ("team__code", "question__code")
    list_select_related = ("team", "question")
    readonly_fields = (
        "team",
        "question",
        "position",
        "answer",
        "is_correct",
        "answered_at",
        "superseded_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Neighborhood)
class NeighborhoodAdmin(admin.ModelAdmin):
    list_display = ("index", "name", "theme", "color")
    ordering = ("index",)


@admin.register(MapDesign)
class MapDesignAdmin(admin.ModelAdmin):
    list_display = ("__str__", "road_style", "tint_strength", "halo_strength")

    def has_add_permission(self, request):
        return not MapDesign.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
