from django.urls import path

from minesweeper import views

app_name = "minesweeper"

urlpatterns = [
    path("nodes/<slug:node_code>/enter/", views.EnterPlayView.as_view(), name="node-enter"),
    path("nodes/<slug:node_code>/start/", views.StartPlayView.as_view(), name="node-start"),
    path("attempts/<int:pk>/", views.AttemptDetailView.as_view(), name="attempt-detail"),
    path("attempts/<int:pk>/reveal/", views.RevealCellView.as_view(), name="attempt-reveal"),
    path("attempts/<int:pk>/flag/", views.FlagCellView.as_view(), name="attempt-flag"),
]
