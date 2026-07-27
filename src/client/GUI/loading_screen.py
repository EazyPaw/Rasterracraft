# Commented and arranged by ChatGPT
import pygame

from src.client.GUI.gui import GUI


class LoadingScreen(GUI):
    def __init__(self, render):
        super().__init__(render)
        self.priority = 1000
        self._background_cache = None
        self._background_cache_key = None

    def draw(self):
        client = self.render.client
        screen = self.render.screen
        width, height = screen.get_size()
        self._draw_background(width, height)

        title = client.resources_manager.get_translation_key("menu.loadingLevel")
        title_font = self.render.get_font(max(28, min(46, height // 14)))
        title_surface = title_font.render(title, True, (245, 245, 245))
        screen.blit(
            title_surface, title_surface.get_rect(center=(width // 2, height // 2 - 48))
        )

        required = client.required_spawn_regions
        loaded = client.loaded_chunk_regions
        total = max(1, len(required))
        done = min(total, len(required.intersection(loaded)))
        progress = done / total
        bar_width = min(520, max(240, width - 120))
        bar_rect = pygame.Rect(
            (width - bar_width) // 2, height // 2 + 12, bar_width, 22
        )
        pygame.draw.rect(screen, (35, 35, 35), bar_rect)
        fill = pygame.Rect(
            bar_rect.x + 2,
            bar_rect.y + 2,
            max(0, int((bar_width - 4) * progress)),
            bar_rect.height - 4,
        )
        if fill.width:
            pygame.draw.rect(screen, (101, 173, 68), fill)

    def _draw_background(self, width: int, height: int) -> None:
        cache_key = (width, height)
        if self._background_cache is None or self._background_cache_key != cache_key:
            surface = self.render.create_surface((width, height), convert=True)
            dirt = self.render.client.resources_manager.get_texture_img("blocks.dirt")
            tile_size = max(32, min(128, min(width, height) // 12))
            tile = self.render.scale_surface(dirt, (tile_size, tile_size))
            for x in range(0, width, tile_size):
                for y in range(0, height, tile_size):
                    self.render.blit_to(surface, tile, (x, y))
            shade = self.render.create_surface((width, height), alpha=True)
            self.render.fill_surface(shade, (0, 0, 0, 115))
            self.render.blit_to(surface, shade, (0, 0))
            self._background_cache = surface
            self._background_cache_key = cache_key
        self.render.blit(self._background_cache, (0, 0))

    def handle_events(self, events):

        return
