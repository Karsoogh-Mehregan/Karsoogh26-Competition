"""Give every toll node that already exists a Minesweeper board.

A toll gate takes no question and no occupancy, so its board is the only way
across it; without one the roads out of the gate never open and rings 4 and up
stay unreachable. Existing installs already hold the nodes, so they are filled
in here rather than waiting for the next `import_graph`.

Idempotent and additive: a gate that already has a board keeps its difficulty
and its enabled flag. Nothing is deleted going backwards either — a board an
organiser configured is not this migration's to remove, and dropping the row
would take the attempt history hanging off it.
"""

from django.db import migrations

DEFAULTS = {"C34": "easy", "C45": "medium"}
FALLBACK = "easy"


def seed_toll_boards(apps, schema_editor):
    Node = apps.get_model("game", "Node")
    Settings = apps.get_model("minesweeper", "MinesweeperSettings")
    DifficultyConfig = apps.get_model("minesweeper", "DifficultyConfig")

    configured = set(DifficultyConfig.objects.values_list("key", flat=True))
    if not configured:
        # 0007 seeds these; an operator who deleted them all gets no boards
        # rather than an FK failure.
        return

    existing = set(Settings.objects.values_list("node_id", flat=True))
    rows = []
    for node in Node.objects.filter(level_id="toll").order_by("code"):
        if node.pk in existing:
            continue
        wanted = DEFAULTS.get(node.code.split("_", 1)[0].upper(), FALLBACK)
        if wanted not in configured:
            wanted = min(configured)
        rows.append(Settings(node_id=node.pk, difficulty_id=wanted, enabled=True))
    Settings.objects.bulk_create(rows)


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0013_level_attempt_ttl"),
        ("minesweeper", "0007_difficultyconfig"),
    ]

    operations = [migrations.RunPython(seed_toll_boards, migrations.RunPython.noop)]
