"""Nation model for map simulation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class Nation:
    id: int
    name: str
    color: tuple[int, int, int]
    alive: bool = True
    military: float = 100.0
    aggression: float = 2.0
    at_war: bool = True
    capital_x: int = -1
    capital_y: int = -1

    def reset_military(self, territory_count: int) -> None:
        self.military = max(50.0, territory_count * 2.5 + random.uniform(-10, 10))

    def combat_strength(self, territory_count: int) -> float:
        if not self.alive:
            return 0.0
        return self.military + territory_count * 1.8 + random.uniform(0, 15)


@dataclass
class NationRegistry:
    nations: dict[int, Nation] = field(default_factory=dict)
    _next_id: int = 1

    def create(self, name: str, color: tuple[int, int, int]) -> Nation:
        n = Nation(id=self._next_id, name=name, color=color)
        self.nations[n.id] = n
        self._next_id += 1
        return n

    def get(self, nation_id: int) -> Nation | None:
        return self.nations.get(nation_id)

    def living(self) -> list[Nation]:
        return [n for n in self.nations.values() if n.alive]

    def rename(self, nation_id: int, name: str) -> None:
        if n := self.get(nation_id):
            n.name = name[:32]

    def kill(self, nation_id: int) -> None:
        if n := self.get(nation_id):
            n.alive = False
            n.military = 0
