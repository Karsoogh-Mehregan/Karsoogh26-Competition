from django.urls import path

from game import views

urlpatterns = [
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
