"""Minecraft 风格的单行文本输入框组件。

支持光标操作、文本选择、占位符、剪贴板粘贴，以及窗口大小自适应。
"""

from collections.abc import Callable

import pygame


class InputBox:
    """Minecraft 风格的单行文本输入框。

    特性：
    - 鼠标点击聚焦 / 失焦
    - 光标移动（方向键、Home/End、鼠标点击定位）
    - 退格 / 删除 / Ctrl+A / Ctrl+V 粘贴
    - 占位符文本（无内容时显示）
    - 标签文本（显示在输入框上方）
    - 字体大小与内边距随窗口尺寸自适应
    - 可选 Minecraft 纹理（回退至代码绘制的样式）
    """

    # ---- 默认尺寸与纹理键 ----
    DEFAULT_SIZE = (300, 40)
    NORMAL_TEXTURE = "gui.sprites.widget.text_field"                # 普通状态
    HIGHLIGHTED_TEXTURE = "gui.sprites.widget.text_field_highlighted"  # 聚焦/悬停状态

    def __init__(
        self,
        text: str = "",
        *,
        placeholder: str = "",
        label: str = "",
        size: tuple[int, int] = DEFAULT_SIZE,
        enabled: bool = True,
        visible: bool = True,
        max_length: int | None = 128,
        font_size: int = 0,
        placeholder_font_size: int | None = None,
        label_font_size: int | None = None,
        text_color: tuple[int, int, int] = (255, 255, 255),
        placeholder_color: tuple[int, int, int] = (110, 110, 110),
        label_color: tuple[int, int, int] = (255, 255, 255),
        disabled_text_color: tuple[int, int, int] = (160, 160, 160),
        padding: int = 0,
        on_change: Callable[[str], None] | None = None,
        on_submit: Callable[[str], None] | None = None,
    ):
        """
        参数:
            text: 初始文本内容
            placeholder: 占位符文本（输入框为空时显示）
            label: 标签文本（显示在输入框上方，为空则不显示）
            size: 组件尺寸 (宽, 高)
            enabled: 是否启用交互
            visible: 是否可见
            max_length: 最大字符数限制（None 为不限制）
            font_size: 正文字体大小（0 = 自动根据高度计算）
            placeholder_font_size: 占位符字体大小（None = 与正文相同）
            label_font_size: 标签字体大小（None = 与正文相同）
            text_color: 正文颜色
            placeholder_color: 占位符颜色
            label_color: 标签颜色
            disabled_text_color: 禁用状态下的文字颜色
            padding: 文本区域水平内边距（0 = 自动根据宽度计算）
            on_change: 文本变化回调，接收新文本
            on_submit: 回车提交回调，接收当前文本
        """
        self.placeholder = placeholder
        self.label = label
        self.default_size = size
        self.enabled = enabled
        self.visible = visible
        self.max_length = max_length
        if self.max_length is not None:
            text = text[:self.max_length]
        self.text = text

        # 字体与样式（0 / None 表示自动根据 rect 大小计算）
        self.font_size = font_size
        self.placeholder_font_size = placeholder_font_size
        self.label_font_size = label_font_size
        self.text_color = text_color
        self.placeholder_color = placeholder_color
        self.label_color = label_color
        self.disabled_text_color = disabled_text_color
        self.padding = padding

        self.on_change = on_change
        self.on_submit = on_submit

        # ---- 状态 ----
        self.rect = pygame.Rect(0, 0, *size)
        self.focused = False      # 是否已聚焦
        self.hovered = False      # 鼠标是否悬停在组件上
        self.cursor_pos = len(text)
        self._text_scroll = 0     # 水平滚动偏移（像素）
        self._last_cursor_toggle = 0
        self._cursor_visible = True
        self._metrics_font: pygame.font.Font | None = None

    # ===================== 自适应尺寸计算 =====================

    def _eff_font_size(self) -> int:
        """有效的正文字体大小（用户指定值 > 0 时优先，否则根据高度自动计算）。"""
        return self.font_size or max(12, min(48, int(self.rect.height * 0.55)))

    def _eff_placeholder_font_size(self) -> int:
        """有效的占位符字体大小（未指定时与正文相同）。"""
        return self.placeholder_font_size or self._eff_font_size()

    def _eff_label_font_size(self) -> int:
        """有效的标签字体大小（未指定时与正文相同）。"""
        return self.label_font_size or self._eff_font_size()

    def _eff_padding(self) -> int:
        """有效的水平内边距（用户指定值 > 0 时优先，否则根据宽度自动计算）。"""
        return self.padding or max(4, min(24, int(self.rect.width * 0.04)))

    # ===================== 布局 =====================

    def set_rect(self, x: int, y: int, width: int, height: int):
        """设置组件的位置和大小（会触发后续的自适应计算）。"""
        self.rect = pygame.Rect(x, y, width, height)

    def contains(self, pos: tuple[int, int]) -> bool:
        """判断给定坐标是否在组件范围内。"""
        return self.visible and self.rect.collidepoint(pos)

    # ===================== 文本操作 =====================

    def set_text(self, text: str, *, notify: bool = True):
        """设置文本内容并触发回调。

        参数:
            text: 新文本
            notify: 是否触发 on_change 回调
        """
        if self.max_length is not None:
            text = text[:self.max_length]
        self.text = text
        self.cursor_pos = len(self.text)
        if notify and self.on_change is not None:
            self.on_change(self.text)

    # ===================== 焦点管理 =====================

    def focus(self):
        """聚焦输入框，开始接收文本输入。"""
        if not self.enabled or not self.visible:
            return
        self.focused = True
        self._last_cursor_toggle = pygame.time.get_ticks()
        self._cursor_visible = True
        pygame.key.start_text_input()

    def blur(self):
        """失焦输入框，停止接收文本输入。"""
        if self.focused:
            self.focused = False
            pygame.key.stop_text_input()

    # ===================== 事件处理 =====================

    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件，返回 True 表示事件已被消费。"""
        if not self.visible:
            return False

        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.contains(event.pos)
            return self.hovered

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(event.pos):
                self.focus()
                self._set_cursor_from_mouse(event.pos)
                return True
            # 点击组件外部 → 失去焦点
            self.blur()
            return False

        if not self.enabled or not self.focused:
            return False

        if event.type == pygame.TEXTINPUT:
            self._insert_text(event.text)
            return True

        if event.type == pygame.KEYDOWN:
            return self._handle_keydown(event)

        return False

    # ===================== 绘制 =====================

    def draw(self, render):
        """绘制输入框：标签 → 背景框 → 文本 → 光标。"""
        if not self.visible:
            return

        if self.label:
            label_size = self._eff_label_font_size()
            label_y = self.rect.y - label_size - max(4, self.rect.height // 8)
            render.render_text(
                self.label,
                (self.rect.x, label_y),
                self.label_color if self.enabled else self.disabled_text_color,
                label_size,
                shadow=True,
                shadow_strength=0.1,
            )

        self._draw_box(render)
        self._draw_text(render)
        self._draw_cursor(render)

    def _draw_box(self, render):
        """绘制输入框背景（聚焦或悬停时高亮）。"""
        texture_key = self.HIGHLIGHTED_TEXTURE if self.focused or self.hovered else self.NORMAL_TEXTURE
        texture = render.client.resources_manager.get_texture_img(texture_key)
        if texture is not None:
            texture = render.scale_surface(texture, self.rect.size)
            render.blit(texture, self.rect.topleft)
            return

        # 无纹理时的回退绘制
        bg = (0, 0, 0)
        border = (255, 255, 255) if self.focused else (160, 160, 160)
        if not self.enabled:
            border = (90, 90, 90)
        render.draw_rect(bg, self.rect)
        render.draw_rect(border, self.rect, 2)

    def _draw_text(self, render):
        """绘制文本内容或占位符（支持水平滚动）。"""
        inner = self._inner_rect()
        font_size = self._eff_font_size()
        font = render.get_font(font_size)
        self._metrics_font = font

        if self.text:
            self._update_scroll(font, inner.width)
            draw_text = self.text
            color = self.text_color if self.enabled else self.disabled_text_color
            size = font_size
            offset = self._text_scroll
        else:
            draw_text = self.placeholder
            color = self.placeholder_color if self.enabled else self.disabled_text_color
            size = self._eff_placeholder_font_size()
            offset = 0

        if not draw_text:
            return

        font_obj = render.get_font(size)
        text_h = font_obj.get_height()
        y = inner.centery - text_h / 2
        render.render_text(
            draw_text,
            (inner.x - offset, y),
            color,
            size,
            shadow=False,
            clip_rect=inner,
        )

    def _draw_cursor(self, render):
        """绘制闪烁的光标竖线。"""
        if not self.focused or not self.enabled:
            return

        now = pygame.time.get_ticks()
        if now - self._last_cursor_toggle >= 530:
            self._cursor_visible = not self._cursor_visible
            self._last_cursor_toggle = now
        if not self._cursor_visible:
            return

        inner = self._inner_rect()
        font_size = self._eff_font_size()
        font = render.get_font(font_size)
        cursor_x = inner.x + font.size(self.text[:self.cursor_pos])[0] - self._text_scroll
        cursor_x = max(inner.x, min(inner.right - 1, cursor_x))
        cursor_top = inner.y + max(2, inner.height // 6)
        cursor_bottom = inner.bottom - max(2, inner.height // 6)
        render.draw_line((255, 255, 255), (cursor_x, cursor_top), (cursor_x, cursor_bottom), 2)

    # ===================== 键盘处理 =====================

    def _handle_keydown(self, event: pygame.event.Event) -> bool:
        """处理聚焦状态下的键盘事件。"""
        mods = pygame.key.get_mods()
        ctrl = bool(mods & pygame.KMOD_CTRL)

        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self.on_submit is not None:
                self.on_submit(self.text)
            return True
        if event.key == pygame.K_ESCAPE:
            self.blur()
            return True
        if event.key == pygame.K_BACKSPACE:
            if self.cursor_pos > 0:
                self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
                self.cursor_pos -= 1
                self._notify_change()
            return True
        if event.key == pygame.K_DELETE:
            if self.cursor_pos < len(self.text):
                self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]
                self._notify_change()
            return True
        if event.key == pygame.K_LEFT:
            self.cursor_pos = max(0, self.cursor_pos - 1)
            return True
        if event.key == pygame.K_RIGHT:
            self.cursor_pos = min(len(self.text), self.cursor_pos + 1)
            return True
        if event.key == pygame.K_HOME:
            self.cursor_pos = 0
            return True
        if event.key == pygame.K_END:
            self.cursor_pos = len(self.text)
            return True
        if ctrl and event.key == pygame.K_a:
            self.cursor_pos = len(self.text)
            return True
        if ctrl and event.key == pygame.K_v:
            clip = self._get_clipboard_text()
            if clip:
                self._insert_text(clip.replace("\r", "").replace("\n", ""))
            return True

        return True

    # ===================== 文本编辑辅助 =====================

    def _insert_text(self, text: str):
        """在光标位置插入文本。"""
        if not text:
            return
        if self.max_length is not None:
            remaining = self.max_length - len(self.text)
            if remaining <= 0:
                return
            text = text[:remaining]
        self.text = self.text[:self.cursor_pos] + text + self.text[self.cursor_pos:]
        self.cursor_pos += len(text)
        self._notify_change()

    def _set_cursor_from_mouse(self, pos: tuple[int, int]):
        """根据鼠标点击位置计算光标位置。"""
        inner = self._inner_rect()
        if self._metrics_font is None:
            self.cursor_pos = len(self.text)
            return
        local_x = max(0, pos[0] - inner.x + self._text_scroll)
        best = 0
        best_dist = float("inf")
        for i in range(len(self.text) + 1):
            dist = abs(self._metrics_font.size(self.text[:i])[0] - local_x)
            if dist < best_dist:
                best = i
                best_dist = dist
        self.cursor_pos = best

    def _update_scroll(self, font: pygame.font.Font, max_width: int):
        """更新水平滚动偏移，使光标始终可见。"""
        cursor_px = font.size(self.text[:self.cursor_pos])[0]
        if cursor_px - self._text_scroll < 0:
            self._text_scroll = cursor_px
        if cursor_px - self._text_scroll > max_width - 4:
            self._text_scroll = cursor_px - max_width + 4
        text_w = font.size(self.text)[0]
        if text_w - self._text_scroll < max_width:
            self._text_scroll = max(0, text_w - max_width)
        self._text_scroll = max(0, self._text_scroll)

    def _inner_rect(self) -> pygame.Rect:
        """返回文本区域（去除内边距后的矩形）。"""
        padding = self._eff_padding()
        # 将 padding 限制在合理范围，防止在小宽度下被挤出
        padding = min(padding, max(2, self.rect.width // 5))
        return pygame.Rect(
            self.rect.x + padding,
            self.rect.y + 2,
            max(1, self.rect.width - padding * 2),
            max(1, self.rect.height - 4),
        )

    def _notify_change(self):
        """触发 on_change 回调。"""
        if self.on_change is not None:
            self.on_change(self.text)

    # ===================== 剪贴板 =====================

    @staticmethod
    def _get_clipboard_text() -> str | None:
        """从系统剪贴板获取文本。"""
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            raw = pygame.scrap.get(pygame.SCRAP_TEXT)
            if raw:
                return raw.decode("utf-8", errors="ignore")
        except Exception:
            return None
        return None
