import pygame

from resources.client.GUI.button import Button
from resources.client.GUI.gui import GUI
from resources.server.text import Text, TextColor


class DeathScreen(GUI):
    """Minecraft-style death overlay with explicit respawn/menu actions."""

    def __init__(self, render, death_message: dict | None = None, score: int = 0):
        super().__init__(render)
        self.priority = 1500
        self.score = int(score)
        self.death_message = death_message or {
            "key": "death.attack.generic",
            "args": [getattr(render.client.client_player, "name", "Player")],
        }
        translations = render.client.resources_manager
        self.respawn_button = Button(
            translations.get_translation_key("deathScreen.respawn"),
            self.respawn,
        )
        self.title_button = Button(
            translations.get_translation_key("deathScreen.titleScreen"),
            self.return_to_title,
        )
        self.buttons = (self.respawn_button, self.title_button)
        self._overlay = None
        self._overlay_size = None

    def update_death_message(self, death_message: dict | None) -> None:
        if isinstance(death_message, dict):
            self.death_message = death_message

    def _resolve_translation_arg(self, value):
        if isinstance(value, dict) and isinstance(value.get("translate"), str):
            return self.render.client.resources_manager.get_translation_key(
                value["translate"]
            )
        return str(value)

    def get_death_message_text(self) -> str:
        key = str(self.death_message.get("key", "death.attack.generic"))
        args = tuple(
            self._resolve_translation_arg(value)
            for value in self.death_message.get("args", ())
        )
        return self.render.client.resources_manager.get_translation_key(key, *args)

    def _score_text(self) -> Text:
        marker = "{score}"
        translated = self.render.client.resources_manager.get_translation_key(
            "deathScreen.scoreValue", marker
        )
        before, found, after = translated.partition(marker)
        segments = [{"text": before, "color": TextColor.WHITE, "bold": False}]
        if found:
            segments.append({
                "text": str(self.score),
                "color": TextColor.YELLOW,
                "bold": False,
            })
            if after:
                segments.append({"text": after, "color": TextColor.WHITE, "bold": False})
        else:
            segments[0]["text"] = translated
        return Text(segments)

    def _draw_overlay(self, width: int, height: int) -> None:
        size = (width, height)
        if self._overlay is None or self._overlay_size != size:
            overlay = pygame.Surface(size, pygame.SRCALPHA)
            denominator = max(1, height - 1)
            for y in range(height):
                t = y / denominator
                color = (
                    int(48 + 45 * t),
                    int(2 + 18 * t),
                    int(2 + 18 * t),
                    int(220 - 20 * t),
                )
                pygame.draw.line(overlay, color, (0, y), (width, y))
            self._overlay = overlay
            self._overlay_size = size
        self.render.blit(self._overlay, (0, 0))

    def _draw_centered(self, text, y: int, color, font_size: int, **kwargs) -> None:
        plain = text.to_plain_string() if isinstance(text, Text) else str(text)
        width = self.render.get_font(font_size).size(plain)[0]
        self.render.render_text(
            text,
            ((self.render.SCREEN_WIDTH - width) / 2, y),
            color,
            font_size,
            shadow=True,
            **kwargs,
        )

    def _layout_buttons(self) -> None:
        width, height = self.render.screen.get_size()
        button_width = max(260, min(520, int(width * 0.46)))
        button_height = max(38, min(54, int(height * 0.064)))
        gap = max(8, int(button_height * 0.24))
        y = int(height * 0.57)
        for button in self.buttons:
            button.set_rect((width - button_width) // 2, y, button_width, button_height)
            y += button_height + gap

    def draw(self) -> None:
        width, height = self.render.screen.get_size()
        self._draw_overlay(width, height)
        self._layout_buttons()

        title = self.render.client.resources_manager.get_translation_key("deathScreen.title")
        title_size = max(34, min(58, height // 10))
        body_size = max(20, min(30, height // 22))
        score_size = max(18, min(26, height // 25))
        self._draw_centered(title, int(height * 0.23), (255, 255, 255), title_size)
        self._draw_centered(
            self.get_death_message_text(),
            int(height * 0.35),
            (255, 255, 255),
            body_size,
        )
        self._draw_centered(
            self._score_text(),
            int(height * 0.42),
            (255, 255, 255),
            score_size,
        )
        for button in self.buttons:
            button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events[:]:
            if event.type in (
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
            ):
                for button in self.buttons:
                    button.handle_event(event)
                events.remove(event)
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.respawn_button.click()
                events.remove(event)

    def respawn(self) -> None:
        if not self.respawn_button.enabled:
            return
        self.respawn_button.enabled = False
        self.render.client.sent_packet({"__class__": "RequestRespawn"})

    def return_to_title(self) -> None:
        self.render.client.return_to_main_menu()

    def on_open(self) -> None:
        self.render.client.game_manager.acquire_game_input()
        self.render.request_text_input(False)

    def on_close(self) -> None:
        self.render.client.game_manager.release_game_input()
