from django.urls import path

from .views import AssignQuestionView, GradeView, ReleaseView

app_name = "game"

_HOLDING = "teams/<slug:team_code>/nodes/<slug:node_code>/"

urlpatterns = [
    path(f"{_HOLDING}assign-question/", AssignQuestionView.as_view(), name="assign-question"),
    path(f"{_HOLDING}grade/", GradeView.as_view(), name="grade"),
    path(f"{_HOLDING}release/", ReleaseView.as_view(), name="release"),
]
