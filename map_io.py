"""Save and load custom maps."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from nation import Nation, NationRegistry
from paths import app_root
from world_map import WorldMap

MAP_EXT = ".naw"
MAPS_DIR_NAME = "maps"


def maps_directory() -> Path:
    d = app_root() / MAPS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name.strip())
    cleaned = cleaned.replace(" ", "_")[:48] or "custom_map"
    if not cleaned.endswith(MAP_EXT):
        cleaned += MAP_EXT
    return cleaned


def list_saved_maps() -> list[str]:
    return sorted(p.stem for p in maps_directory().glob(f"*{MAP_EXT}"))


def save_custom_map(
    filename: str, world: WorldMap, registry: NationRegistry
) -> Path:
    path = maps_directory() / _safe_filename(filename)
    nations = []
    for n in registry.nations.values():
        nations.append(
            {
                "id": n.id,
                "name": n.name,
                "color": list(n.color),
                "capital_x": n.capital_x,
                "capital_y": n.capital_y,
            }
        )
    payload = {
        "version": 1,
        "width": world.width,
        "height": world.height,
        "grid": world.grid.tolist(),
        "nations": nations,
        "next_id": registry._next_id,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def load_custom_map(filename: str) -> tuple[WorldMap, NationRegistry]:
    path = maps_directory() / _safe_filename(filename)
    if not path.is_file():
        raise FileNotFoundError(f"No saved map: {path.name}")

    data = json.loads(path.read_text(encoding="utf-8"))
    w = int(data["width"])
    h = int(data["height"])
    world = WorldMap(width=w, height=h)
    world.grid = np.array(data["grid"], dtype=np.int32)

    registry = NationRegistry()
    registry._next_id = int(data.get("next_id", 1))
    for nd in data["nations"]:
        nation = Nation(
            id=int(nd["id"]),
            name=str(nd["name"]),
            color=tuple(int(c) for c in nd["color"]),
            capital_x=int(nd.get("capital_x", -1)),
            capital_y=int(nd.get("capital_y", -1)),
        )
        registry.nations[nation.id] = nation
        registry._next_id = max(registry._next_id, nation.id + 1)

    world.assign_capitals(registry)
    return world, registry
