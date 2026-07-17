import pygame

from resources.client.GUI.button import Button
from resources.client.GUI.gui import GUI
from resources.server.text import Text


class DisconnectScreen(GUI):
    """Minecraft-style full-screen connection failure page."""

    def __init__(self, render, title_key: str, reason: str | Text):
        super().__init__(render)
        self.priority = 2000
        self.title_key = title_key
        self.reason = reason
        self.back_button = Button(
            self.render.client.resources_manager.get_translation_key("gui.toMenu"),
            self._return_to_main_menu,
        )
        self._background_cache = None
        self._background_cache_key = None

    def draw(self):
        width, height = self.render.screen.get_size()
        self._draw_background(width, height)

        title = self.render.client.resources_manager.get_translation_key(self.title_key)
        title_size = max(24, min(40, height // 25))
        reason_size = max(20, min(32, height // 30))
        title_width = self.render.get_font(title_size).size(title)[0]
        self.render.render_text(
            title,
            ((width - title_width) / 2, int(height * 0.38)),
            font_size=title_size,
            shadow=True,
        )

        max_reason_width = max(240, min(1000, width - 100))
        reason_lines = self._wrap_text(self.reason, reason_size, max_reason_width)
        line_height = self.render.get_font(reason_size).get_linesize()
        reason_y = int(height * 0.49)
        for index, line in enumerate(reason_lines):
            line_width = self._measure_text(line, reason_size)
            self.render.render_text(
                line,
                ((width - line_width) / 2, reason_y + index * line_height),
                font_size=reason_size,
                shadow=True,
            )

        button_width = max(300, min(800, int(width * 0.43)))
        button_height = max(38, min(58, int(height * 0.065)))
        button_y = max(
            int(height * 0.58),
            reason_y + len(reason_lines) * line_height + max(18, height // 45),
        )
        button_y = min(button_y, height - button_height - 30)
        self.back_button.set_rect(
            (width - button_width) // 2, button_y, button_width, button_height
        )
        self.back_button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]):
        for event in events[:]:
            if event.type in (
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
            ):
                if self.back_button.handle_event(event):
                    events.remove(event)
            elif event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN,
                pygame.K_KP_ENTER,
            ):
                self.back_button.click()
                events.remove(event)

    def _return_to_main_menu(self):
        self.render.client.return_to_main_menu()

    def _draw_background(self, width: int, height: int):
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
            self.render.fill_surface(shade, (0, 0, 0, 145))
            self.render.blit_to(surface, shade, (0, 0))
            self._background_cache = surface
            self._background_cache_key = cache_key
        self.render.blit(self._background_cache, (0, 0))

    def _measure_text(self, text: str | Text, font_size: int) -> int:
        if not isinstance(text, Text):
            return self.render.get_font(font_size).size(str(text))[0]
        return sum(
            self.render.get_font(font_size, bool(segment.get("bold", False))).size(
                str(segment.get("text", ""))
            )[0]
            for segment in text.text
        )

    def _wrap_text(self, text: str | Text, font_size: int, max_width: int):
        if not isinstance(text, Text):
            text = Text(str(text))
        lines = []
        current_segments = []
        current_width = 0
        for segment in text.text:
            color = segment.get("color")
            bold = bool(segment.get("bold", False))
            font = self.render.get_font(font_size, bold)
            for char in str(segment.get("text", "")):
                if char == "\n":
                    lines.append(Text(current_segments))
                    current_segments = []
                    current_width = 0
                    continue
                char_width = font.size(char)[0]
                if current_segments and current_width + char_width > max_width:
                    lines.append(Text(current_segments))
                    current_segments = []
                    current_width = 0
                if (
                    current_segments
                    and current_segments[-1]["color"] == color
                    and current_segments[-1]["bold"] == bold
                ):
                    current_segments[-1]["text"] += char
                else:
                    current_segments.append(
                        {"text": char, "color": color, "bold": bold}
                    )
                current_width += char_width
        if current_segments or not lines:
            lines.append(Text(current_segments))
        return lines
