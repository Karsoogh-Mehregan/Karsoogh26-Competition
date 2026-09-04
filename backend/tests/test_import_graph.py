"""The map lives in the SPA's graph_data.json; import_graph is the only path
from it into Node/Edge, so the mapping and the upsert semantics are pinned here.
"""

import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.boards import Board
from game.models import Edge, Node

pytestmark = pytest.mark.django_db


GRAPH = {
    "nodes": [
        {"id": "L1_0", "type": "start"},
        {"id": "L1_1", "type": "gateway"},
        {"id": "L3_0", "type": "l3"},
        {"id": "C34_0", "type": "c34"},
        {"id": "CENTER", "type": "center"},
    ],
    "edges": [
        {"source": "L1_1", "target": "L1_0", "directed": False},
        {"source": "L3_0", "target": "C34_0", "directed": True},
        {"source": "CENTER", "target": "L3_0", "directed": False},
    ],
}


@pytest.fixture
def graph_file(tmp_path):
    def write(graph=GRAPH):
        path = tmp_path / "graph_data.json"
        path.write_text(json.dumps(graph), encoding="utf-8")
        return path

    return write


def test_imports_nodes_at_their_mapped_level(graph_file):
    call_command("import_graph", board=Board.GIRLS, file=graph_file())

    levels = dict(Node.objects.values_list("code", "level_id"))
    assert levels == {
        "L1_0": "spawn",
        "L1_1": "easy",
        "L3_0": "medium",
        "C34_0": "toll",
        "CENTER": "center",
    }


def test_undirected_edges_are_normalised_directed_ones_are_not(graph_file):
    call_command("import_graph", board=Board.GIRLS, file=graph_file())

    assert Edge.objects.count() == 3
    for edge in Edge.objects.filter(directed=False):
        assert edge.a_id < edge.b_id

    funnel = Edge.objects.get(directed=True)
    assert (funnel.a.code, funnel.b.code) == ("L3_0", "C34_0")


def test_rerun_changes_nothing(graph_file):
    path = graph_file()
    call_command("import_graph", board=Board.GIRLS, file=path)
    before = set(Edge.objects.values_list("a_id", "b_id", "directed"))

    call_command("import_graph", board=Board.GIRLS, file=path)

    assert Node.objects.count() == 5
    assert set(Edge.objects.values_list("a_id", "b_id", "directed")) == before


def test_rerun_moves_a_node_that_changed_type(graph_file):
    call_command("import_graph", board=Board.GIRLS, file=graph_file())

    regraded = json.loads(json.dumps(GRAPH))
    regraded["nodes"][2]["type"] = "l5"
    call_command("import_graph", board=Board.GIRLS, file=graph_file(regraded))

    assert Node.objects.get(code="L3_0").level_id == "hard"


def test_dry_run_writes_nothing(graph_file):
    call_command("import_graph", board=Board.GIRLS, file=graph_file(), dry_run=True)

    assert Node.objects.count() == 0
    assert Edge.objects.count() == 0


def test_unmapped_node_type_is_refused(graph_file):
    graph = json.loads(json.dumps(GRAPH))
    graph["nodes"].append({"id": "X_0", "type": "wormhole"})

    with pytest.raises(CommandError, match="wormhole"):
        call_command("import_graph", board=Board.GIRLS, file=graph_file(graph))

    assert Node.objects.count() == 0


def test_edge_endpoint_without_a_node_is_refused(graph_file):
    graph = json.loads(json.dumps(GRAPH))
    graph["edges"].append({"source": "L1_0", "target": "NOWHERE", "directed": False})

    with pytest.raises(CommandError, match="NOWHERE"):
        call_command("import_graph", board=Board.GIRLS, file=graph_file(graph))

    assert Node.objects.count() == 0
