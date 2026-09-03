from django.urls import path

from minesweeper import views

app_name = "minesweeper"

urlpatterns = [
    path("games/", views.CreateGameView.as_view(), name="game-create"),
    path("games/<int:pk>/", views.GameDetailView.as_view(), name="game-detail"),
    path("games/<int:pk>/join/", views.JoinGameView.as_view(), name="game-join"),
    path("games/<int:pk>/reveal/", views.RevealCellView.as_view(), name="game-reveal"),
    path("games/<int:pk>/flag/", views.FlagCellView.as_view(), name="game-flag"),
]
