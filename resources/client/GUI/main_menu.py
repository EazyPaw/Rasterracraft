import pygame

from resources.client.GUI.button import Button
from resources.client.GUI.gui import GUI
from resources.client.GUI.saves_menu import SavesMenu
from resources.client.resources_manager import transkey


class MainMenu(GUI):
    """Minecraft-style title menu with extensible button registration."""

    def __init__(self, render):
        super().__init__(render)
        self.priority = 100
        self.buttons: list[Button] = []
        self.starting_world = False
        self._background_cache = None
        self._background_cache_key = None
        self.add_button(transkey("menu.singleplayer"), self.start_singleplayer)

    def add_button(
        self,
        text: str,
        callback=None,
        *,
        size: tuple[int, int] = Button.DEFAULT_SIZE,
        enabled: bool = True,
        visible: bool = True,
    ) -> Button:
        """Register a menu button. Future GUIs can hook into this method."""
        button = Button(text, callback, size=size, enabled=enabled, visible=visible)
        self.buttons.append(button)
        return button

    def clear_buttons(self):
        self.buttons.clear()

    def start_singleplayer(self):
        if self.starting_world:
            return
        self.render.close_gui(self)
        self.render.client.saves_menu = SavesMenu(self.render, self)
        self.render.show_gui(self.render.client.saves_menu)

    def draw(self):
        self._layout_buttons()
        self._draw_background()
        self._draw_logo()
        for button in self.buttons:
            button.draw(self.render)
        self._draw_footer()

    def handle_events(self, events: list[pygame.event.Event]):
        for event in events[:]:
            if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                handled = False
                for button in self.buttons:
                    if button.handle_event(event):
                        handled = True
                if handled and event in events:
                    events.remove(event)
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                for button in self.buttons:
                    if button.enabled and button.visible:
                        button.click()
                        events.remove(event)
                        break

    def _layout_buttons(self):
        screen_w = self.render.SCREEN_WIDTH
        screen_h = self.render.SCREEN_HEIGHT

        # 按钮尺寸与窗口成比例缩放，并设置合理的上下限
        button_w = max(180, min(400, int(screen_w * 0.35)))
        button_h = max(28, min(48, int(screen_h * 0.055)))
        gap = max(4, int(button_h * 0.3))

        visible_buttons = [b for b in self.buttons if b.visible]
        if not visible_buttons:
            return

        button_sizes = [
            (button_w, button_h)
            if button.default_size == Button.DEFAULT_SIZE
            else button.default_size
            for button in visible_buttons
        ]
        total_h = sum(size[1] for size in button_sizes) + gap * (len(visible_buttons) - 1)

        # 按钮区域：屏幕 38%~65% 的垂直区间，按钮组在该区域内居中
        button_zone_top = int(screen_h * 0.38)
        button_zone_bottom = int(screen_h * 0.68)
        button_zone_height = button_zone_bottom - button_zone_top
        y = button_zone_top + (button_zone_height - total_h) // 2

        # 确保按钮组不会超出屏幕底部
        if y + total_h > screen_h - int(screen_h * 0.05):
            y = screen_h - int(screen_h * 0.05) - total_h

        for button, (width, height) in zip(visible_buttons, button_sizes):
            button.set_rect((screen_w - width) // 2, y, width, height)
            y += height + gap

    def _draw_background(self):
        cache_key = (self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT)
        if self._background_cache is None or self._background_cache_key != cache_key:
            self._background_cache = self._build_background()
            self._background_cache_key = cache_key
        self.render.blit(self._background_cache, (0, 0))

    def _build_background(self):
        width = self.render.SCREEN_WIDTH
        height = self.render.SCREEN_HEIGHT
        surface = self.render.create_surface((width, height), convert=True)
        dirt = self.render.client.resources_manager.get_texture_img("blocks.dirt")
        # 背景 tile 大小随窗口尺寸自适应（取短边的 1/12，限制在 32~128 之间）
        tile_size = max(32, min(128, min(width, height) // 12))
        tile = self.render.scale_surface(dirt, (tile_size, tile_size))
        for x in range(0, width, tile_size):
            for y in range(0, height, tile_size):
                self.render.blit_to(surface, tile, (x, y))
        shade = self.render.create_surface((width, height), alpha=True)
        self.render.fill_surface(shade, (0, 0, 0, 115))
        self.render.blit_to(surface, shade, (0, 0))
        return surface

    def _draw_logo(self):
        screen_w = self.render.SCREEN_WIDTH
        screen_h = self.render.SCREEN_HEIGHT
        logo = self.render.client.resources_manager.get_texture_img("gui.title.minecraft", True)

        # Logo 区域：屏幕顶部 ~35% 的空间，Logo 在其中居中
        logo_zone_height = int(screen_h * 0.35)

        # 按 Logo 区域等比缩放：不超过屏幕宽度的 70%、不超过 Logo 区域高度的 85%
        max_w = int(screen_w * 0.50)
        max_h = int(logo_zone_height * 0.60)
        scale_w = max_w / logo.get_width()
        scale_h = max_h / logo.get_height()
        # 取宽高约束中较小的缩放比，同时限制最大放大倍数防止过度模糊
        scale = min(scale_w, scale_h, 2.5)
        logo_w = int(logo.get_width() * scale)
        logo_h = int(logo.get_height() * scale)
        logo_surface = self.render.scale_surface(logo, (logo_w, logo_h))

        # 在 Logo 区域内居中
        x = (screen_w - logo_w) // 2
        y = (logo_zone_height - logo_h) // 2
        self.render.blit(logo_surface, (x, y))

    def _draw_footer(self):
        version = getattr(self.render.client, "version", "")
        footer_font_size = max(16, int(self.render.SCREEN_HEIGHT * 0.026))
        y = self.render.SCREEN_HEIGHT - footer_font_size - 8
        self.render.render_text(f"PyCraft 2D {version}", (8, y), (255, 255, 255), footer_font_size, True)
        copyright_text = "Minecraft assets by Mojang Studios"
        font = self.render.get_font(footer_font_size)
        x = self.render.SCREEN_WIDTH - font.size(copyright_text)[0] - 8
        self.render.render_text(copyright_text, (x, y), (255, 255, 255), footer_font_size, True)
