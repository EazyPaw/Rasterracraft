# Commented and arranged by ChatGPT
from collections.abc import Callable

import pygame

from resources.server.utils import client_method


class Button:
    DEFAULT_SIZE = (400, 40)
    NORMAL_TEXTURE = "gui.sprites.widget.button"
    HOVER_TEXTURE = "gui.sprites.widget.button_highlighted"
    DISABLED_TEXTURE = "gui.sprites.widget.button_disabled"

    def __init__(
        self,
        text: str,
        callback: Callable[[], None] | None = None,
        *,
        size: tuple[int, int] = DEFAULT_SIZE,
        enabled: bool = True,
        visible: bool = True,
    ):
        self.text = text
        self.callback = callback
        self.default_size = size
        self.enabled = enabled
        self.visible = visible
        self.rect = pygame.Rect(0, 0, *size)
        self.hovered = False
        self.pressed = False

    def set_rect(self, x: int, y: int, width: int, height: int):
        self.rect = pygame.Rect(x, y, width, height)

    def contains(self, pos: tuple[int, int]) -> bool:
        return self.visible and self.rect.collidepoint(pos)

    @client_method
    def click(self, client=None):
        if self.enabled and self.callback is not None:
            # 回调可能会调用 pygame.quit()（例如主菜单的“退出”），
            # 因此先播放按键音效，避免在 pygame 关闭后访问混音器。
            client.resources_manager.play_sound("gui.button.press")
            self.callback()

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.visible:
            return False

        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.contains(event.pos)
            return self.hovered

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(event.pos):
                self.pressed = self.enabled
                return True

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_pressed = self.pressed
            self.pressed = False
            if self.contains(event.pos):
                if was_pressed:
                    self.click()
                return True

        return False

    def draw(self, render):
        if not self.visible:
            return

        texture_key = self.NORMAL_TEXTURE
        if not self.enabled:
            texture_key = self.DISABLED_TEXTURE
        elif self.hovered or self.pressed:
            texture_key = self.HOVER_TEXTURE

        texture = render.client.resources_manager.get_texture_img(texture_key)
        if texture is not None:
            texture = render.scale_surface(texture, self.rect.size)
            render.blit(texture, self.rect.topleft)
        else:
            self._draw_fallback(render)

        color = (255, 255, 160) if self.enabled and self.hovered else (255, 255, 255)
        if not self.enabled:
            color = (160, 160, 160)
        font_size = max(18, int(self.rect.height * 0.55))
        font = render.get_font(font_size)
        text_w, text_h = font.size(self.text)
        text_pos = (
            self.rect.centerx - text_w / 2,
            self.rect.centery - text_h / 2,
        )
        render.render_text(
            self.text, text_pos, color, font_size, shadow=True, shadow_strength=0.1
        )

    def _draw_fallback(self, render):
        base = (96, 96, 96) if self.enabled else (56, 56, 56)
        top = (180, 180, 180) if self.hovered and self.enabled else (150, 150, 150)
        render.draw_rect(base, self.rect)
        render.draw_line(top, self.rect.topleft, self.rect.topright, 2)
        render.draw_line(top, self.rect.topleft, self.rect.bottomleft, 2)
        render.draw_line((35, 35, 35), self.rect.bottomleft, self.rect.bottomright, 2)
        render.draw_line((35, 35, 35), self.rect.topright, self.rect.bottomright, 2)
