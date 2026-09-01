from django.urls import path

from .views import TerritoryGameDetailView, TerritoryGameListCreateView, TerritoryTurnView

app_name = "events"

urlpatterns = [
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
