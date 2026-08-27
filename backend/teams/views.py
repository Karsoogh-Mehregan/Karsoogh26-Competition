from rest_framework.generics import ListAPIView

from accounts.permissions import IsMentor

from .models import Team
from .serializers import TeamSerializer


class TeamListView(ListAPIView):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [IsMentor]
