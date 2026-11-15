# Commented and arranged by ChatGPT
from src.client.GUI.menu_style import gui_scale

import pygame

from src.client.GUI.button import Button
from src.client.GUI.gui import GUI
from src.client.resources_manager import transkey


class PauseMenu(GUI):
    def __init__(self, render):
        super().__init__(render)
        self.priority = 90
        self.buttons = [
            Button(transkey("menu.returnToGame"), self.resume_game),
            Button(transkey("mods.title"), self.open_mods),
            Button(transkey("menu.returnToMenu"), self.return_to_menu),
        ]

    def draw(self):
        self._layout_buttons()
        overlay = pygame.Surface(
            (self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        overlay.fill((0, 0, 0, 120))
        self.render.blit(overlay, (0, 0))
        for button in self.buttons:
            button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]):
        for event in events[:]:
            handled = False
            if event.type in (
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
            ):
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

    def open_mods(self):
        from src.client.GUI.mods_menu import ModsMenu
        self.render.close_gui(self)
        self.render.show_gui(ModsMenu(self.render, self))

    def return_to_menu(self):
        self.render.close_gui(self)
        self.render.client.return_to_main_menu()

    def on_open(self):
        self.render.client.game_manager.acquire_game_input()
        self.render.request_text_input(False)

    def on_close(self):
        self.render.client.game_manager.release_game_input()

    def _layout_buttons(self):
        s = gui_scale(self.render)
        w, h = self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT
        width, height, gap = min(200 * s, w - 24), 20 * s, 4 * s
        y = (h - len(self.buttons) * (height + gap) + gap) // 2
        for button in self.buttons:
            button.set_rect((w - width) // 2, y, width, height)
            y += height + gap
