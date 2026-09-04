from django.urls import path

from .views import (
    ClaimStartView,
    TeamBalanceEventView,
    TeamItemListView,
    TeamListView,
    UseTeamItemView,
)

urlpatterns = [
    path("", TeamListView.as_view(), name="team-list"),
    path("me/items/", TeamItemListView.as_view(), name="team-items"),
    path("me/items/use/", UseTeamItemView.as_view(), name="team-items-use"),
    path("<slug:team_code>/claim-start/", ClaimStartView.as_view(), name="claim-start"),
    path(
        "<slug:team_code>/balance-events/",
        TeamBalanceEventView.as_view(),
        name="team-balance-events",
    ),
]
