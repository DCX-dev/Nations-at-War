"""UI helpers for Nations at War."""

from __future__ import annotations

import pygame

from constants import (
    ACCENT,
    ACCENT_HOVER,
    BG,
    DANGER,
    FONT_LARGE,
    FONT_MED,
    FONT_SMALL,
    FONT_TITLE,
    PANEL,
    PANEL_BORDER,
    SUCCESS,
    TEXT,
    TEXT_DIM,
)


class Button:
    def __init__(
        self,
        rect: pygame.Rect,
        label: str,
        font: pygame.font.Font,
        primary: bool = False,
    ) -> None:
        self.rect = rect
        self.label = label
        self.font = font
        self.primary = primary
        self.hovered = False

    def draw(self, surface: pygame.Surface) -> None:
        if self.primary:
            bg = ACCENT_HOVER if self.hovered else ACCENT
        else:
            bg = (45, 55, 75) if self.hovered else (38, 46, 62)
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        pygame.draw.rect(surface, PANEL_BORDER, self.rect, 2, border_radius=8)
        text = self.font.render(self.label, True, TEXT)
        surface.blit(
            text,
            text.get_rect(center=self.rect.center),
        )

    def handle(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                return True
        return False


def load_fonts() -> dict:
    """Load UI fonts (pygame or bitmap fallback). Requires pygame.init() first."""
    from bitmap_font import load_fonts_safe

    return load_fonts_safe()


def draw_panel(surface: pygame.Surface, rect: pygame.Rect, title: str | None, font) -> None:
    pygame.draw.rect(surface, PANEL, rect, border_radius=10)
    pygame.draw.rect(surface, PANEL_BORDER, rect, 2, border_radius=10)
    if title:
        t = font.render(title, True, TEXT)
        surface.blit(t, (rect.x + 12, rect.y + 8))


def draw_title_screen(surface: pygame.Surface, fonts) -> None:
    surface.fill(BG)
    title = fonts["title"].render("NATIONS AT WAR", True, ACCENT)
    sub = fonts["med"].render("World War Simulator", True, TEXT_DIM)
    surface.blit(title, title.get_rect(center=(surface.get_width() // 2, 180)))
    surface.blit(sub, sub.get_rect(center=(surface.get_width() // 2, 240)))
