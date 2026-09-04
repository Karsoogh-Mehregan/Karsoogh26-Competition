from django.contrib import admin

from .models import (
    AuctionBid,
    AuctionEvent,
    AuctionPair,
    CentipedeDecision,
    CentipedeGame,
    CharityBagEvent,
    CharityBagParticipation,
    EventConfiguration,
    MatchmakingTicket,
    OlympicsMatch,
    OlympicsResult,
    PigEvent,
    PigGame,
    PigRoll,
    TerritoryCell,
    TerritoryGame,
    TerritoryTurn,
    WheelEvent,
    WheelPrize,
    WheelSpin,
)


class TerritoryCellInline(admin.TabularInline):
    model = TerritoryCell
    extra = 0
    max_num = 25
    readonly_fields = ("row", "column", "value", "owner")


@admin.register(TerritoryGame)
class TerritoryGameAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "player_one",
        "player_two",
        "active_player",
        "turns_completed",
        "status",
        "winner",
    )
    list_filter = ("status",)
    inlines = (TerritoryCellInline,)


@admin.register(TerritoryTurn)
class TerritoryTurnAdmin(admin.ModelAdmin):
    list_display = ("game", "number", "acting_player", "action_type", "success", "dice_result")
    list_filter = ("action_type", "success")


class CharityBagParticipationInline(admin.TabularInline):
    model = CharityBagParticipation
    extra = 0
    readonly_fields = (
        "team",
        "action",
        "amount",
        "stake_deducted",
        "final_payout",
        "submitted_at",
        "settled_at",
    )


@admin.register(CharityBagEvent)
class CharityBagEventAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "starts_at",
        "ends_at",
        "total_contributed",
        "total_requested",
        "charity_succeeded",
    )
    list_filter = ("status", "charity_succeeded")
    inlines = (CharityBagParticipationInline,)


@admin.register(CharityBagParticipation)
class CharityBagParticipationAdmin(admin.ModelAdmin):
    list_display = ("event", "team", "action", "amount", "final_payout", "submitted_at")
    list_filter = ("action",)


class CentipedeDecisionInline(admin.TabularInline):
    model = CentipedeDecision
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    readonly_fields = (
        "sequence",
        "round_number",
        "actor",
        "action",
        "displayed_reward",
        "created_at",
    )


@admin.register(CentipedeGame)
class CentipedeGameAdmin(admin.ModelAdmin):
    readonly_fields = tuple(field.name for field in CentipedeGame._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = (
        "id",
        "player_one",
        "player_two",
        "round_number",
        "active_player",
        "status",
        "winner",
        "rules_version",
        "pot",
    )
    list_filter = ("status",)
    inlines = (CentipedeDecisionInline,)


@admin.register(CentipedeDecision)
class CentipedeDecisionAdmin(admin.ModelAdmin):
    readonly_fields = tuple(field.name for field in CentipedeDecision._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = ("game", "sequence", "round_number", "actor", "action", "displayed_reward")
    list_filter = ("action",)


class OlympicsResultInline(admin.TabularInline):
    model = OlympicsResult
    extra = 0
    readonly_fields = (
        "request_id",
        "round_number",
        "player_one_attempts",
        "player_two_attempts",
        "player_one_total",
        "player_two_total",
        "player_one_best_distance",
        "player_two_best_distance",
        "outcome",
        "recorded_by",
        "created_at",
    )


@admin.register(OlympicsMatch)
class OlympicsMatchAdmin(admin.ModelAdmin):
    list_display = ("id", "mini_game", "player_one", "player_two", "status", "winner")
    list_filter = ("mini_game", "status")
    inlines = (OlympicsResultInline,)


@admin.register(OlympicsResult)
class OlympicsResultAdmin(admin.ModelAdmin):
    list_display = ("match", "round_number", "outcome", "recorded_by", "created_at")
    list_filter = ("outcome",)


@admin.register(AuctionEvent)
class AuctionEventAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "duration_seconds", "starts_at", "ends_at")
    readonly_fields = ("ranking_snapshot", "starts_at", "ends_at", "settled_at")


admin.site.register(AuctionPair)
admin.site.register(AuctionBid)
admin.site.register(WheelEvent)
admin.site.register(WheelPrize)
admin.site.register(WheelSpin)
admin.site.register(PigEvent)
admin.site.register(PigGame)
admin.site.register(PigRoll)


@admin.register(EventConfiguration)
class EventConfigurationAdmin(admin.ModelAdmin):
    list_display = ("code", "enabled", "duration_seconds", "updated_at")
    list_editable = ("enabled", "duration_seconds")
    list_filter = ("enabled",)
    actions = ("enable_events", "disable_events")

    @admin.action(description="فعال‌کردن رویدادهای انتخاب‌شده")
    def enable_events(self, request, queryset):
        updated = queryset.update(enabled=True)
        self.message_user(request, f"{updated} رویداد فعال شد.")

    @admin.action(description="غیرفعال‌کردن رویدادهای انتخاب‌شده")
    def disable_events(self, request, queryset):
        updated = queryset.update(enabled=False)
        self.message_user(request, f"{updated} رویداد غیرفعال شد.")


@admin.register(MatchmakingTicket)
class MatchmakingTicketAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "event_code",
        "team",
        "status",
        "matched_team",
        "match_id",
        "dismissed_at",
        "created_at",
    )
    list_filter = ("event_code", "status")
    readonly_fields = (
        "event_code",
        "team",
        "status",
        "matched_team",
        "match_id",
        "created_at",
        "matched_at",
        "dismissed_at",
    )
