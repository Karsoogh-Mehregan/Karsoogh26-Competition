"""The buyout API.

One read and one write:

* `GET  /api/buyouts/targets/` — the table of floors this team may buy.
* `POST /api/buyouts/`         — buy one.

Shaped like `/api/duels/targets/` on purpose: the house panel filters the table
to the node it is showing, and a node with no rows is a node with no purchase,
so the panel never offers a buyout the server would refuse.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import GameIsRunning
from core.openapi import OpenApiExample, extend_schema
from game.permissions import IsTeamMember
from game.serializers import (
    BuyoutResultSerializer,
    BuyOutSerializer,
    BuyoutTargetSerializer,
)
from game.services.buyout import buy_out, buyable_targets

_TARGET_EXAMPLE = {
    "occupancy_id": 41,
    "node_code": "L3_12",
    "node_name": "برج شمالی",
    "level": "hard",
    "floor": 2,
    "team": {"code": "beta", "name": "بتا", "color": "#00ff00"},
    "cost": 4000,
    "points": 1000,
}


@extend_schema(
    tags=["buyouts"],
    summary="Floors this team may buy",
    description=(
        "Every owned floor of every building adjacent to the team, minus houses the "
        "team already sits in and seats under an open duel. Each row carries the price "
        "of buying it and the points the buyer is paid for it."
    ),
    responses=BuyoutTargetSerializer(many=True),
    examples=[OpenApiExample("targets", value=[_TARGET_EXAMPLE], response_only=True)],
)
class BuyoutTargetListView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember]
    serializer_class = BuyoutTargetSerializer

    def get(self, request):
        rows = buyable_targets(request.user.team)
        return Response(BuyoutTargetSerializer(rows, many=True).data)


@extend_schema(
    tags=["buyouts"],
    summary="Buy a floor out from its holder",
    description=(
        "Charges the floor's buyout price, puts the holder out without clawing "
        "anything back, seats the caller on the same slot and floor, and pays the "
        "caller the floor's points. 409 with a Persian reason when refused."
    ),
    request=BuyOutSerializer,
    responses=BuyoutResultSerializer,
    examples=[
        OpenApiExample("request", value={"occupancy": 41}, request_only=True),
    ],
)
class BuyOutView(APIView):
    permission_classes = [IsAuthenticated, IsTeamMember, GameIsRunning]
    serializer_class = BuyOutSerializer

    def post(self, request):
        payload = BuyOutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        team = request.user.team
        # `BuyoutRefused` is an APIException: it answers 409 with its message.
        holding = buy_out(team, payload.validated_data["occupancy"])
        team.refresh_from_db(fields=["balance"])
        return Response(
            BuyoutResultSerializer({"holding": holding, "balance": team.balance}).data,
            status=201,
        )
