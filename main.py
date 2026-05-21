#!/usr/bin/env python3
"""Nations at War — world war map simulator."""

from __future__ import annotations

import os
import sys
from enum import Enum, auto
from pathlib import Path


def _reexec_with_venv_on_py314() -> None:
    """Python 3.14 breaks pygame.font; re-launch with project venv when available."""
    if sys.version_info < (3, 14):
        return
    root = Path(__file__).resolve().parent
    venv_py = root / ".venv" / "bin" / "python"
    if not venv_py.is_file():
        return
    try:
        if Path(sys.executable).resolve() == venv_py.resolve():
            return
    except OSError:
        return
    script = str(Path(__file__).resolve())
    os.execv(str(venv_py), [str(venv_py), script, *sys.argv[1:]])


_reexec_with_venv_on_py314()

import pygame

from constants import (
    CAPITAL_COLOR,
    CAPITAL_RING,
    CELL_SIZE,
    GRID_H,
    GRID_W,
    MAP_AREA_H,
    MAP_AREA_W,
    MAP_OFFSET_X,
    MAP_OFFSET_Y,
    MAP_PIXEL_SCALE,
    SIM_SPEEDS,
    WINDOW_H,
    WINDOW_W,
    BG,
    DANGER,
    PANEL_BORDER,
    SUCCESS,
    TEXT,
    TEXT_DIM,
    OCEAN,
)
from default_world import build_default_world, editor_palette
from nation import NationRegistry
from simulation import WarSimulator
from ui import Button, draw_panel, draw_title_screen, load_fonts
from world_map import WorldMap


class GameState(Enum):
    MENU = auto()
    SIM_DEFAULT = auto()
    EDITOR = auto()
    SIM_CUSTOM = auto()


