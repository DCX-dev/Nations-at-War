"""Per-nation AI personalities — each country behaves differently."""

from __future__ import annotations

import random
from dataclasses import dataclass

from nation import Nation, NationRegistry


@dataclass
class NationAI:
    style: str
    aggression: float
    neutral_bias: float
    capital_focus: float
    push_mult: float
    battle_weight: float
    overextend: float


STYLES = (
    "expansionist",
    "opportunist",
    "imperialist",
    "defensive",
    "raider",
    "isolationist",
    "skirmisher",
    "conqueror",
)

_STYLE_BASE: dict[str, dict[str, float]] = {
    "expansionist": {
        "aggression": 2.2,
        "neutral_bias": 0.55,
        "capital_focus": 0.15,
        "push_mult": 1.25,
        "battle_weight": 1.15,
        "overextend": 0.85,
    },
    "opportunist": {
        "aggression": 1.9,
        "neutral_bias": 0.35,
        "capital_focus": 0.35,
        "push_mult": 1.0,
        "battle_weight": 1.0,
        "overextend": 1.0,
    },
    "imperialist": {
        "aggression": 2.4,
        "neutral_bias": 0.2,
        "capital_focus": 0.25,
        "push_mult": 1.1,
        "battle_weight": 0.85,
        "overextend": 0.7,
    },
    "defensive": {
        "aggression": 1.2,
        "neutral_bias": 0.25,
        "capital_focus": 0.1,
        "push_mult": 0.85,
        "battle_weight": 0.65,
        "overextend": 1.2,
    },
    "raider": {
        "aggression": 2.0,
        "neutral_bias": 0.3,
        "capital_focus": 0.75,
        "push_mult": 1.15,
        "battle_weight": 0.9,
        "overextend": 1.0,
    },
    "isolationist": {
        "aggression": 0.9,
        "neutral_bias": 0.15,
        "capital_focus": 0.05,
        "push_mult": 0.7,
        "battle_weight": 0.45,
        "overextend": 1.3,
    },
    "skirmisher": {
        "aggression": 1.6,
        "neutral_bias": 0.4,
        "capital_focus": 0.2,
        "push_mult": 0.95,
        "battle_weight": 1.25,
        "overextend": 1.05,
    },
    "conqueror": {
        "aggression": 2.5,
        "neutral_bias": 0.45,
        "capital_focus": 0.5,
        "push_mult": 1.35,
        "battle_weight": 1.05,
        "overextend": 0.75,
    },
}


def _rng_for(name: str) -> random.Random:
    return random.Random(hash(name) & 0xFFFFFFFF)


def generate_ai(name: str, territory: int) -> NationAI:
    r = _rng_for(name)
    style = r.choice(STYLES)

    if territory > 1400:
        style = r.choice(["defensive", "isolationist", "imperialist", "defensive"])
    elif territory > 900:
        style = r.choice(["defensive", "opportunist", "imperialist", "skirmisher"])
    elif territory < 40:
        style = r.choice(["raider", "expansionist", "conqueror", "skirmisher"])
    elif territory < 120:
        style = r.choice(["expansionist", "raider", "opportunist", "conqueror"])

    base = _STYLE_BASE[style]
    jitter = lambda lo, hi: r.uniform(lo, hi)

    return NationAI(
        style=style,
        aggression=base["aggression"] * jitter(0.85, 1.15),
        neutral_bias=min(0.9, base["neutral_bias"] * jitter(0.7, 1.3)),
        capital_focus=min(0.95, base["capital_focus"] * jitter(0.7, 1.3)),
        push_mult=base["push_mult"] * jitter(0.85, 1.2),
        battle_weight=base["battle_weight"] * jitter(0.8, 1.2),
        overextend=base["overextend"] * jitter(0.9, 1.1),
    )


def apply_ai_to_nation(nation: Nation, ai: NationAI, territory: int) -> None:
    nation.ai_style = ai.style
    nation.aggression = ai.aggression
    nation.neutral_bias = ai.neutral_bias
    nation.capital_focus = ai.capital_focus
    nation.push_mult = ai.push_mult
    nation.battle_weight = ai.battle_weight
    nation.overextend = ai.overextend
    nation.reset_military(territory)


def assign_all_personalities(registry: NationRegistry, counts: dict[int, int]) -> None:
    for nation in registry.nations.values():
        tc = counts.get(nation.id, 0)
        if tc <= 0:
            continue
        ai = generate_ai(nation.name, tc)
        apply_ai_to_nation(nation, ai, tc)


def pick_target(
    attacker: Nation,
    enemies: list[int],
    counts: dict[int, int],
    registry: NationRegistry,
    rng: random.Random,
) -> int | None:
    if not enemies:
        return None

    style = getattr(attacker, "ai_style", "opportunist")
    cap_focus = getattr(attacker, "capital_focus", 0.3)

    cap_enemies = [
        e
        for e in enemies
        if (d := registry.get(e)) and d.capital_x >= 0 and counts.get(e, 0) > 0
    ]

    if style == "raider" and cap_enemies and rng.random() < 0.7:
        return rng.choice(cap_enemies)

    if style == "imperialist":
        return max(enemies, key=lambda e: counts.get(e, 0))

    if style == "opportunist":
        return min(enemies, key=lambda e: counts.get(e, 999999))

    if style == "conqueror" and cap_enemies and rng.random() < 0.5:
        return rng.choice(cap_enemies)

    if style == "defensive":
        return min(enemies, key=lambda e: counts.get(e, 999999))

    if style == "expansionist":
        return min(enemies, key=lambda e: counts.get(e, 999999))

    if cap_enemies and rng.random() < cap_focus:
        return rng.choice(cap_enemies)

    return rng.choice(enemies)


def combat_multiplier(attacker: Nation, territory: int) -> float:
    """Large empires fight worse far from core — stops one nation always winning."""
    over = getattr(attacker, "overextend", 1.0)
    if territory > 2000:
        return over * 0.72
    if territory > 1200:
        return over * 0.82
    if territory > 700:
        return over * 0.92
    return over


def push_strength(attacker: Nation, advantage: float, rng: random.Random) -> int:
    mult = getattr(attacker, "push_mult", 1.0)
    style = getattr(attacker, "ai_style", "opportunist")
    base = 3 + int(advantage / 22) + rng.randint(0, 2)
    if style == "expansionist":
        base += 1
    if style == "isolationist":
        base -= 1
    return int(min(12, max(2, base * mult)))
