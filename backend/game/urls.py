from django.urls import path

from game import sse, views

app_name = "game"

_HOLDING = "teams/<slug:team_code>/nodes/<slug:node_code>/"

urlpatterns = [
    # Clock and stage: every client polls state; only mentors may change it.
    path("game/state/", views.GameStateView.as_view(), name="game-state"),
    path("game/settings/", views.GameSettingsView.as_view(), name="game-settings"),
    # Mentor actions on a holding, addressed by (team, node).
    path(f"{_HOLDING}assign-question/", views.AssignQuestionView.as_view(), name="assign-question"),
    path(f"{_HOLDING}grade/", views.GradeView.as_view(), name="grade"),
    path(f"{_HOLDING}release/", views.ReleaseView.as_view(), name="release"),
    path(
        "teams/<slug:team_code>/attempts/",
        views.TeamAttemptsView.as_view(),
        name="team-attempts",
    ),
    # Team-facing question + submission flow, addressed by occupancy id.
    path(
        "occupancies/<int:pk>/question/",
        views.OccupancyQuestionView.as_view(),
        name="occupancy-question",
    ),
    path(
        "occupancies/<int:pk>/submit/",
        views.OccupancySubmitView.as_view(),
        name="occupancy-submit",
    ),
    path("submissions/", views.SubmissionListView.as_view(), name="submission-list"),
    path("submissions/<int:pk>/", views.SubmissionDetailView.as_view(), name="submission-detail"),
    path(
        "submissions/<int:pk>/grade/",
        views.SubmissionGradeView.as_view(),
        name="submission-grade",
    ),
    path(
        "media/submissions/<int:pk>/",
        views.SubmissionMediaView.as_view(),
        name="submission-media",
    ),
    path(
        "media/questions/<int:pk>/",
        views.QuestionMediaView.as_view(),
        name="question-media",
    ),
    # Plain async view, not DRF: APIView.dispatch is sync-only in DRF 3.18.
    path("realtime/stream/", sse.board_stream, name="board-stream"),
]
