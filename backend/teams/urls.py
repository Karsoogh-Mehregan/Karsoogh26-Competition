from django.urls import path

from .views import ClaimStartView, TeamListView

urlpatterns = [
    path("", TeamListView.as_view(), name="team-list"),
    path("claim-start/", ClaimStartView.as_view(), name="claim-start"),
]
