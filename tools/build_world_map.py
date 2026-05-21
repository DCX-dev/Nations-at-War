#!/usr/bin/env python3
"""Rebuild world_map_data.npz from Natural Earth country borders."""

from __future__ import annotations

import colorsys
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape
from shapely.prepared import prep
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "data" / "ne_110m_admin_0_countries.geojson"
OUT = ROOT / "world_map_data.npz"
URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_110m_admin_0_countries.geojson"
)
W, H = 360, 180
# Not playable / not land nations on Natural Earth
SKIP_NAMES = frozenset({"Antarctica", "Seven seas (open ocean)"})


def ensure_geojson() -> None:
    GEO.parent.mkdir(parents=True, exist_ok=True)
    if GEO.exists() and GEO.stat().st_size > 1000:
        return
    print("Downloading Natural Earth GeoJSON...")
    subprocess.run(["curl", "-fsSL", "-o", str(GEO), URL], check=True)


def color_for(i: int) -> tuple[int, int, int]:
    h = (i * 137.508) % 360
    s = 0.55 + (i % 5) * 0.06
    v = 0.72 + (i % 3) * 0.08
    r, g, b = colorsys.hsv_to_rgb(h / 360, min(s, 1), min(v, 1))
    return int(r * 255), int(g * 255), int(b * 255)


def main() -> None:
    try:
        from shapely.geometry import shape as _shape  # noqa: F401
    except ImportError:
        print("Install shapely first: pip install shapely", file=sys.stderr)
        sys.exit(1)

    ensure_geojson()
    data = json.loads(GEO.read_text())

    features: list[tuple[str, object]] = []
    for ftr in data["features"]:
        props = ftr.get("properties") or {}
        name = props.get("NAME") or props.get("ADMIN") or "Unknown"
        if name in SKIP_NAMES:
            continue
        geom = ftr.get("geometry")
        if not geom:
            continue
        try:
            g = shape(geom)
            if not g.is_empty:
                features.append((name, g))
        except Exception:
            pass

    features.sort(key=lambda x: x[1].area, reverse=True)
    geoms = [g for _, g in features]
    prepared = [prep(g) for g in geoms]
    tree = STRtree(geoms)
    print(f"Rasterizing {len(features)} countries to {W}x{H}...")

    grid = np.zeros((H, W), dtype=np.uint16)
    for y in range(H):
        lat = 90.0 - (y + 0.5) * (180.0 / H)
        for x in range(W):
            lon = -180.0 + (x + 0.5) * (360.0 / W)
            pt = Point(lon, lat)
            for idx in tree.query(pt):
                if prepared[idx].contains(pt):
                    grid[y, x] = idx + 1
                    break

    names = [features[i][0] for i in range(len(features))]
    colors = np.array([color_for(i + 1) for i in range(len(features))], dtype=np.uint8)
    np.savez_compressed(OUT, grid=grid, names=np.array(names, dtype=object), colors=colors)
    land = int((grid > 0).sum())
    print(f"Done: {OUT} ({OUT.stat().st_size / 1024:.1f} KB), land cells={land}")


if __name__ == "__main__":
    main()
