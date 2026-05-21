"""Autonomous nation warfare simulation."""

from __future__ import annotations

import random

from constants import NEUTRAL_LAND, START_YEAR, TICKS_PER_YEAR
from nation import NationRegistry
from world_map import WorldMap


class WarSimulator:
    def __init__(self, world: WorldMap, registry: NationRegistry) -> None:
        self.world = world
        self.registry = registry
        self.tick = 0
        self.events: list[str] = []
        self.max_events = 14
        self._counts: dict[int, int] = {}
        self.prepare_for_war()

    def prepare_for_war(self) -> None:
        """All nations start at war with capitals assigned."""
        self.world.assign_capitals(self.registry)
        counts = self._sync_counts()
        for nation in self.registry.nations.values():
            nation.at_war = True
            nation.alive = counts.get(nation.id, 0) > 0
            nation.aggression = 1.8 + random.uniform(0.0, 0.7)
            nation.reset_military(counts.get(nation.id, 1))
        living = len([n for n in self.registry.nations.values() if n.alive])
        self._log(f"World war! {living} nations — capture red capitals to destroy them!")

    def _log(self, msg: str) -> None:
        self.events.insert(0, msg)
        self.events = self.events[: self.max_events]

    def _sync_counts(self) -> dict[int, int]:
        self._counts = self.world.territory_counts()
        return self._counts

    def refresh_military(self) -> None:
        counts = self._sync_counts()
        for nation in self.registry.living():
            tc = counts.get(nation.id, 0)
            if tc == 0:
                nation.alive = False
                continue
            nation.military += tc * 0.08
            nation.military = min(nation.military, tc * 4 + 200)

    def eliminate_empty(self) -> None:
        counts = self._counts
        for nation in list(self.registry.living()):
            if counts.get(nation.id, 0) <= 0:
                if nation.alive:
                    nation.alive = False
                    nation.at_war = False
                    self._log(f"{nation.name} has been conquered!")

    def collapse_nation(self, victim_id: int, capturer_id: int | None) -> None:
        """Capital fallen — nation dies, land becomes unclaimed."""
        victim = self.registry.get(victim_id)
        if not victim or not victim.alive:
            return
        capturer = self.registry.get(capturer_id) if capturer_id else None
        land = self.world.collapse_nation(victim_id)
        victim.alive = False
        victim.at_war = False
        victim.capital_x = victim.capital_y = -1
        self._sync_counts()
        if capturer:
            self._log(
                f"{capturer.name} captured {victim.name}'s capital! "
                f"{land} tiles up for grabs!"
            )
        else:
            self._log(f"{victim.name} fell! {land} tiles unclaimed!")

    def _check_capital_captured(self, x: int, y: int, new_owner: int) -> None:
        victim_id = self.world.nation_at_capital(self.registry, x, y)
        if victim_id is not None and victim_id != new_owner:
            self.collapse_nation(victim_id, new_owner)

    def step(self, intensity: float = 1.0) -> None:
        self.tick += 1
        self.world.tick_flash()
        counts = self._sync_counts()
        living = [n for n in self.registry.living() if counts.get(n.id, 0) > 0]
        if len(living) <= 1:
            if len(living) == 1:
                self._log(f"{living[0].name} rules the world!")
            return

        at_war = [n for n in living if n.at_war]
        random.shuffle(at_war)
        battles = min(40, max(6, int(len(at_war) * 0.35 * intensity)))

        for attacker in at_war[:battles]:
            if not attacker.alive or not attacker.at_war:
                continue
            front = self.world.random_front_cell(attacker.id, samples=72)
            if not front:
                continue
            ax, ay = front
            g = self.world.grid
            targets: set[int] = set()
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nx, ny = ax + dx, ay + dy
                if 0 <= nx < self.world.width and 0 <= ny < self.world.height:
                    v = int(g[ny, nx])
                    if v == NEUTRAL_LAND:
                        targets.add(NEUTRAL_LAND)
                    elif v > 0 and v != attacker.id:
                        targets.add(v)

            if not targets:
                continue

            if NEUTRAL_LAND in targets and random.random() < 0.35:
                target_id = NEUTRAL_LAND
                defender = None
            else:
                enemies = [t for t in targets if t > 0]
                if not enemies:
                    target_id = NEUTRAL_LAND
                    defender = None
                else:
                    if random.random() < 0.55:
                        target_id = min(enemies, key=lambda e: counts.get(e, 999999))
                    else:
                        cap_targets = [
                            e
                            for e in enemies
                            if (dn := self.registry.get(e))
                            and dn.capital_x >= 0
                        ]
                        target_id = random.choice(cap_targets or enemies)
                    defender = self.registry.get(target_id)

            if defender and (not defender.alive or not defender.at_war):
                continue

            a_count = counts.get(attacker.id, 1)
            d_count = counts.get(target_id, 1) if target_id > 0 else 20
            a_str = attacker.combat_strength(a_count) * attacker.aggression
            d_str = (
                defender.combat_strength(d_count)
                if defender
                else 15 + random.uniform(0, 10)
            )

            if a_str > d_str * random.uniform(0.7, 1.05):
                toward = None
                if defender and defender.capital_x >= 0:
                    toward = (defender.capital_x, defender.capital_y)
                push = 3 + int((a_str - d_str) / 25) + random.randint(0, 2)
                push = min(10, max(3, push))
                taken = self.world.push_front(
                    attacker.id,
                    target_id,
                    ax,
                    ay,
                    push,
                    toward=toward,
                )
                for tx, ty in taken:
                    self._check_capital_captured(tx, ty, attacker.id)
                if defender:
                    defender.military -= len(taken) * 2
                attacker.military += len(taken)
            elif defender and d_str > a_str * 1.15:
                attacker.military *= 0.92

        if self.tick % 15 == 0:
            self.refresh_military()
        self._after_battles()
        self.eliminate_empty()

    def _after_battles(self) -> None:
        self._sync_counts()

    def god_attack_to_death(self, attacker_id: int, victim_id: int) -> None:
        attacker = self.registry.get(attacker_id)
        victim = self.registry.get(victim_id)
        if not attacker or not victim or not victim.alive:
            return
        if attacker_id == victim_id:
            self.collapse_nation(victim_id, None)
            return

        if victim.capital_x >= 0:
            self.world.transfer_cell(victim.capital_x, victim.capital_y, attacker_id)
            self.collapse_nation(victim_id, attacker_id)
        else:
            transferred = self.world.annex_all(victim_id, attacker_id)
            victim.alive = False
            victim.military = 0
            attacker.military += transferred * 0.5
            self._sync_counts()
            self._log(f"{attacker.name} annihilated {victim.name}!")

    def god_destroy(self, nation_id: int) -> None:
        nation = self.registry.get(nation_id)
        if not nation:
            return
        self.collapse_nation(nation_id, None)

    def leader(self) -> tuple[str, int]:
        counts = self._counts or self._sync_counts()
        if not counts:
            return "None", 0
        best = max(counts.items(), key=lambda x: x[1])
        name = self.registry.get(best[0])
        return (name.name if name else "?"), best[1]

    def nations_alive_count(self) -> int:
        return len([n for n in self.registry.nations.values() if n.alive])

    def current_year(self) -> int:
        return START_YEAR + self.tick // TICKS_PER_YEAR
