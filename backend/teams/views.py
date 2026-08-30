from rest_framework.generics import ListAPIView

from accounts.permissions import IsMentor
from core.openapi import OpenApiExample, extend_schema

from .models import Team
from .serializers import TeamSerializer


@extend_schema(
    tags=["teams"],
    summary="List teams",
    description="Every team: code, name, current balance.",
    examples=[
        OpenApiExample(
            "team",
            value={"code": "alpha", "name": "Alpha", "balance": 42},
            response_only=True,
        ),
    ],
)
class TeamListView(ListAPIView):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [IsMentor]
