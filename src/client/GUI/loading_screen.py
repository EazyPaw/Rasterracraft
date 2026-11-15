# Commented and arranged by ChatGPT
from src.client.GUI.menu_style import draw_dirt, gui_scale

import pygame

from src.client.GUI.gui import GUI


class LoadingScreen(GUI):
    def __init__(self, render, title_key: str = "menu.loadingLevel"):
        super().__init__(render)
        self.priority = 1000
        self.title_key = title_key
        self._background_cache = None
        self._background_cache_key = None

    def draw(self):
        client = self.render.client
        screen = self.render.screen
        width, height = screen.get_size()
        self._draw_background(width, height)

        title = client.resources_manager.get_translation_key(self.title_key)
        scale = gui_scale(self.render)
        font_size = 8 * scale
        title_width = self.render.get_font(font_size).size(title)[0]
        self.render.render_text(title, ((width - title_width) // 2, height // 2 - 24 * scale),
                                (255, 255, 255), font_size, shadow=True, shadow_strength=0.25)

        required = client.required_spawn_regions
        loaded = client.loaded_chunk_regions
        total = max(1, len(required))
        done = min(total, len(required.intersection(loaded)))
        progress = done / total
        bar_width = min(100 * scale, width - 32)
        bar_rect = pygame.Rect(
            (width - bar_width) // 2, height // 2 + 4 * scale, bar_width, 2 * scale
        )
        pygame.draw.rect(screen, (35, 35, 35), bar_rect)
        fill = pygame.Rect(
            bar_rect.x,
            bar_rect.y,
            max(0, int(bar_width * progress)),
            bar_rect.height,
        )
        if fill.width:
            pygame.draw.rect(screen, (128, 128, 255), fill)

    def _draw_background(self, width: int, height: int):
        draw_dirt(self)

    def handle_events(self, events):

        return
