import logging

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .acting import ACTING_TEAM_SESSION_KEY, NoActingTeam, resolve_acting_team, set_acting_team
from .permissions import IsMentor
from .serializers import ActAsSerializer, LoginSerializer, MeSerializer

logger = logging.getLogger("karsoogh.auth")


def _me_response(request, user):
    try:
        team = resolve_acting_team(request)
    except NoActingTeam:
        team = None
    return Response(MeSerializer(user, context={"acting_team": team}).data)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data["username"]
        user = authenticate(
            request,
            username=username,
            password=serializer.validated_data["password"],
        )
        if user is None:
            logger.warning(
                "Failed login for username=%s ip=%s",
                username,
                request.META.get("REMOTE_ADDR", "-"),
            )
            return Response(
                {"detail": "Unable to log in with provided credentials."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request, user)
        request.session.pop(ACTING_TEAM_SESSION_KEY, None)
        return _me_response(request, user)


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsMentor]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsMentor]
    serializer_class = MeSerializer

    def get(self, request):
        return _me_response(request, request.user)


class ActAsView(APIView):
    permission_classes = [IsMentor]
    serializer_class = ActAsSerializer

    def post(self, request):
        serializer = ActAsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = serializer.validated_data["team"]
        set_acting_team(request, team)
        return Response(MeSerializer(request.user, context={"acting_team": team}).data)
