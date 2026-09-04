from django.urls import path

from . import views

app_name = "duels"

urlpatterns = [
    path("", views.DuelListView.as_view(), name="duel-list"),
    path("targets/", views.DuelTargetListView.as_view(), name="duel-targets"),
    path("<int:pk>/", views.DuelDetailView.as_view(), name="duel-detail"),
    path("<int:pk>/resolve/", views.DuelResolveView.as_view(), name="duel-resolve"),
]
