"""Developer-only GUI for executing Python in the client context."""

import traceback

import pygame

from src.client.GUI.button import Button
from src.client.GUI.gui import GUI
from src.client.GUI.input_box import InputBox


class DebugExecGUI(GUI):
    """Small in-game Python console available only in development mode."""

    def __init__(self, render):
        super().__init__(render)
        self.priority = 100_000
        self._owns_game_input = False
        self.result_text = ""
        self.result_color = (180, 180, 180)
        self.code_box = InputBox(
            "client",
            label="Python code",
            placeholder="Enter an expression or statement",
            max_length=23_767,
            on_change=self._on_code_changed,
            on_submit=self.client_exec,
        )
        self.address_box = self.code_box
        self.submit_button = Button("Run", self.client_exec, enabled=True)
        self.cancel_button = Button("Cancel", self.back)
        self.buttons = (self.submit_button, self.cancel_button)

    def _on_code_changed(self, code: str) -> None:
        self.submit_button.enabled = bool(code.strip())

    def _layout(self) -> None:
        width, height = self.render.screen.get_size()
        content_width = max(300, min(760, int(width * 0.72)))
        input_height = max(38, min(54, int(height * 0.065)))
        self.code_box.set_rect(
            (width - content_width) // 2,
            max(110, int(height * 0.36)),
            content_width,
            input_height,
        )

        gap = max(8, int(content_width * 0.015))
        button_height = max(36, min(48, int(height * 0.058)))
        button_width = (content_width - gap) // 2
        button_y = self.code_box.rect.bottom + max(22, input_height // 2)
        self.submit_button.set_rect(
            self.code_box.rect.x, button_y, button_width, button_height
        )
        self.cancel_button.set_rect(
            self.code_box.rect.x + button_width + gap,
            button_y,
            content_width - button_width - gap,
            button_height,
        )

    def draw(self) -> None:
        width, height = self.render.screen.get_size()
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.render.blit(overlay, (0, 0))
        self._layout()

        title = "Client Python Executor"
        title_size = max(26, min(42, height // 16))
        title_width = self.render.get_font(title_size).size(title)[0]
        self.render.render_text(
            title,
            ((width - title_width) / 2, int(height * 0.20)),
            (255, 255, 255),
            title_size,
            shadow=True,
            shadow_strength=0.1,
        )
        self.code_box.draw(self.render)
        for button in self.buttons:
            button.draw(self.render)

        if self.result_text:
            result_size = max(15, min(22, height // 34))
            self.render.render_text(
                self.result_text,
                (self.code_box.rect.x, self.cancel_button.rect.bottom + 16),
                self.result_color,
                result_size,
                shadow=True,
                shadow_strength=0.1,
                clip_rect=pygame.Rect(
                    self.code_box.rect.x,
                    self.cancel_button.rect.bottom + 12,
                    self.code_box.rect.width,
                    max(1, height - self.cancel_button.rect.bottom - 20),
                ),
            )

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        for event in events[:]:
            handled = self.code_box.handle_event(event)
            if event.type in (
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
            ):
                for button in self.buttons:
                    handled = button.handle_event(event) or handled
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_F8):
                    self.back()
                handled = True
            if handled and event in events:
                events.remove(event)

    def client_exec(self, code: str | None = None) -> None:
        if code is None:
            code = self.code_box.text
        code = code.strip()
        if not code:
            return

        client = self.render.client
        namespace = {"client": client, "render": self.render, "pygame": pygame}
        try:
            try:
                result = eval(code, namespace, namespace)
            except SyntaxError:
                exec(code, namespace, namespace)
                result = None
            self.result_text = (
                "Executed successfully" if result is None else repr(result)
            )
            self.result_color = (120, 255, 120)
        except Exception:
            self.result_text = traceback.format_exc().strip().splitlines()[-1]
            self.result_color = (255, 110, 110)

    def back(self) -> None:
        self.render.close_gui(self)

    def on_open(self) -> None:
        if not getattr(self.render.client, "under_dev", False):
            self.render.close_gui(self)
            return
        self.render.client.game_manager.acquire_game_input()
        self._owns_game_input = True
        self.code_box.focus()
        self.render.request_text_input(True, repeat=(400, 30))

    def on_close(self) -> None:
        self.code_box.blur()
        if self._owns_game_input:
            self.render.client.game_manager.release_game_input()
            self._owns_game_input = False
