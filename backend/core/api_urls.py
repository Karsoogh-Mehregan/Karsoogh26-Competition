from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path("auth/", include("accounts.urls")),
    path("teams/", include("teams.urls")),
    # game.urls owns "teams/<code>/nodes/<code>/..."; teams.urls only defines "",
    # so the two do not shadow each other.
    path("", include("game.urls")),
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
