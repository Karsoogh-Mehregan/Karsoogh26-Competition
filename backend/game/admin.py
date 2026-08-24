from django.contrib import admin

from .models import (
    Edge,
    FloorReward,
    GameSettings,
    GradeMultiplier,
    LevelConfig,
    Node,
    Occupancy,
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
    fields = ("team", "slot", "floor", "grade", "points_awarded", "is_spawn")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return super().get_queryset(request).filter(released_at__isnull=True)


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "level")
    list_filter = ("level",)
    search_fields = ("code", "name")
    list_select_related = ("level",)
    inlines = [OccupancyInline]


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ("a", "b")
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
        "points_awarded",
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
        "points_awarded",
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
    list_display = ("__str__", "status", "initial_balance", "attempt_ttl_minutes")

    def has_add_permission(self, request):
        return not GameSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
