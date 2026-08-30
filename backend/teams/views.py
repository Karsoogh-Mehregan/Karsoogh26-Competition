from rest_framework.generics import ListAPIView

from accounts.permissions import IsMentor
from core.openapi import OpenApiExample, extend_schema

from .models import Team
from .serializers import TeamSerializer


@extend_schema(
    tags=["teams"],
    summary="List teams",
    description="Every team: code, name, current balance, and the nodes it holds right now.",
    examples=[
        OpenApiExample(
            "team",
            value={
                "code": "alpha",
                "name": "Alpha",
                "balance": 42,
                "holdings": [
                    {
                        "id": 7,
                        "node_code": "n-12",
                        "node_name": "برج شمالی",
                        "level": "easy",
                        "slot": 1,
                        "floor": 2,
                    }
                ],
            },
            response_only=True,
        ),
    ],
)
class TeamListView(ListAPIView):
    queryset = Team.objects.with_holdings()
    serializer_class = TeamSerializer
    permission_classes = [IsMentor]
