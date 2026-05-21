"""Default world map from real country borders (Natural Earth 110m)."""

from __future__ import annotations

import numpy as np

from nation import NationRegistry
from paths import app_root
from world_map import WorldMap

_DATA_FILE = app_root() / "world_map_data.npz"


def build_default_world() -> tuple[WorldMap, NationRegistry]:
    if not _DATA_FILE.exists():
        raise FileNotFoundError(
            f"Missing {_DATA_FILE.name}. Run: python tools/build_world_map.py"
        )

    raw = np.load(_DATA_FILE, allow_pickle=True)
    grid = raw["grid"].astype(np.int32)
    names = list(raw["names"])
    colors = raw["colors"]

    height, width = grid.shape
    world = WorldMap(width=width, height=height)
    world.grid = grid.copy()

    registry = NationRegistry()
    for i, name in enumerate(names):
        rgb = tuple(int(c) for c in colors[i])
        registry.create(str(name), rgb)

    world.assign_capitals(registry)
    return world, registry


def editor_palette() -> list[tuple[str, tuple[int, int, int]]]:
    """Colors for custom map editor."""
    return [
        ("Nation A", (200, 60, 60)),
        ("Nation B", (60, 120, 200)),
        ("Nation C", (60, 180, 80)),
        ("Nation D", (220, 180, 50)),
        ("Nation E", (180, 80, 200)),
        ("Nation F", (80, 200, 200)),
        ("Nation G", (240, 120, 80)),
        ("Nation H", (120, 120, 180)),
    ]
