"""Deterministic colours for the 48 L1 diamond start nodes.

The SPA map is not the Django graph, so both sides compute the same
``L1_{4k}`` → hex mapping instead of sharing a table of node rows.
"""

from __future__ import annotations

import re

START_COUNT = 48
START_ID_RE = re.compile(r"^L1_(\d+)$")

# 48 even hues (HLS L=0.48 S=0.72). Keep in sync with frontend/src/lib/startColors.js.
START_COLORS = [
    "#d92121",
    "#d9d921",
    "#21d921",
    "#21d9d9",
    "#2121d9",
    "#d921d9",
    "#d93721",
    "#c3d921",
    "#21d937",
    "#21c3d9",
    "#3721d9",
    "#d921c3",
    "#d94d21",
    "#add921",
    "#21d94d",
    "#21add9",
    "#4d21d9",
    "#d921ad",
    "#d96321",
    "#96d921",
    "#21d963",
    "#2196d9",
    "#6321d9",
    "#d92196",
    "#d97921",
    "#80d921",
    "#21d979",
    "#2180d9",
    "#7921d9",
    "#d92180",
    "#d98f21",
    "#6ad921",
    "#21d98f",
    "#216ad9",
    "#8f21d9",
    "#d9216a",
    "#d9a521",
    "#54d921",
    "#21d9a5",
    "#2154d9",
    "#a521d9",
    "#d92154",
    "#d9bb21",
    "#3ed921",
    "#21d9bb",
    "#213ed9",
    "#bb21d9",
    "#d9213e",
]


def start_index(node_id: str) -> int | None:
    match = START_ID_RE.fullmatch(node_id)
    if match is None:
        return None
    number = int(match.group(1))
    if number % 4 != 0:
        return None
    index = number // 4
    if index < 0 or index >= START_COUNT:
        return None
    return index


def color_for_start(node_id: str) -> str | None:
    index = start_index(node_id)
    if index is None:
        return None
    return START_COLORS[index]
