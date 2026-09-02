from django.urls import path

from .views import (
    CentipedeActionView,
    CentipedeGameDetailView,
    CentipedeGameListCreateView,
    CharityBagDetailView,
    CharityBagListCreateView,
    CharityBagParticipationView,
    CharityBagResolveView,
    OlympicsMatchDetailView,
    OlympicsMatchListCreateView,
    OlympicsMatchStartView,
    OlympicsResultView,
    TerritoryGameDetailView,
    TerritoryGameListCreateView,
    TerritoryTurnView,
)

app_name = "events"

urlpatterns = [
    path("olympics/matches/", OlympicsMatchListCreateView.as_view(), name="olympics-list"),
    path(
        "olympics/matches/<int:pk>/",
        OlympicsMatchDetailView.as_view(),
        name="olympics-detail",
    ),
    path(
        "olympics/matches/<int:pk>/start/",
        OlympicsMatchStartView.as_view(),
        name="olympics-start",
    ),
    path(
        "olympics/matches/<int:pk>/results/",
        OlympicsResultView.as_view(),
        name="olympics-result",
    ),
    path("centipede/games/", CentipedeGameListCreateView.as_view(), name="centipede-list"),
    path(
        "centipede/games/<int:pk>/",
        CentipedeGameDetailView.as_view(),
        name="centipede-detail",
    ),
    path(
        "centipede/games/<int:pk>/actions/",
        CentipedeActionView.as_view(),
        name="centipede-action",
    ),
    path("charity-bag/instances/", CharityBagListCreateView.as_view(), name="charity-list"),
    path(
        "charity-bag/instances/<int:pk>/",
        CharityBagDetailView.as_view(),
        name="charity-detail",
    ),
    path(
        "charity-bag/instances/<int:pk>/participate/",
        CharityBagParticipationView.as_view(),
        name="charity-participate",
    ),
    path(
        "charity-bag/instances/<int:pk>/resolve/",
        CharityBagResolveView.as_view(),
        name="charity-resolve",
    ),
    path("territory-control/games/", TerritoryGameListCreateView.as_view(), name="territory-list"),
    path(
        "territory-control/games/<int:pk>/",
        TerritoryGameDetailView.as_view(),
        name="territory-detail",
    ),
    path(
        "territory-control/games/<int:pk>/turns/",
        TerritoryTurnView.as_view(),
        name="territory-turn",
    ),
]
