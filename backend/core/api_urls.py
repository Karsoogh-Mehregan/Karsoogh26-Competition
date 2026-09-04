from django.conf import settings
from django.urls import include, path

from teams.views import LeaderboardView

urlpatterns = [
    path("auth/", include("accounts.urls")),
    path("teams/", include("teams.urls")),
    path("leaderboard/", LeaderboardView.as_view(), name="leaderboard"),
    path("events/", include("events.urls")),
    # game.urls owns "teams/<code>/nodes/<code>/..."; teams.urls only defines "",
    # so the two do not shadow each other.
    path("", include("game.urls")),
    # notifications.urls owns "notifications/..." and "messages/...", which
    # nothing above claims.
    path("", include("notifications.urls")),
    path("minesweeper/", include("minesweeper.urls")),
]

if settings.DEBUG:
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
    ]
