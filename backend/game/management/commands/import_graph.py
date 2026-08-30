"""Import the map topology from the SPA's graph_data.json into Node/Edge.

The JSON is the single source of truth for the map; the frontend keeps the
layout fields (x/y/color/shape/theta/r) and the backend keeps only the topology,
sharing node ids so the two halves address the same map.

Upsert only: rows are never deleted, so Occupancy's PROTECT FK is never tripped
and re-running is safe mid-game.
"""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from game.models import Edge, Node

DEFAULT_PATH = Path("frontend/src/data/graph_data.json")

TYPE_TO_LEVEL = {
    "start": "spawn",
    "gateway": "easy",
    "l1": "easy",
    "l2": "easy",
    "l3": "medium",
    "l4": "medium",
    "l5": "hard",
    "l6": "hard",
    "center": "hard",
    "c34": "toll",
    "c45": "toll",
}


class Command(BaseCommand):
    help = "Import nodes and edges from the frontend's graph_data.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=Path,
            default=settings.BASE_DIR.parent / DEFAULT_PATH,
            help=f"Path to graph_data.json (default: {DEFAULT_PATH}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change, then roll back.",
        )

    def handle(self, *args, **options):
        path = options["file"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise CommandError(f"Cannot read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"{path} is not valid JSON: {exc}") from exc

        with transaction.atomic():
            nodes = self._import_nodes(data.get("nodes", []))
            self._import_edges(data.get("edges", []), nodes)
            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry run: rolled back."))

    def _import_nodes(self, raw_nodes):
        unknown = sorted({n["type"] for n in raw_nodes if n["type"] not in TYPE_TO_LEVEL})
        if unknown:
            raise CommandError(
                f"No level mapping for node type(s): {', '.join(unknown)}. "
                f"Add them to TYPE_TO_LEVEL."
            )

        wanted = {}
        for n in raw_nodes:
            code = n["id"]
            level = TYPE_TO_LEVEL[n["type"]]
            if wanted.get(code, level) != level:
                raise CommandError(f"Node {code} appears twice with different types.")
            wanted[code] = level

        existing = {node.code: node for node in Node.objects.all()}

        to_create = [
            Node(code=code, level_id=level)
            for code, level in wanted.items()
            if code not in existing
        ]
        to_update = [
            node
            for code, level in wanted.items()
            if (node := existing.get(code)) is not None and node.level_id != level
        ]
        for node in to_update:
            node.level_id = wanted[node.code]

        Node.objects.bulk_create(to_create)
        Node.objects.bulk_update(to_update, ["level"])

        self._report("Nodes", len(to_create), len(to_update), len(wanted))
        return {node.code: node for node in Node.objects.filter(code__in=wanted)}

    def _import_edges(self, raw_edges, nodes):
        missing = sorted(
            {c for e in raw_edges for c in (e["source"], e["target"]) if c not in nodes}
        )
        if missing:
            raise CommandError(f"Edge endpoints with no matching node: {', '.join(missing)}.")

        existing = {(e.a_id, e.b_id): e for e in Edge.objects.all()}
        pending = {}
        to_create = []
        to_update = []

        for e in raw_edges:
            directed = bool(e["directed"])
            a, b = nodes[e["source"]], nodes[e["target"]]
            if not directed and a.pk > b.pk:
                a, b = b, a
            key = (a.pk, b.pk)

            if pending.get(key, directed) != directed:
                raise CommandError(f"{a.code}/{b.code} appears twice with different direction.")
            if key in pending:
                continue
            pending[key] = directed

            row = existing.get(key)
            if row is not None:
                if row.directed != directed:
                    row.directed = directed
                    to_update.append(row)
                continue
            if (b.pk, a.pk) in existing:
                raise CommandError(
                    f"{a.code} -> {b.code} is already stored as {b.code} -> {a.code}; "
                    f"remove the stale edge before importing."
                )
            to_create.append(Edge(a=a, b=b, directed=directed))

        Edge.objects.bulk_create(to_create)
        Edge.objects.bulk_update(to_update, ["directed"])

        self._report("Edges", len(to_create), len(to_update), len(pending))

    def _report(self, label, created, updated, total):
        self.stdout.write(
            self.style.SUCCESS(
                f"{label}: {created} created, {updated} updated, "
                f"{total - created - updated} unchanged ({total} total)."
            )
        )
