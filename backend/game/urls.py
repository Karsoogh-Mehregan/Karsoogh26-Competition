from django.urls import path

from game import views

app_name = "game"

_HOLDING = "teams/<slug:team_code>/nodes/<slug:node_code>/"

urlpatterns = [
    # Mentor actions on a holding, addressed by (team, node).
    path(f"{_HOLDING}assign-question/", views.AssignQuestionView.as_view(), name="assign-question"),
    path(f"{_HOLDING}grade/", views.GradeView.as_view(), name="grade"),
    path(f"{_HOLDING}release/", views.ReleaseView.as_view(), name="release"),
    # Pre-game entry sheet, always the caller's own team.
    path("entry/sheet/", views.EntrySheetView.as_view(), name="entry-sheet"),
    path(
        "entry/questions/<slug:code>/answer/",
        views.EntryAnswerView.as_view(),
        name="entry-answer",
    ),
    path(
        "entry/questions/<slug:code>/refresh/",
        views.EntryRefreshView.as_view(),
        name="entry-refresh",
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
]
