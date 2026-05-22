"""Grid-based world map with territory ownership."""

from __future__ import annotations

import random
from collections import deque

import numpy as np

from constants import BORDER_DARKEN, GRID_H, GRID_W, LAND_EMPTY, NEUTRAL_LAND, OCEAN, PUSH_FLASH
from nation import NationRegistry
from real_capitals import capital_lonlat_for_name, lonlat_to_grid


class WorldMap:
    """Each cell: 0 = ocean, -1 = unclaimed land, positive int = nation id."""

    def __init__(self, width: int = GRID_W, height: int = GRID_H) -> None:
        self.width = width
        self.height = height
        self.grid = np.zeros((height, width), dtype=np.int32)
        self.version = 0
        self.flash_cells: dict[tuple[int, int], int] = {}

    def _touch(self) -> None:
        self.version += 1

    def clear(self) -> None:
        self.grid.fill(0)
        self.flash_cells.clear()
        self._touch()

    def _snap_capital_to_territory(
        self, nation_id: int, target_x: int, target_y: int
    ) -> tuple[int, int]:
        ys, xs = np.where(self.grid == nation_id)
        if len(xs) == 0:
            return -1, -1
        dist = (xs - target_x) ** 2 + (ys - target_y) ** 2
        i = int(dist.argmin())
        return int(xs[i]), int(ys[i])

    def assign_capitals(self, registry: NationRegistry) -> None:
        """Place capitals at real-world cities when known, else territory core."""
        for nation in registry.nations.values():
            ys, xs = np.where(self.grid == nation.id)
            if len(xs) == 0:
                nation.capital_x = nation.capital_y = -1
                continue

            lonlat = capital_lonlat_for_name(nation.name)
            if lonlat:
                tx, ty = lonlat_to_grid(
                    lonlat[0], lonlat[1], self.width, self.height
                )
                cx, cy = self._snap_capital_to_territory(nation.id, tx, ty)
            else:
                cx, cy = int(xs.mean()), int(ys.mean())
                dist = (xs - cx) ** 2 + (ys - cy) ** 2
                i = int(dist.argmin())
                cx, cy = int(xs[i]), int(ys[i])

            nation.capital_x, nation.capital_y = cx, cy
            self.grid[cy, cx] = nation.id

    def nation_at_capital(self, registry: NationRegistry, x: int, y: int) -> int | None:
        for nation in registry.nations.values():
            if not nation.alive:
                continue
            if nation.capital_x == x and nation.capital_y == y:
                return nation.id
        return None

    def set_cell(self, x: int, y: int, nation_id: int, *, flash: bool = True) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            if int(self.grid[y, x]) != nation_id:
                self.grid[y, x] = nation_id
                if flash and nation_id > 0:
                    self.flash_cells[(x, y)] = 8
                self._touch()

    def get_cell(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return int(self.grid[y, x])
        return 0

    def paint_disk(self, cx: int, cy: int, radius: int, nation_id: int) -> None:
        changed = False
        for y in range(max(0, cy - radius), min(self.height, cy + radius + 1)):
            for x in range(max(0, cx - radius), min(self.width, cx + radius + 1)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= radius * radius:
                    if int(self.grid[y, x]) != nation_id:
                        self.grid[y, x] = nation_id
                        changed = True
        if changed:
            self._touch()

    def flood_fill(self, x: int, y: int, nation_id: int) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        target = int(self.grid[y, x])
        if target == nation_id:
            return
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if not (0 <= cx < self.width and 0 <= cy < self.height):
                continue
            if int(self.grid[cy, cx]) != target:
                continue
            self.grid[cy, cx] = nation_id
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        self._touch()

    def territory_counts(self) -> dict[int, int]:
        flat = self.grid.ravel()
        if flat.size == 0:
            return {}
        positive = flat[flat > 0]
        if positive.size == 0:
            return {}
        bc = np.bincount(positive)
        return {i: int(c) for i, c in enumerate(bc) if c > 0}

    def neighbors_of(self, x: int, y: int) -> set[int]:
        ids: set[int] = set()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.width and 0 <= ny < self.height:
                v = int(self.grid[ny, nx])
                if v > 0:
                    ids.add(v)
        return ids

    def cell_has_foreign_neighbor(self, x: int, y: int, owner: int) -> bool:
        g = self.grid
        h, w = self.height, self.width
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h:
                v = int(g[ny, nx])
                if v != owner and (v > 0 or v == NEUTRAL_LAND):
                    return True
        return False

    def random_front_cell(
        self, nation_id: int, samples: int = 64
    ) -> tuple[int, int] | None:
        """Border with enemy nations or unclaimed land."""
        g = self.grid
        h, w = self.height, self.width
        for _ in range(samples):
            x = random.randrange(w)
            y = random.randrange(h)
            if int(g[y, x]) != nation_id:
                continue
            if self.cell_has_foreign_neighbor(x, y, nation_id):
                return x, y
        return None

    def transfer_cell(self, x: int, y: int, new_owner: int) -> int:
        """Returns previous owner id at cell."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return 0
        old = int(self.grid[y, x])
        if old != new_owner:
            self.grid[y, x] = new_owner
            if new_owner > 0:
                self.flash_cells[(x, y)] = 10
            self._touch()
        return old

    def push_front(
        self,
        attacker_id: int,
        target_id: int,
        start_x: int,
        start_y: int,
        strength: int,
        toward: tuple[int, int] | None = None,
    ) -> list[tuple[int, int]]:
        """Conquer a chunk of enemy/neutral cells from the border — visible push."""
        g = self.grid
        h, w = self.height, self.width
        taken: list[tuple[int, int]] = []
        valid = {target_id, NEUTRAL_LAND}

        def priority_neighbors(cx: int, cy: int) -> list[tuple[int, int]]:
            opts = [
                (cx + 1, cy),
                (cx - 1, cy),
                (cx, cy + 1),
                (cx, cy - 1),
                (cx + 1, cy + 1),
                (cx - 1, cy - 1),
                (cx + 1, cy - 1),
                (cx - 1, cy + 1),
            ]
            if toward:
                tx, ty = toward
                opts.sort(key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)
            return opts

        seeds: list[tuple[int, int]] = []
        for nx, ny in priority_neighbors(start_x, start_y):
            if 0 <= nx < w and 0 <= ny < h and int(g[ny, nx]) in valid:
                seeds.append((nx, ny))

        queue: deque[tuple[int, int]] = deque(seeds)
        seen = set(seeds)

        while queue and len(taken) < strength:
            cx, cy = queue.popleft()
            if int(g[cy, cx]) not in valid:
                continue
            self.transfer_cell(cx, cy, attacker_id)
            taken.append((cx, cy))
            for nx, ny in priority_neighbors(cx, cy):
                if (nx, ny) in seen or not (0 <= nx < w and 0 <= ny < h):
                    continue
                if int(g[ny, nx]) in valid:
                    seen.add((nx, ny))
                    queue.append((nx, ny))
        return taken

    def collapse_nation(self, nation_id: int) -> int:
        """Nation destroyed — territory becomes unclaimed land others can seize."""
        mask = self.grid == nation_id
        count = int(mask.sum())
        if count:
            self.grid[mask] = NEUTRAL_LAND
            self._touch()
        return count

    def annex_all(self, from_id: int, to_id: int) -> int:
        mask = self.grid == from_id
        count = int(mask.sum())
        if count:
            self.grid[mask] = to_id
            for y, x in zip(*np.where(mask)):
                self.flash_cells[(int(x), int(y))] = 6
            self._touch()
        return count

    def wipe_nation(self, nation_id: int) -> None:
        if (self.grid == nation_id).any():
            self.grid[self.grid == nation_id] = NEUTRAL_LAND
            self._touch()

    def tick_flash(self) -> None:
        expired = [k for k, v in self.flash_cells.items() if v <= 1]
        for k in expired:
            del self.flash_cells[k]
        for k in list(self.flash_cells.keys()):
            self.flash_cells[k] -= 1

    def screen_to_grid(
        self, sx: int, sy: int, offset_x: int, offset_y: int, cell_size: int
    ) -> tuple[int, int] | None:
        gx = (sx - offset_x) // cell_size
        gy = (sy - offset_y) // cell_size
        if 0 <= gx < self.width and 0 <= gy < self.height:
            return gx, gy
        return None

    def to_rgb_array(self, registry: NationRegistry) -> np.ndarray:
        """Vectorized RGB with borders and battle flashes."""
        max_id = max((n.id for n in registry.nations.values()), default=0)
        lut = np.zeros((max_id + 1, 3), dtype=np.uint8)
        lut[0] = OCEAN
        for nation in registry.nations.values():
            if nation.alive:
                lut[nation.id] = nation.color
            else:
                lut[nation.id] = tuple(max(20, c // 4) for c in nation.color)

        g = self.grid
        rgb = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        ocean = g == 0
        neutral = g == NEUTRAL_LAND
        land = g > 0
        rgb[ocean] = OCEAN
        rgb[neutral] = LAND_EMPTY
        if land.any():
            rgb[land] = lut[g[land]]

        border = np.zeros(g.shape, dtype=bool)
        border[1:, :] |= g[1:, :] != g[:-1, :]
        border[:-1, :] |= g[:-1, :] != g[1:, :]
        border[:, 1:] |= g[:, 1:] != g[:, :-1]
        border[:, :-1] |= g[:, :-1] != g[:, 1:]
        border &= g != 0
        rgb[border] = (rgb[border] * BORDER_DARKEN).astype(np.uint8)

        for (fx, fy), _ttl in self.flash_cells.items():
            if 0 <= fx < self.width and 0 <= fy < self.height:
                base = rgb[fy, fx].astype(np.int16)
                rgb[fy, fx] = np.minimum(255, base + np.array(PUSH_FLASH) // 2).astype(np.uint8)

        return rgb
