from django.urls import path

from .views import (
    AuctionBidView,
    AuctionEventDetailView,
    AuctionEventListCreateView,
    AuctionResolveView,
    CentipedeActionView,
    CentipedeGameDetailView,
    CentipedeGameListCreateView,
    CharityBagDetailView,
    CharityBagListCreateView,
    CharityBagParticipationView,
    CharityBagResolveView,
    OlympicsMatchDetailView,
    OlympicsMatchListCreateView,
    OlympicsMatchStartView,
    OlympicsResultView,
    PigActionView,
    PigEventFinishView,
    PigEventListCreateView,
    PigGameStartView,
    TerritoryGameDetailView,
    TerritoryGameListCreateView,
    TerritoryTurnView,
    WheelDeliveryView,
    WheelEventDetailView,
    WheelEventListCreateView,
    WheelSpinView,
    WheelStartView,
    WheelStopView,
)

app_name = "events"

urlpatterns = [
    path("limited-auction/events/", AuctionEventListCreateView.as_view(), name="auction-list"),
    path(
        "limited-auction/events/<int:pk>/", AuctionEventDetailView.as_view(), name="auction-detail"
    ),
    path(
        "limited-auction/events/<int:pk>/resolve/",
        AuctionResolveView.as_view(),
        name="auction-resolve",
    ),
    path("limited-auction/pairs/<int:pk>/bids/", AuctionBidView.as_view(), name="auction-bid"),
    path("prize-wheel/events/", WheelEventListCreateView.as_view(), name="wheel-list"),
    path("prize-wheel/events/<int:pk>/", WheelEventDetailView.as_view(), name="wheel-detail"),
    path("prize-wheel/events/<int:pk>/start/", WheelStartView.as_view(), name="wheel-start"),
    path("prize-wheel/events/<int:pk>/stop/", WheelStopView.as_view(), name="wheel-stop"),
    path("prize-wheel/events/<int:pk>/spins/", WheelSpinView.as_view(), name="wheel-spin"),
    path("prize-wheel/spins/<int:pk>/deliver/", WheelDeliveryView.as_view(), name="wheel-deliver"),
    path("pig/events/", PigEventListCreateView.as_view(), name="pig-list"),
    path("pig/events/<int:pk>/finish/", PigEventFinishView.as_view(), name="pig-finish"),
    path("pig/events/<int:pk>/games/", PigGameStartView.as_view(), name="pig-game-start"),
    path("pig/games/<int:pk>/actions/", PigActionView.as_view(), name="pig-action"),
    path("olympics/matches/", OlympicsMatchListCreateView.as_view(), name="olympics-list"),
    path(
        "olympics/matches/<int:pk>/",
        OlympicsMatchDetailView.as_view(),
        name="olympics-detail",
    ),
    path(
        "olympics/matches/<int:pk>/start/",
        OlympicsMatchStartView.as_view(),
        name="olympics-start",
    ),
    path(
        "olympics/matches/<int:pk>/results/",
        OlympicsResultView.as_view(),
        name="olympics-result",
    ),
    path("centipede/games/", CentipedeGameListCreateView.as_view(), name="centipede-list"),
    path(
        "centipede/games/<int:pk>/",
        CentipedeGameDetailView.as_view(),
        name="centipede-detail",
    ),
    path(
        "centipede/games/<int:pk>/actions/",
        CentipedeActionView.as_view(),
        name="centipede-action",
    ),
    path("charity-bag/instances/", CharityBagListCreateView.as_view(), name="charity-list"),
    path(
        "charity-bag/instances/<int:pk>/",
        CharityBagDetailView.as_view(),
        name="charity-detail",
    ),
    path(
        "charity-bag/instances/<int:pk>/participate/",
        CharityBagParticipationView.as_view(),
        name="charity-participate",
    ),
    path(
        "charity-bag/instances/<int:pk>/resolve/",
        CharityBagResolveView.as_view(),
        name="charity-resolve",
    ),
    path("territory-control/games/", TerritoryGameListCreateView.as_view(), name="territory-list"),
    path(
        "territory-control/games/<int:pk>/",
        TerritoryGameDetailView.as_view(),
        name="territory-detail",
    ),
    path(
        "territory-control/games/<int:pk>/turns/",
        TerritoryTurnView.as_view(),
        name="territory-turn",
    ),
]
