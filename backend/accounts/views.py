import logging

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.openapi import OpenApiExample, OpenApiResponse, extend_schema

from .acting import (
    ACTING_TEAM_SESSION_KEY,
    NoActingTeam,
    clear_acting_team,
    resolve_acting_team,
    set_acting_team,
)
from .permissions import IsMentor
from .serializers import ActAsSerializer, CsrfSerializer, LoginSerializer, MeSerializer

logger = logging.getLogger("karsoogh.auth")

_ME = {
    "id": 1,
    "username": "mentor",
    "is_staff": False,
    "acting_team": {"code": "alpha", "name": "Alpha", "balance": 42},
}
_ME_CLEARED = {**_ME, "acting_team": None}


def _me_response(request, user):
    try:
        team = resolve_acting_team(request)
    except NoActingTeam:
        team = None
    return Response(MeSerializer(user, context={"acting_team": team}).data)


@extend_schema(
    tags=["auth"],
    summary="Get CSRF token",
    description="Sets the `csrftoken` cookie. Send it back as `X-CSRFToken` on POST.",
    responses=CsrfSerializer,
    examples=[
        OpenApiExample("ok", value={"csrf_token": "abc123"}, response_only=True),
    ],
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@extend_schema(
    tags=["auth"],
    summary="Log in",
    description="Creates a session. Clears any acting-as team. Rotates the CSRF cookie.",
    request=LoginSerializer,
    responses=MeSerializer,
    examples=[
        OpenApiExample(
            "request",
            value={"username": "mentor", "password": "secret"},
            request_only=True,
        ),
        OpenApiExample("session", value=_ME_CLEARED, response_only=True),
    ],
)
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


@extend_schema(
    tags=["auth"],
    summary="Log out",
    description="Destroys the session cookie.",
    request=None,
    responses={204: OpenApiResponse(description="Session cleared.")},
)
@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["auth"],
    summary="Current user",
    description="Who you are and which team you are acting as (null if none).",
    responses=MeSerializer,
    examples=[OpenApiExample("acting as alpha", value=_ME, response_only=True)],
)
class MeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MeSerializer

    def get(self, request):
        return _me_response(request, request.user)


@extend_schema(
    tags=["auth"],
    summary="Act as a team",
    description="Stores the team on the session. Send `null` to stop acting as anyone.",
    request=ActAsSerializer,
    responses=MeSerializer,
    examples=[
        OpenApiExample("pick", value={"team": "alpha"}, request_only=True),
        OpenApiExample("clear", value={"team": None}, request_only=True),
        OpenApiExample("acting as alpha", value=_ME, response_only=True),
    ],
)
class ActAsView(APIView):
    permission_classes = [IsMentor]
    serializer_class = ActAsSerializer

    def post(self, request):
        serializer = ActAsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        team = serializer.validated_data["team"]
        if team is None:
            clear_acting_team(request)
            return _me_response(request, request.user)
        set_acting_team(request, team)
        return Response(MeSerializer(request.user, context={"acting_team": team}).data)
