from django.urls import path

from .views import (
    CharityBagDetailView,
    CharityBagListCreateView,
    CharityBagParticipationView,
    CharityBagResolveView,
    TerritoryGameDetailView,
    TerritoryGameListCreateView,
    TerritoryTurnView,
)

app_name = "events"

urlpatterns = [
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
