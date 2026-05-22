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


if not getattr(sys, "frozen", False):
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
    GOD_GOLD,
    GOD_PANEL,
    PANEL_BORDER,
    SELECT_BORDER,
    SELECT_GLOW,
    SUCCESS,
    TEXT,
    TEXT_DIM,
    OCEAN,
)
from default_world import build_default_world, editor_palette
from map_io import list_saved_maps, load_custom_map, save_custom_map
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
        self.god_mode = False
        self.god_brush = 6
        self.god_annex_armed = False
        self.editor_brush = 8
        self.editor_registry = NationRegistry()
        self.text_buffer = ""
        self.text_input_mode: str | None = None
        self.status_message = ""
        self.status_timer = 0.0
        self._map_surface: pygame.Surface | None = None
        self._buttons: list[Button] = []
        self._last_redraw_tick = -1
        self._map_dirty = True
        self._map_render_version = -1
        self._map_redraw_timer = 0.0
        self._display_surface: pygame.Surface | None = None
        self._cached_counts: dict[int, int] = {}
        self._setup_menu_buttons()

    def _setup_menu_buttons(self) -> None:
        cx = WINDOW_W // 2
        bw, bh = 320, 48
        y0 = 290
        self._buttons = [
            Button(
                pygame.Rect(cx - bw // 2, y0, bw, bh),
                "Default World Map",
                self.fonts["large"],
                primary=True,
            ),
            Button(
                pygame.Rect(cx - bw // 2, y0 + 58, bw, bh),
                "Create Custom Map",
                self.fonts["large"],
            ),
            Button(
                pygame.Rect(cx - bw // 2, y0 + 116, bw, bh),
                "Load Saved Map",
                self.fonts["large"],
            ),
            Button(
                pygame.Rect(cx - bw // 2, y0 + 174, bw, bh),
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
        self._select_nation(None)
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
        self.sim = None
        nations = list(self.registry.nations.values())
        if nations:
            self._select_nation(nations[0].id)
        else:
            self._select_nation(None)
        self._rebuild_map_surface()

    def load_saved_map(self, name: str) -> None:
        try:
            self.world, self.registry = load_custom_map(name)
        except FileNotFoundError:
            self.status_message = f"Map not found: {name}"
            self.status_timer = 4.0
            return
        self.state = GameState.EDITOR
        self.editor_registry = self.registry
        self.sim = None
        nations = list(self.registry.nations.values())
        self._select_nation(nations[0].id if nations else None)
        self._mark_map_dirty()
        self._rebuild_map_surface()
        self.status_message = f"Loaded map: {name}"
        self.status_timer = 3.0

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

    def _select_nation(self, nation_id: int | None) -> None:
        self.selected_nation = nation_id
        self.god_annex_armed = False
        if nation_id and self.registry:
            n = self.registry.get(nation_id)
            if n:
                self.status_message = f"Selected: {n.name}"
                self.status_timer = 2.0

    def _sidebar_panel_rect(self) -> pygame.Rect:
        sx = MAP_OFFSET_X + MAP_AREA_W + 24
        return pygame.Rect(sx, MAP_OFFSET_Y, WINDOW_W - sx - 16, MAP_AREA_H)

    def _sidebar_nation_order(self) -> list:
        if not self.registry:
            return []
        if self.state == GameState.EDITOR:
            return list(self.registry.nations.values())
        counts = self._cached_counts or self.world.territory_counts()
        with_land = [
            n
            for n in self.registry.nations.values()
            if counts.get(n.id, 0) > 0
        ]
        if self.selected_nation:
            selected = self.registry.get(self.selected_nation)
            rest = [n for n in with_land if n.id != self.selected_nation]
            rest.sort(key=lambda n: counts.get(n.id, 0), reverse=True)
            if selected:
                return ([selected] if counts.get(selected.id, 0) > 0 else []) + rest
        return sorted(with_land, key=lambda n: counts.get(n.id, 0), reverse=True)

    def _sidebar_list_top(self, panel: pygame.Rect) -> int:
        return panel.y + 118

    def _try_select_nation_from_sidebar(self, mx: int, my: int) -> bool:
        if self.state not in (GameState.EDITOR, GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
            return False
        panel = self._sidebar_panel_rect()
        list_top = self._sidebar_list_top(panel)
        bottom = panel.bottom - (300 if self.god_mode and self.sim else 130)
        if not (panel.x <= mx <= panel.right and list_top <= my <= bottom):
            return False
        nations = self._sidebar_nation_order()
        if not nations:
            return False
        row_h = 30
        idx = (my - list_top) // row_h
        if 0 <= idx < len(nations):
            self._select_nation(nations[idx].id)
            return True
        return False

    def run(self) -> None:
        while True:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit(0)
                self._handle_event(event)

            if self.status_timer > 0:
                self.status_timer = max(0.0, self.status_timer - dt)

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
                        self.text_input_mode = "load_menu"
                        self.text_buffer = ""
                    elif i == 3:
                        pygame.quit()
                        sys.exit(0)
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if self.text_input_mode:
                    self.text_input_mode = None
                    self.text_buffer = ""
                else:
                    self.state = GameState.MENU
                    self._setup_menu_buttons()
                return
            if self.text_input_mode:
                self._handle_text_input_key(event)
                return
            if event.key == pygame.K_SPACE:
                if self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
                    self.paused = not self.paused
            if event.key == pygame.K_g and self.state in (
                GameState.SIM_DEFAULT,
                GameState.SIM_CUSTOM,
            ):
                self.god_mode = not self.god_mode
                self.god_annex_armed = False
                self.status_message = (
                    "God mode ON — reshape the world!"
                    if self.god_mode
                    else "God mode OFF — watch only"
                )
                self.status_timer = 2.5
            if event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                self.speed_idx = min(len(SIM_SPEEDS) - 1, self.speed_idx + 1)
            if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self.speed_idx = max(0, self.speed_idx - 1)
        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            if self._handle_ui_click(mx, my):
                return
            if self.state == GameState.EDITOR:
                self._editor_paint(mx, my, event.button)
            elif self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
                self._handle_sim_map_click(mx, my, event.button)

        if event.type == pygame.MOUSEMOTION and event.buttons[0]:
            if self.state == GameState.EDITOR:
                self._editor_paint(event.pos[0], event.pos[1], 1)
            elif (
                self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM)
                and self.god_mode
                and self.selected_nation
            ):
                self._god_paint(event.pos[0], event.pos[1], 1)
        if event.type == pygame.MOUSEMOTION and event.buttons[2]:
            if self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM) and self.god_mode:
                self._god_paint(event.pos[0], event.pos[1], 3)

    def _handle_sim_map_click(self, mx: int, my: int, button: int) -> None:
        if not self.world or not self.registry:
            return
        nid = self._nation_at_mouse((mx, my))

        if self.god_mode and button == 3:
            self._god_paint(mx, my, 3)
            return

        if (
            self.god_mode
            and button == 1
            and self.god_annex_armed
            and nid
            and self.selected_nation
            and nid != self.selected_nation
            and self.sim
        ):
            self.sim.god_attack_to_death(self.selected_nation, nid)
            self._mark_map_dirty()
            self.god_annex_armed = False
            self.status_message = "Annexed!"
            self.status_timer = 1.5
            return

        if button == 1 and nid:
            self._select_nation(nid)

    def _god_paint(self, mx: int, my: int, button: int) -> None:
        if not self.sim or not self.world or not self.selected_nation:
            return
        g = self._grid_at_mouse((mx, my))
        if not g:
            return
        if button == 1:
            for dx in range(-self.god_brush, self.god_brush + 1):
                for dy in range(-self.god_brush, self.god_brush + 1):
                    if dx * dx + dy * dy <= self.god_brush * self.god_brush:
                        self.sim.god_claim_tile(
                            g[0] + dx, g[1] + dy, self.selected_nation
                        )
        elif button == 3:
            self.sim.god_neutralize_tile(g[0], g[1])
        self._cached_counts = self.sim._counts
        self._mark_map_dirty()

    def _editor_paint(self, mx: int, my: int, button: int) -> None:
        if not self.world or not self.registry:
            return
        g = self._grid_at_mouse((mx, my))
        if not g:
            return
        if button == 1 and self.selected_nation:
            self.world.paint_disk(g[0], g[1], self.editor_brush, self.selected_nation)
        elif button == 3:
            self.world.set_cell(g[0], g[1], 0)
        self._mark_map_dirty()

    def _handle_ui_click(self, mx: int, my: int) -> bool:
        # Bottom toolbar
        bar = pygame.Rect(0, WINDOW_H - 56, WINDOW_W, 56)
        if not bar.collidepoint(mx, my):
            if self._try_select_nation_from_sidebar(mx, my):
                return True
            return False

        btn_w = 108
        x = 12
        buttons_sim = [
            ("Pause" if not self.paused else "Resume", "pause"),
            ("Slower", "slow"),
            ("Faster", "fast"),
            ("God ON" if self.god_mode else "God OFF", "god"),
            ("Menu", "menu"),
        ]
        if self.god_mode:
            buttons_sim = buttons_sim[:4] + [
                ("Destroy", "destroy"),
                ("Boost", "boost"),
                ("Peace", "peace"),
                ("Annex", "attack"),
            ] + buttons_sim[4:]
        buttons_edit = [
            ("Start War", "start"),
            ("Save", "save"),
            ("Load", "load"),
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
            x += btn_w + 6
        return False

    def _handle_text_input_key(self, event: pygame.event.Event) -> None:
        if event.key == pygame.K_RETURN:
            name = self.text_buffer.strip() or "custom_map"
            mode = self.text_input_mode
            self.text_input_mode = None
            self.text_buffer = ""
            if mode == "rename" and self.registry and self.selected_nation:
                self.registry.rename(self.selected_nation, name)
                self.world.assign_capitals(self.registry) if self.world else None
                self._mark_map_dirty()
            elif mode == "save" and self.world and self.registry:
                path = save_custom_map(name, self.world, self.registry)
                self.status_message = f"Saved: {path.name}"
                self.status_timer = 3.0
            elif mode in ("load", "load_menu"):
                self.load_saved_map(name)
            return
        if event.key == pygame.K_BACKSPACE:
            self.text_buffer = self.text_buffer[:-1]
        elif event.unicode and len(self.text_buffer) < 40:
            self.text_buffer += event.unicode

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
        elif action == "god":
            self.god_mode = not self.god_mode
            self.god_annex_armed = False
            self.status_message = (
                "God mode ON!" if self.god_mode else "God mode OFF"
            )
            self.status_timer = 2.0
        elif action == "boost" and self.sim and self.selected_nation:
            self.sim.god_boost(self.selected_nation)
        elif action == "peace" and self.sim and self.selected_nation:
            self.sim.god_toggle_peace(self.selected_nation)
        elif action == "start":
            self.start_custom_sim()
        elif action == "b+":
            self.editor_brush = min(24, self.editor_brush + 2)
        elif action == "b-":
            self.editor_brush = max(2, self.editor_brush - 2)
        elif action == "save" and self.world and self.registry:
            self.text_input_mode = "save"
            self.text_buffer = "my_map"
        elif action == "load":
            saved = list_saved_maps()
            self.text_input_mode = "load"
            self.text_buffer = saved[-1] if saved else "my_map"
        elif action == "rename" and self.selected_nation:
            self.text_input_mode = "rename"
            n = self.registry.get(self.selected_nation) if self.registry else None
            self.text_buffer = n.name if n else ""
        elif action == "destroy" and self.sim and self.selected_nation:
            self.sim.god_destroy(self.selected_nation)
            self._mark_map_dirty()
        elif action == "attack" and self.sim and self.selected_nation:
            self.god_annex_armed = True
            self.status_message = "Click another nation on the map to annex"
            self.status_timer = 3.0

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
                "Watch nations fight • Press G in-game for God mode",
                True,
                TEXT_DIM,
            )
            self.screen.blit(hint, hint.get_rect(center=(WINDOW_W // 2, WINDOW_H - 40)))
            return

        self._draw_map_view()
        self._draw_year_banner()
        if self.god_mode and self.state in (
            GameState.SIM_DEFAULT,
            GameState.SIM_CUSTOM,
        ):
            self._draw_god_banner()
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

    def _draw_god_banner(self) -> None:
        label = "GOD MODE"
        font = self.fonts["med"]
        text = font.render(label, True, GOD_GOLD)
        box = text.get_rect()
        box.topright = (MAP_OFFSET_X + MAP_AREA_W - 12, MAP_OFFSET_Y + 8)
        bg = box.inflate(20, 12)
        pygame.draw.rect(self.screen, GOD_PANEL, bg, border_radius=8)
        pygame.draw.rect(self.screen, GOD_GOLD, bg, 2, border_radius=8)
        self.screen.blit(text, box)

    def _draw_god_panel(self, panel: pygame.Rect) -> None:
        if not self.god_mode or self.state not in (
            GameState.SIM_DEFAULT,
            GameState.SIM_CUSTOM,
        ):
            return
        box = pygame.Rect(panel.x + 8, panel.bottom - 200, panel.width - 16, 188)
        pygame.draw.rect(self.screen, GOD_PANEL, box, border_radius=8)
        pygame.draw.rect(self.screen, GOD_GOLD, box, 2, border_radius=8)
        lines = [
            "GOD MODE",
            "G — toggle",
            "Paint: drag w/ nation",
            "R-click: neutral land",
            "Annex: toolbar then click target",
            "[Destroy] [Boost]",
            "[Peace] [Annex]",
        ]
        y = box.y + 8
        for i, line in enumerate(lines):
            color = GOD_GOLD if i == 0 else TEXT_DIM
            t = self.fonts["small"].render(line, True, color)
            self.screen.blit(t, (box.x + 10, y))
            y += 20

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
            is_sel = nation.id == self.selected_nation
            radius = 9 if is_sel else 6
            pygame.draw.circle(self.screen, CAPITAL_COLOR, (px, py), radius)
            ring = SELECT_GLOW if is_sel else CAPITAL_RING
            pygame.draw.circle(self.screen, ring, (px, py), radius, 3 if is_sel else 2)
            pygame.draw.circle(self.screen, (20, 0, 0), (px, py), 2)

    def _draw_selected_nation_card(self, panel: pygame.Rect) -> None:
        card = pygame.Rect(panel.x + 8, panel.y + 34, panel.width - 16, 78)
        pygame.draw.rect(self.screen, (35, 42, 58), card, border_radius=8)

        if not self.selected_nation or not self.registry:
            pygame.draw.rect(self.screen, PANEL_BORDER, card, 2, border_radius=8)
            t = self.fonts["small"].render(
                "No nation selected — click list or map",
                True,
                TEXT_DIM,
            )
            self.screen.blit(t, (card.x + 12, card.y + 28))
            return

        nation = self.registry.get(self.selected_nation)
        if not nation:
            return

        pygame.draw.rect(self.screen, nation.color, (card.x + 12, card.y + 14, 48, 48))
        pygame.draw.rect(self.screen, SELECT_BORDER, (card.x + 12, card.y + 14, 48, 48), 2)

        title = self.fonts["small"].render("YOUR NATION", True, SELECT_GLOW)
        self.screen.blit(title, (card.x + 68, card.y + 12))

        name = self.fonts["med"].render(nation.name[:16], True, TEXT)
        self.screen.blit(name, (card.x + 68, card.y + 32))

        counts = self._cached_counts or (
            self.world.territory_counts() if self.world else {}
        )
        extra = ""
        if self.state == GameState.EDITOR:
            extra = "  (paint with this color)"
        elif self.sim and hasattr(nation, "ai_style"):
            extra = f"  [{nation.ai_style}]"
        sub = self.fonts["small"].render(
            f"Land: {counts.get(nation.id, 0)}{extra}",
            True,
            TEXT_DIM,
        )
        self.screen.blit(sub, (card.x + 68, card.y + 54))

        pygame.draw.rect(self.screen, SELECT_GLOW, card, 3, border_radius=8)

    def _draw_sidebar(self) -> None:
        panel = self._sidebar_panel_rect()
        title = "Map Editor" if self.state == GameState.EDITOR else "Nations"
        draw_panel(self.screen, panel, title, self.fonts["med"])

        if not self.registry:
            return

        self._draw_selected_nation_card(panel)

        hint = self.fonts["small"].render("Click a nation to switch:", True, TEXT_DIM)
        self.screen.blit(hint, (panel.x + 12, panel.y + 100))

        counts = self._cached_counts or (
            self.world.territory_counts() if self.world else {}
        )
        nations = self._sidebar_nation_order()
        y = self._sidebar_list_top(panel)
        row_h = 30
        max_rows = (panel.bottom - (300 if self.god_mode and self.sim else 130) - y) // row_h

        for i, nation in enumerate(nations[: max_rows]):
            tc = counts.get(nation.id, 0)
            row = pygame.Rect(panel.x + 8, y, panel.width - 16, row_h - 2)
            is_sel = nation.id == self.selected_nation

            if is_sel:
                pygame.draw.rect(self.screen, (50, 65, 95), row, border_radius=6)
                pygame.draw.rect(self.screen, nation.color, row, 3, border_radius=6)
            else:
                pygame.draw.rect(self.screen, (32, 38, 52), row, border_radius=6)

            pygame.draw.circle(self.screen, nation.color, (row.x + 16, row.centery), 8)
            if is_sel:
                check = self.fonts["small"].render(">", True, SELECT_GLOW)
                self.screen.blit(check, (row.x + 28, row.centery - 7))

            label = nation.name[:13] if self.state == GameState.EDITOR else nation.name[:11]
            if self.state != GameState.EDITOR:
                label = f"{label}  {tc}"
            color = nation.color if nation.alive else TEXT_DIM
            t = self.fonts["small"].render(label, True, color if nation.alive else TEXT_DIM)
            self.screen.blit(t, (row.x + 40, row.centery - 7))
            y += row_h

        self._draw_god_panel(panel)

        if self.sim:
            leader, size = self.sim.leader()
            stats_h = 118 if not self.god_mode else 108
            y = panel.bottom - (310 if self.god_mode else 110)
            draw_panel(self.screen, pygame.Rect(panel.x + 8, y, panel.width - 16, stats_h), None, self.fonts["small"])
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

        if self.god_annex_armed:
            t = self.fonts["small"].render(
                "Annex mode: click target nation on map",
                True,
                GOD_GOLD,
            )
            self.screen.blit(t, (MAP_OFFSET_X, MAP_OFFSET_Y - 28))

        if self.text_input_mode:
            prompts = {
                "rename": "Rename nation",
                "save": "Save map as (Enter)",
                "load": "Load map name (Enter)",
                "load_menu": "Load map name (Enter)",
            }
            hint = prompts.get(self.text_input_mode, "Input")
            box = pygame.Rect(MAP_OFFSET_X, MAP_OFFSET_Y + MAP_AREA_H + 8, MAP_AREA_W, 32)
            pygame.draw.rect(self.screen, (40, 48, 65), box, border_radius=6)
            t = self.fonts["small"].render(
                f"{hint}: {self.text_buffer}_", True, TEXT
            )
            self.screen.blit(t, (box.x + 10, box.y + 6))
            if self.text_input_mode in ("load", "load_menu"):
                saved = list_saved_maps()
                if saved:
                    lst = self.fonts["small"].render(
                        "Saved: " + ", ".join(saved[:6])
                        + ("..." if len(saved) > 6 else ""),
                        True,
                        TEXT_DIM,
                    )
                    self.screen.blit(lst, (box.x + 10, box.y + 22))

        if self.status_timer > 0 and self.status_message:
            t = self.fonts["small"].render(self.status_message, True, SUCCESS)
            self.screen.blit(t, (MAP_OFFSET_X, MAP_OFFSET_Y - 48))

    def _draw_toolbar(self) -> None:
        bar = pygame.Rect(0, WINDOW_H - 56, WINDOW_W, 56)
        pygame.draw.rect(self.screen, (24, 28, 38), bar)
        pygame.draw.line(self.screen, (50, 58, 75), (0, bar.y), (WINDOW_W, bar.y), 2)
        x = 20
        btn_w = 96
        if self.state in (GameState.SIM_DEFAULT, GameState.SIM_CUSTOM):
            items = [
                "Pause" if not self.paused else "Resume",
                "Slower",
                "Faster",
                "God ON" if self.god_mode else "God OFF",
                "Menu",
            ]
            if self.god_mode:
                items = items[:4] + ["Destroy", "Boost", "Peace", "Annex"] + items[4:]
        else:
            items = ["Start War", "Save", "Load", "Brush+", "Brush-", "Rename", "Menu"]
        for label in items:
            r = pygame.Rect(x, bar.y + 10, btn_w, 36)
            pygame.draw.rect(self.screen, (45, 55, 75), r, border_radius=6)
            t = self.fonts["small"].render(label, True, TEXT)
            self.screen.blit(t, t.get_rect(center=r.center))
            x += btn_w + 8

    def _draw_help_line(self) -> None:
        if self.state == GameState.EDITOR:
            msg = (
                "1) Pick YOUR NATION in the list  2) Paint on map  "
                "3) Save map  4) Start War"
            )
        else:
            msg = (
                "Click nation in list or on map to select • G = God mode • Space pause"
                if not self.god_mode
                else "Selected nation shown above — paint/drag in God mode • Annex = pick then click target"
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
