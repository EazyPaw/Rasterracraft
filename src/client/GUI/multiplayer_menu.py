import pygame

from src.client.GUI.button import Button
from src.client.GUI.gui import GUI
from src.client.GUI.input_box import InputBox
from src.client.resources_manager import transkey
from src.server.utils import client_method


class MultiplayerMenu(GUI):
    """输入服务器地址并发起多人游戏连接的页面。"""

    @client_method
    def __init__(self, render, main_menu=None, client=None):
        super().__init__(render)
        self.client = client
        self.priority = 100
        self.main_menu = main_menu
        self.connecting = False
        self.error_message = ""
        self._background_cache = None
        self._background_cache_key = None

        self.address_box = InputBox(
            "",
            label=transkey("addServer.enterIp"),
            max_length=253,
            on_change=self._on_address_changed,
            on_submit=lambda _text: self.connect(),
        )
        self.connect_button = Button(
            transkey("selectServer.select"), self.connect, enabled=False
        )
        self.cancel_button = Button(transkey("gui.cancel"), self.back)
        self.buttons = [self.connect_button, self.cancel_button]

    def on_open(self):
        self.address_box.focus()

    def on_close(self):
        self.address_box.blur()

    def draw(self):
        self._layout()
        self._draw_background()
        self._draw_title()
        self.address_box.draw(self.render)
        self._draw_error()
        for button in self.buttons:
            button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]):
        self._layout()
        for event in events[:]:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.back()
                events.remove(event)
                continue

            if self.address_box.handle_event(event):
                events.remove(event)
                continue

            if event.type in (
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
            ):
                handled = False
                for button in self.buttons:
                    if button.handle_event(event):
                        handled = True
                if handled:
                    events.remove(event)
                    continue

            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN,
                pygame.K_KP_ENTER,
            ):
                self.connect()
                events.remove(event)

    def connect(self):
        if self.connecting:
            return
        address = self.address_box.text.strip()
        try:
            self.client.parse_server_address(address)
        except ValueError:
            self.error_message = transkey("pycraft.multiplayer.invalidAddress")
            self._update_connect_button()
            return

        self.connecting = True
        self.error_message = ""
        self.address_box.enabled = False
        self.address_box.blur()
        self.connect_button.enabled = False
        self.cancel_button.enabled = False
        self.client.start_multiplayer(address)

    def back(self):
        if self.connecting:
            return
        self.render.close_gui(self)
        if self.main_menu is not None:
            self.render.show_gui(self.main_menu)

    def _on_address_changed(self, _text: str):
        self.error_message = ""
        self._update_connect_button()

    def _update_connect_button(self):
        self.connect_button.enabled = bool(self.address_box.text.strip()) and not (
            self.connecting
        )

    def _layout(self):
        width = self.render.SCREEN_WIDTH
        height = self.render.SCREEN_HEIGHT
        content_width = min(720, max(320, int(width * 0.58)))
        field_height = max(36, min(54, int(height * 0.065)))
        field_y = int(height * 0.42)
        self.address_box.set_rect(
            (width - content_width) // 2,
            field_y,
            content_width,
            field_height,
        )

        gap = max(8, int(width * 0.012))
        button_height = max(34, min(50, int(height * 0.06)))
        button_y = field_y + field_height + max(60, int(height * 0.10))
        button_width = (content_width - gap) // 2
        self.connect_button.set_rect(
            (width - content_width) // 2,
            button_y,
            button_width,
            button_height,
        )
        self.cancel_button.set_rect(
            self.connect_button.rect.right + gap,
            button_y,
            button_width,
            button_height,
        )

    def _draw_background(self):
        key = (self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT)
        if self._background_cache is None or self._background_cache_key != key:
            width, height = key
            surface = self.render.create_surface((width, height), convert=True)
            dirt = self.render.client.resources_manager.get_texture_img(
                "blocks.dirt"
            )
            tile_size = max(32, min(128, min(width, height) // 12))
            tile = self.render.scale_surface(dirt, (tile_size, tile_size))
            for x in range(0, width, tile_size):
                for y in range(0, height, tile_size):
                    self.render.blit_to(surface, tile, (x, y))
            shade = self.render.create_surface((width, height), alpha=True)
            self.render.fill_surface(shade, (0, 0, 0, 145))
            self.render.blit_to(surface, shade, (0, 0))
            self._background_cache = surface
            self._background_cache_key = key
        self.render.blit(self._background_cache, (0, 0))

    def _draw_title(self):
        text = transkey("selectServer.direct")
        font_size = max(26, min(44, int(self.render.SCREEN_HEIGHT * 0.055)))
        font = self.render.get_font(font_size)
        x = (self.render.SCREEN_WIDTH - font.size(text)[0]) // 2
        y = int(self.render.SCREEN_HEIGHT * 0.20)
        self.render.render_text(
            text, (x, y), (255, 255, 255), font_size, shadow=True
        )

    def _draw_error(self):
        if not self.error_message:
            return
        font_size = max(18, min(28, int(self.render.SCREEN_HEIGHT * 0.032)))
        font = self.render.get_font(font_size)
        x = (self.render.SCREEN_WIDTH - font.size(self.error_message)[0]) // 2
        y = self.address_box.rect.bottom + max(10, int(font_size * 0.45))
        self.render.render_text(
            self.error_message, (x, y), (255, 85, 85), font_size, shadow=True
        )