class NationsAtWar:
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Nations at War")
        self.clock = pygame.time.Clock()
        self.fonts = load_fonts()
        if self.fonts.get("_bitmap"):
            pygame.display.set_caption("Nations at War (bitmap fonts)")
        self.state = GameState.MENU
        self.world: WorldMap | None = None
        self.registry: NationRegistry | None = None
        self.sim: WarSimulator | None = None
        self.paused = False
        self.speed_idx = 2
        self.accum = 0.0
        self.selected_nation: int | None = None
        self.god_mode = True
        self.editor_brush = 8
        self.editor_nation_idx = 0
        self.editor_registry = NationRegistry()
        self.rename_buffer = ""
        self.editing_name = False
        self._map_surface: pygame.Surface | None = None
        self._buttons: list[Button] = []
        self._last_redraw_tick = -1
        self._attack_source: int | None = None
        self._map_dirty = True
        self._map_render_version = -1
        self._map_redraw_timer = 0.0
        self._display_surface: pygame.Surface | None = None
        self._cached_counts: dict[int, int] = {}
        self._setup_menu_buttons()

    def _setup_menu_buttons(self) -> None:
        cx = WINDOW_W // 2
        bw, bh = 320, 52
        y0 = 320
        self._buttons = [
            Button(
                pygame.Rect(cx - bw // 2, y0, bw, bh),
                "Default World Map",
                self.fonts["large"],
                primary=True,
            ),
            Button(
                pygame.Rect(cx - bw // 2, y0 + 70, bw, bh),
                "Create Custom Map",
                self.fonts["large"],
            ),
            Button(
                pygame.Rect(cx - bw // 2, y0 + 140, bw, bh),
                "Quit",
                self.fonts["med"],
            ),
        ]

    def _cell_size(self) -> int:
        return max(3, min(MAP_AREA_W // GRID_W, MAP_AREA_H // GRID_H))

    def _mark_map_dirty(self) -> None:
        self._map_dirty = True

    def _rebuild_map_surface(self) -> None:
        if not self.world or not self.registry:
            return
        rgb = self.world.to_rgb_array(self.registry)
        w, h = self.world.width, self.world.height
        # Fast path: numpy buffer -> pygame surface -> single scale to screen size
        base = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
        block_w = min(MAP_AREA_W, w * MAP_PIXEL_SCALE)
        block_h = min(MAP_AREA_H, h * MAP_PIXEL_SCALE)
        blocky = pygame.transform.scale(base, (block_w, block_h))
        self._map_surface = pygame.transform.scale(blocky, (MAP_AREA_W, MAP_AREA_H))
        self._map_scale_x = MAP_AREA_W / w
        self._map_scale_y = MAP_AREA_H / h
        self._display_surface = self._map_surface
        self._map_dirty = False
        self._map_render_version = self.world.version

    def start_default(self) -> None:
        self.world, self.registry = build_default_world()
        self.sim = WarSimulator(self.world, self.registry)
        self.state = GameState.SIM_DEFAULT
        self.selected_nation = None
        self.paused = False
        self._cached_counts = self.sim._sync_counts()
        self.accum = 0.15
        self._mark_map_dirty()
        self._rebuild_map_surface()

    def start_editor(self) -> None:
        self.world = WorldMap()
        self.editor_registry = NationRegistry()
        palette = editor_palette()
        for name, color in palette:
            self.editor_registry.create(name, color)
        self.registry = self.editor_registry
        self.state = GameState.EDITOR
        self.editor_nation_idx = 0
        self._rebuild_map_surface()

    def start_custom_sim(self) -> None:
        if not self.world or not self.registry:
            return
        counts = self.world.territory_counts()
        if len(counts) < 2:
            return
        self.sim = WarSimulator(self.world, self.registry)
        self.state = GameState.SIM_CUSTOM
        self.selected_nation = None
        self.paused = False
        self._cached_counts = self.sim._counts
        self.accum = 0.15
        self._mark_map_dirty()
        self._rebuild_map_surface()

    def _grid_at_mouse(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        if not self.world:
            return None
        cs = self._cell_size()
        return self.world.screen_to_grid(
            pos[0], pos[1], MAP_OFFSET_X, MAP_OFFSET_Y, cs
        )

    def _nation_at_mouse(self, pos: tuple[int, int]) -> int | None:
        g = self._grid_at_mouse(pos)
        if not g:
            return None
        nid = self.world.get_cell(g[0], g[1]) if self.world else 0
        return nid if nid > 0 else None

    def run(self) -> None:
        while True:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                self._handle_event(event)

            if self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
                self._update_sim(dt)
            else:
                self._maybe_refresh_map(dt)

            self._draw()
            pygame.display.flip()

    def _handle_event(self, event: pygame.event.Event) -> None:
        if self.state == GameState.MENU:
            for i, btn in enumerate(self._buttons):
                if btn.handle(event):
                    if i == 0:
                        self.start_default()
                    elif i == 1:
                        self.start_editor()
                    elif i == 2:
                        pygame.quit()
                        sys.exit(0)
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.editing_name:
                    self.editing_name = False
                    self.rename_buffer = ""
                else:
                    self.state = GameState.MENU
                    self._setup_menu_buttons()
                return
            if event.key == pygame.K_SPACE:
                if self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
                    self.paused = not self.paused
            if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.speed_idx = min(len(SIM_SPEEDS) - 1, self.speed_idx + 1)
            if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.speed_idx = max(0, self.speed_idx - 1)
            if self.editing_name and self.registry and self.selected_nation:
                if event.key == pygame.K_RETURN:
                    self.registry.rename(self.selected_nation, self.rename_buffer or "Unnamed")
                    self.editing_name = False
                    self.rename_buffer = ""
                    self._rebuild_map_surface()
                elif event.key == pygame.K_BACKSPACE:
                    self.rename_buffer = self.rename_buffer[:-1]
                elif event.unicode and len(self.rename_buffer) < 32:
                    self.rename_buffer += event.unicode

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if self._handle_ui_click(mx, my):
                return
            if self.state == GameState.EDITOR:
                self._editor_paint(mx, my, event.button)
            elif self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
                nid = self._nation_at_mouse((mx, my))
                if nid:
                    if (
                        self._attack_source
                        and self._attack_source != nid
                        and self.sim
                    ):
                        self.sim.god_attack_to_death(self._attack_source, nid)
                        self._mark_map_dirty()
                        self._attack_source = None
                    else:
                        self.selected_nation = nid
                        self._attack_source = nid

        if event.type == pygame.MOUSEMOTION and event.buttons[0]:
            if self.state == GameState.EDITOR:
                self._editor_paint(event.pos[0], event.pos[1], 1)

    def _editor_paint(self, mx: int, my: int, button: int) -> None:
        if not self.world or not self.registry:
            return
        g = self._grid_at_mouse((mx, my))
        if not g:
            return
        palette = list(self.registry.nations.values())
        if not palette:
            return
        if button == 1:
            nation = palette[self.editor_nation_idx % len(palette)]
            self.world.paint_disk(g[0], g[1], self.editor_brush, nation.id)
        elif button == 3:
            self.world.set_cell(g[0], g[1], 0)
        self._mark_map_dirty()

    def _handle_ui_click(self, mx: int, my: int) -> bool:
        # Bottom toolbar
        bar = pygame.Rect(0, WINDOW_H - 56, WINDOW_W, 56)
        if not bar.collidepoint(mx, my):
            if self.state == GameState.EDITOR:
                # Side palette clicks
                pr = pygame.Rect(MAP_OFFSET_X + MAP_AREA_W + 30, MAP_OFFSET_Y, 220, MAP_AREA_H)
                if pr.collidepoint(mx, my):
                    nations = list(self.registry.nations.values()) if self.registry else []
                    idx = (my - pr.y - 40) // 36
                    if 0 <= idx < len(nations):
                        self.editor_nation_idx = idx
                        self.selected_nation = nations[idx].id
                    return True
            return False

        btn_w = 130
        x = 20
        buttons_sim = [
            ("Pause" if not self.paused else "Resume", "pause"),
            ("Slower", "slow"),
            ("Faster", "fast"),
            ("Destroy", "destroy"),
            ("Attack!", "attack"),
            ("Menu", "menu"),
        ]
        buttons_edit = [
            ("Start War", "start"),
            ("Brush+", "b+"),
            ("Brush-", "b-"),
            ("Rename", "rename"),
            ("Menu", "menu"),
        ]
        labels = (
            buttons_sim
            if self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM)
            else buttons_edit
        )
        for label, action in labels:
            r = pygame.Rect(x, bar.y + 10, btn_w, 36)
            if r.collidepoint(mx, my):
                self._toolbar_action(action)
                return True
            x += btn_w + 8
        return False

    def _toolbar_action(self, action: str) -> None:
        if action == "menu":
            self.state = GameState.MENU
            self._setup_menu_buttons()
        elif action == "pause":
            self.paused = not self.paused
        elif action == "slow":
            self.speed_idx = max(0, self.speed_idx - 1)
        elif action == "fast":
            self.speed_idx = min(len(SIM_SPEEDS) - 1, self.speed_idx + 1)
        elif action == "start":
            self.start_custom_sim()
        elif action == "b+":
            self.editor_brush = min(24, self.editor_brush + 2)
        elif action == "b-":
            self.editor_brush = max(2, self.editor_brush - 2)
        elif action == "rename" and self.selected_nation:
            self.editing_name = True
            n = self.registry.get(self.selected_nation) if self.registry else None
            self.rename_buffer = n.name if n else ""
        elif action == "destroy" and self.sim and self.selected_nation:
            self.sim.god_destroy(self.selected_nation)
            self._mark_map_dirty()
        elif action == "attack" and self.sim and self.selected_nation:
            living = [
                n.id
                for n in self.registry.living()
                if n.id != self.selected_nation
            ] if self.registry else []
            if living and self.world:
                counts = self.world.territory_counts()
                victim = max(living, key=lambda i: counts.get(i, 0))
                self.sim.god_attack_to_death(self.selected_nation, victim)
                self._mark_map_dirty()

    def _update_sim(self, dt: float) -> None:
        if not self.sim or self.paused:
            self._maybe_refresh_map(dt)
            return
        self.accum += dt * SIM_SPEEDS[self.speed_idx]
        steps = 0
        max_steps = 5
        while self.accum >= 0.05 and steps < max_steps:
            self.accum -= 0.05
            self.sim.step(SIM_SPEEDS[self.speed_idx])
            self._mark_map_dirty()
            steps += 1
        if self.sim:
            self._cached_counts = self.sim._counts
        self._maybe_refresh_map(dt)

    def _maybe_refresh_map(self, dt: float) -> None:
        if not self.world or not self.registry:
            return
        if not self._map_dirty and self.world.version == self._map_render_version:
            return
        self._map_redraw_timer -= dt
        if self._map_redraw_timer > 0:
            return
        self._rebuild_map_surface()
        self._map_redraw_timer = 0.08

    def _draw(self) -> None:
        self.screen.fill(BG)
        if self.state == GameState.MENU:
            draw_title_screen(self.screen, self.fonts)
            for btn in self._buttons:
                btn.draw(self.screen)
            hint = self.fonts["small"].render(
                "Watch nations fight • Click to select • God-mode destroy & attack",
                True,
                TEXT_DIM,
            )
            self.screen.blit(hint, hint.get_rect(center=(WINDOW_W // 2, WINDOW_H - 40)))
            return

        self._draw_map_view()
        self._draw_year_banner()
        self._draw_sidebar()
        self._draw_toolbar()
        self._draw_help_line()

    def _draw_map_view(self) -> None:
        frame = pygame.Rect(MAP_OFFSET_X - 4, MAP_OFFSET_Y - 4, MAP_AREA_W + 8, MAP_AREA_H + 8)
        pygame.draw.rect(self.screen, (40, 48, 65), frame, border_radius=6)
        if self._map_surface:
            self.screen.blit(self._map_surface, (MAP_OFFSET_X, MAP_OFFSET_Y))
            self._draw_capitals()

    def _draw_year_banner(self) -> None:
        if not self.sim or self.state not in (
            GameState.SIM_DEFAULT,
            GameState.SIM_CUSTOM,
        ):
            return
        year = self.sim.current_year()
        label = str(year)
        font = self.fonts["large"]
        text = font.render(label, True, TEXT)
        pad_x, pad_y = 14, 6
        box = text.get_rect()
        box.centerx = MAP_OFFSET_X + MAP_AREA_W // 2
        box.y = MAP_OFFSET_Y + 8
        bg = pygame.Rect(
            box.x - pad_x,
            box.y - pad_y,
            box.width + pad_x * 2,
            box.height + pad_y * 2,
        )
        pygame.draw.rect(self.screen, (20, 24, 34), bg, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_BORDER, bg, 2, border_radius=8)
        self.screen.blit(text, box)
        sub = self.fonts["small"].render("Year", True, TEXT_DIM)
        sub_rect = sub.get_rect(midbottom=(box.centerx, box.y - 2))
        self.screen.blit(sub, sub_rect)

    def _draw_capitals(self) -> None:
        if not self.registry or not self.world:
            return
        ox, oy = MAP_OFFSET_X, MAP_OFFSET_Y
        sx = getattr(self, "_map_scale_x", MAP_AREA_W / self.world.width)
        sy = getattr(self, "_map_scale_y", MAP_AREA_H / self.world.height)
        for nation in self.registry.nations.values():
            if not nation.alive or nation.capital_x < 0:
                continue
            px = ox + int((nation.capital_x + 0.5) * sx)
            py = oy + int((nation.capital_y + 0.5) * sy)
            pygame.draw.circle(self.screen, CAPITAL_COLOR, (px, py), 6)
            pygame.draw.circle(self.screen, CAPITAL_RING, (px, py), 6, 2)
            pygame.draw.circle(self.screen, (20, 0, 0), (px, py), 2)

    def _draw_sidebar(self) -> None:
        sx = MAP_OFFSET_X + MAP_AREA_W + 24
        panel = pygame.Rect(sx, MAP_OFFSET_Y, WINDOW_W - sx - 16, MAP_AREA_H)
        draw_panel(self.screen, panel, "Nations", self.fonts["med"])

        if not self.registry:
            return
        counts = self._cached_counts or (
            self.world.territory_counts() if self.world else {}
        )
        sorted_nations = sorted(
            self.registry.nations.values(),
            key=lambda n: counts.get(n.id, 0),
            reverse=True,
        )
        y = panel.y + 40
        for nation in sorted_nations[:22]:
            tc = counts.get(nation.id, 0)
            if self.state == GameState.EDITOR and tc == 0 and nation.alive:
                pass
            color = nation.color if nation.alive else TEXT_DIM
            label = f"{nation.name[:14]:<14} {tc:>5}"
            if nation.id == self.selected_nation:
                pygame.draw.rect(
                    self.screen,
                    (55, 70, 100),
                    (panel.x + 8, y - 2, panel.width - 16, 22),
                    border_radius=4,
                )
            t = self.fonts["small"].render(label, True, color if nation.alive else TEXT_DIM)
            pygame.draw.circle(self.screen, nation.color, (panel.x + 16, y + 8), 6)
            self.screen.blit(t, (panel.x + 28, y))
            y += 24
            if y > panel.bottom - 120:
                break

        if self.sim:
            leader, size = self.sim.leader()
            y = panel.bottom - 110
            draw_panel(self.screen, pygame.Rect(panel.x + 8, y, panel.width - 16, 118), None, self.fonts["small"])
            alive = self.sim.nations_alive_count()
            year = self.sim.current_year()
            lines = [
                f"Year: {year}",
                f"Leader: {leader}",
                f"Nations left: {alive}",
                f"Land: {size}",
                f"Speed: {SIM_SPEEDS[self.speed_idx]}x",
            ]
            for i, line in enumerate(lines):
                t = self.fonts["small"].render(line, True, TEXT)
                self.screen.blit(t, (panel.x + 16, y + 12 + i * 22))

            for i, ev in enumerate(self.sim.events[:5]):
                t = self.fonts["small"].render(ev[:36], True, TEXT_DIM)
                self.screen.blit(t, (panel.x + 16, y - 88 + i * 18))

        if self.state == GameState.EDITOR:
            y = panel.y + 40
            for i, nation in enumerate(list(self.registry.nations.values())):
                if nation.id == self.selected_nation or i == self.editor_nation_idx:
                    pygame.draw.rect(
                        self.screen,
                        (70, 90, 130) if i == self.editor_nation_idx else (55, 70, 100),
                        (panel.x + 6, y - 2, panel.width - 12, 24),
                        2,
                        border_radius=4,
                    )
                y += 24

        if self.editing_name:
            box = pygame.Rect(sx, MAP_OFFSET_Y - 36, panel.width, 28)
            pygame.draw.rect(self.screen, (50, 60, 80), box, border_radius=4)
            t = self.fonts["small"].render(f"Rename: {self.rename_buffer}_", True, TEXT)
            self.screen.blit(t, (box.x + 8, box.y + 4))

        if self.selected_nation and self.registry:
            n = self.registry.get(self.selected_nation)
            if n:
                sel = self.fonts["small"].render(
                    f"Selected: {n.name}" + (" (dead)" if not n.alive else ""),
                    True,
                    DANGER if not n.alive else SUCCESS,
                )
                self.screen.blit(sel, (MAP_OFFSET_X, MAP_OFFSET_Y - 28))

    def _draw_toolbar(self) -> None:
        bar = pygame.Rect(0, WINDOW_H - 56, WINDOW_W, 56)
        pygame.draw.rect(self.screen, (24, 28, 38), bar)
        pygame.draw.line(self.screen, (50, 58, 75), (0, bar.y), (WINDOW_W, bar.y), 2)
        x = 20
        btn_w = 130
        if self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
            items = [
                "Pause" if not self.paused else "Resume",
                "Slower",
                "Faster",
                "Destroy",
                "Attack!",
                "Menu",
            ]
        else:
            items = ["Start War", "Brush+", "Brush-", "Rename", "Menu"]
        for label in items:
            r = pygame.Rect(x, bar.y + 10, btn_w, 36)
            pygame.draw.rect(self.screen, (45, 55, 75), r, border_radius=6)
            t = self.fonts["small"].render(label, True, TEXT)
            self.screen.blit(t, t.get_rect(center=r.center))
            x += btn_w + 8

    def _draw_help_line(self) -> None:
        if self.state == GameState.EDITOR:
            msg = "Left-click paint • Right-click erase • Pick nation in list • Start War when ready"
        else:
            msg = (
                "Red dot = capital • Capture it to destroy a nation • "
                "Tan land = free territory • Space pause"
            )
        t = self.fonts["small"].render(msg, True, TEXT_DIM)
        self.screen.blit(t, (MAP_OFFSET_X, 50))


def main() -> None:
    game = NationsAtWar()
    if game.fonts.get("_bitmap"):
        print("Using bitmap fonts (pygame.font unavailable on this Python).")
    game.run()


if __name__ == "__main__":
    main()
