import pygame

from resources.client.GUI.button import Button
from resources.client.GUI.gui import GUI
from resources.client.resources_manager import transkey


class PauseMenu(GUI):
    def __init__(self, render):
        super().__init__(render)
        self.priority = 90
        self.buttons = [
            Button(transkey("menu.returnToGame"), self.resume_game),
            Button(transkey("menu.returnToMenu"), self.return_to_menu),
        ]

    def draw(self):
        self._layout_buttons()
        overlay = pygame.Surface((self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.render.blit(overlay, (0, 0))
        for button in self.buttons:
            button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]):
        for event in events[:]:
            handled = False
            if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                for button in self.buttons:
                    if button.handle_event(event):
                        handled = True
                if handled:
                    events.remove(event)
                    continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.resume_game()
                events.remove(event)

    def resume_game(self):
        self.render.close_gui(self)

    def return_to_menu(self):
        self.render.close_gui(self)
        self.render.client.return_to_main_menu()

    def on_open(self):
        self.render.client.game_manager.ing_mouse_lock += 1
        pygame.key.stop_text_input()

    def on_close(self):
        self.render.client.game_manager.ing_mouse_lock = max(
            0,
            self.render.client.game_manager.ing_mouse_lock - 1,
        )

    def _layout_buttons(self):
        screen_w = self.render.SCREEN_WIDTH
        screen_h = self.render.SCREEN_HEIGHT
        button_w = max(220, min(420, int(screen_w * 0.36)))
        button_h = max(34, min(48, int(screen_h * 0.06)))
        gap = max(8, int(button_h * 0.35))
        total_h = len(self.buttons) * button_h + (len(self.buttons) - 1) * gap
        y = (screen_h - total_h) // 2
        for button in self.buttons:
            button.set_rect((screen_w - button_w) // 2, y, button_w, button_h)
            y += button_h + gap
