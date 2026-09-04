from django.contrib import admin

from .models import DifficultyConfig, MinesweeperAttempt, MinesweeperGame, MinesweeperSettings


@admin.register(DifficultyConfig)
class DifficultyConfigAdmin(admin.ModelAdmin):
    """Board size, mines and payout, editable between rounds.

    Retuning a row reshapes the *next* board generated at that difficulty.
    Boards already in play keep the numbers they were built with, so nobody
    loses a grid mid-game.
    """

    list_display = ("key", "label", "width", "height", "mine_count", "base_score", "sort_order")
    list_editable = ("width", "height", "mine_count", "base_score", "sort_order")
    search_fields = ("key", "label")
    ordering = ("sort_order", "key")


@admin.register(MinesweeperSettings)
class MinesweeperSettingsAdmin(admin.ModelAdmin):
    list_display = ("node", "node_level", "difficulty", "enabled", "updated_at")
    list_filter = ("difficulty", "enabled", "node__level")
    list_editable = ("difficulty", "enabled")
    search_fields = ("node__code", "node__name")
    list_select_related = ("node", "node__level")
    autocomplete_fields = ("node",)
    ordering = ("node__code",)
    actions = ("enable_boards", "disable_boards")

    @admin.display(description="level", ordering="node__level")
    def node_level(self, obj):
        return obj.node.level_id

    @admin.action(description="Enable the selected boards")
    def enable_boards(self, request, queryset):
        updated = queryset.update(enabled=True)
        self.message_user(request, f"{updated} board(s) enabled.")

    @admin.action(description="Disable the selected boards")
    def disable_boards(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(request, f"{updated} board(s) disabled.")


class MinesweeperAttemptInline(admin.TabularInline):
    model = MinesweeperAttempt
    extra = 0
    can_delete = False
    autocomplete_fields = ("team",)
    readonly_fields = (
        "team",
        "status",
        "score",
        "board",
        "started_at",
        "finished_at",
        "created_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(MinesweeperGame)
class MinesweeperGameAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "node",
        "difficulty",
        "width",
        "height",
        "mine_count",
        "created_at",
    )
    list_filter = ("difficulty",)
    search_fields = ("id", "node__code", "node__name")
    list_select_related = ("node",)
    autocomplete_fields = ("node",)
    ordering = ("-created_at",)
    inlines = (MinesweeperAttemptInline,)
    readonly_fields = (
        "node",
        "difficulty",
        "width",
        "height",
        "mine_count",
        "base_score",
        "board",
        "created_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(MinesweeperAttempt)
class MinesweeperAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "game",
        "team",
        "status",
        "score",
        "started_at",
        "finished_at",
    )
    list_filter = ("status", "game__difficulty")
    search_fields = ("team__code", "team__name", "game__node__code")
    list_select_related = ("game", "game__node", "team")
    autocomplete_fields = ("game", "team")
    readonly_fields = ("started_at", "finished_at", "created_at", "board")
    ordering = ("-started_at",)
