"""The map's look: neighbourhood colours, road style, and per-node building types.

Read by every client at load; written only by Designers. A write publishes a
`map.design` frame so open clients refetch, the same way a status change
publishes `game.state`.

The two boards play identical maps, so this app treats them as one: a read
returns a single board's copy of the node list (they agree), and a node write is
applied to *every* board's copy in one transaction. A Designer therefore pins a
building once rather than twice, and the two contests cannot drift apart — which
they must not, since the map is the fairness guarantee between them.
"""

from django.db import transaction
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsDesigner
from core.boards import viewing_board
from core.openapi import OpenApiExample, OpenApiParameter, extend_schema
from game import services
from game.api_exceptions import Conflict
from game.models import MapDesign, Neighborhood, Node, Occupancy
from game.serializers import (
    MapDesignPatchSerializer,
    MapDesignSerializer,
    NodeDesignSerializer,
)

_DESIGN_EXAMPLE = {
    "road_style": "curved",
    "tint_strength": 8,
    "halo_strength": 45,
    "neighborhoods": [{"index": 0, "name": "محلهٔ آبی", "theme": "water", "color": "#3b82c4"}],
    "nodes": [
        {
            "code": "L1_0",
            "level": "spawn",
            "capacity": 1,
            "archetype": "",
            "minesweeper": False,
            "gelled": False,
        }
    ],
}


def _design_payload(board: str) -> dict:
    design = MapDesign.load()
    # Attach the two lists by hand: they are not relations on the singleton.
    design.neighborhoods = Neighborhood.objects.order_by("index")
    design.nodes = (
        Node.objects.filter(board=board)
        .select_related("level", "minesweeper_settings")
        .order_by("code")
    )
    return MapDesignSerializer(design).data


@extend_schema(
    tags=["design"],
    summary="Read or change the map's look",
    description=(
        "GET is open to every logged-in user: sector colours and themes, road style, "
        "and every node's level, capacity, pinned building type and whether a minesweeper "
        "board is playable on it. PATCH is Designer-only "
        "and takes any subset of the settings plus a `neighborhoods` list addressed by "
        "`index`. A write publishes a `map.design` event."
    ),
    request=MapDesignPatchSerializer,
    responses=MapDesignSerializer,
    examples=[
        OpenApiExample("design", value=_DESIGN_EXAMPLE, response_only=True),
        OpenApiExample(
            "recolour one sector",
            value={"neighborhoods": [{"index": 3, "color": "#4c7f3b"}]},
            request_only=True,
        ),
    ],
)
class MapDesignView(APIView):
    serializer_class = MapDesignSerializer

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsDesigner()]
        return [IsAuthenticated()]

    def get(self, request):
        return Response(_design_payload(viewing_board(request)))

    def patch(self, request):
        payload = MapDesignPatchSerializer(data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        with transaction.atomic():
            design = MapDesign.load()
            for field in ("road_style", "tint_strength", "halo_strength"):
                if field in data:
                    setattr(design, field, data[field])
            design.save()

            for row in data.get("neighborhoods", []):
                neighborhood = Neighborhood.objects.filter(index=row["index"]).first()
                if neighborhood is None:
                    raise NotFound(f"محلهٔ شمارهٔ {row['index']} وجود ندارد.")
                for field in ("name", "theme", "color"):
                    if field in row:
                        setattr(neighborhood, field, row[field])
                neighborhood.save()

            services.publish_on_commit(services.MAP_DESIGN, {"scope": "map"})

        return Response(_design_payload(viewing_board(request)))


@extend_schema(
    tags=["design"],
    summary="Pin a node's building type or move it between levels",
    description=(
        "Designer-only. `archetype` pins a building type (empty string unpins, letting the "
        "renderer choose). `level` moves the node between tiers and is refused with a 409 "
        "while any team holds a seat on it — capacity and entry cost hang off the level."
    ),
    parameters=[OpenApiParameter("node_code", str, OpenApiParameter.PATH, description="e.g. L6_0")],
    request=NodeDesignSerializer,
    responses=NodeDesignSerializer,
    examples=[
        OpenApiExample("pin", value={"archetype": "observatory"}, request_only=True),
        OpenApiExample(
            "pinned",
            value={
                "code": "L6_0",
                "level": "hard",
                "capacity": 3,
                "archetype": "observatory",
                "minesweeper": False,
                "gelled": False,
            },
            response_only=True,
        ),
    ],
)
class NodeDesignView(APIView):
    permission_classes = [IsDesigner]
    serializer_class = NodeDesignSerializer

    def patch(self, request, node_code: str):
        copies = list(
            Node.objects.select_related("level", "minesweeper_settings")
            .filter(code=node_code)
            .order_by("board")
        )
        if not copies:
            raise NotFound(f"خانهٔ «{node_code}» پیدا نشد.")

        # Validated once, then applied to every board's copy: the change is to
        # the map, and the map is shared even though its rows are not.
        payloads = [NodeDesignSerializer(node, data=request.data, partial=True) for node in copies]
        for payload in payloads:
            payload.is_valid(raise_exception=True)

        new_level = payloads[0].validated_data.get("level_id")
        moving = [node for node in copies if new_level is not None and new_level != node.level_id]
        # Occupied on *either* board blocks the move on both, so the two copies
        # never disagree about a node's tier.
        if moving and Occupancy.objects.active().filter(node__in=moving).exists():
            raise Conflict("تا وقتی تیمی روی این خانه است نمی‌توان سطح آن را عوض کرد.")

        with transaction.atomic():
            for payload in payloads:
                payload.save()
            services.publish_on_commit(services.MAP_DESIGN, {"scope": "node", "node": node_code})

        shown = copies[0]
        shown.refresh_from_db()
        return Response(NodeDesignSerializer(shown).data)
