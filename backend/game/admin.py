from django.contrib import admin

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
        "networth_base",
        "networth_factor",
        "duel_factor",
        "buyout_factor",
    )
    inlines = [FloorRewardInline]


@admin.register(FloorReward)
class FloorRewardAdmin(admin.ModelAdmin):
    list_display = ("level", "floor", "points", "networth", "duel_cost", "buyout_cost")
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
    list_display = ("code", "name", "level", "archetype")
    list_filter = ("level", "archetype")
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
    readonly_fields = (
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
        "expires_at",
        "entered_at",
        "released_at",
        "release_reason",
    )

    def has_add_permission(self, request):
        return False


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
    )
    readonly_fields = ("started_at", "accumulated_seconds", "running_since")

    def has_add_permission(self, request):
        return not GameSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "level", "answer_type", "is_active", "created_at")
    list_filter = ("level", "answer_type", "is_active")
    search_fields = ("code", "title")
    list_select_related = ("level",)
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
                    "is_active",
                )
            },
        ),
        ("Mentor reference", {"fields": ("answer_key",), "classes": ("collapse",)}),
    )

    class Media:
        js = ("game/admin/question_code_title.js",)


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
