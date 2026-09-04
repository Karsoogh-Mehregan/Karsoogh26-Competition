from django.contrib import admin

from .models import MinesweeperAttempt, MinesweeperGame, MinesweeperSettings


@admin.register(MinesweeperSettings)
class MinesweeperSettingsAdmin(admin.ModelAdmin):
    list_display = ("node", "difficulty", "enabled", "updated_at")
    list_filter = ("difficulty", "enabled")
    search_fields = ("node__code", "node__name")
    list_select_related = ("node",)
    autocomplete_fields = ("node",)
    ordering = ("node__code",)


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
