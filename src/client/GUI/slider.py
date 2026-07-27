# Commented and arranged by ChatGPT
"""Minecraft 风格的横向滑动条组件。

提供可拖拽的滑动条，支持鼠标拖拽、键盘微调、自定义格式化显示。
"""

from collections.abc import Callable

import pygame


class Slider:
    """Minecraft 风格的横向滑动条。

    特性：
    - 鼠标拖拽滑块调整数值
    - 点击轨道快速跳转
    - 键盘左右方向键微调（聚焦后）
    - 自定义数值格式化与显示文本
    - 可选 Minecraft 纹理（回退至代码绘制的样式）
    """

    # ---- 默认尺寸与纹理键 ----
    DEFAULT_SIZE = (300, 40)
    NORMAL_TEXTURE = "gui.sprites.widget.slider"  # 轨道 - 普通
    HIGHLIGHTED_TEXTURE = "gui.sprites.widget.slider_highlighted"  # 轨道 - 悬停
    HANDLE_TEXTURE = "gui.sprites.widget.slider_handle"  # 滑块 - 普通
    HANDLE_HIGHLIGHTED_TEXTURE = (
        "gui.sprites.widget.slider_handle_highlighted"  # 滑块 - 悬停/聚焦
    )

    def __init__(
        self,
        label: str,
        *,
        min_value: float = 0.0,
        max_value: float = 1.0,
        value: float = 0.0,
        step: float = 0.01,
        size: tuple[int, int] = DEFAULT_SIZE,
        enabled: bool = True,
        visible: bool = True,
        formatter: Callable[[float], str] | None = None,
        display: str | Callable[["Slider"], str] | None = None,
        on_change: Callable[[float], None] | None = None,
        font_size: int | None = None,
        text_color: tuple[int, int, int] = (255, 255, 255),
        disabled_text_color: tuple[int, int, int] = (160, 160, 160),
    ):
        """初始化横向滑动条。

        :param label: 滑动条标签。
        :param min_value: 最小值。
        :param max_value: 最大值。
        :param value: 初始值。
        :param step: 每次微调的增量；小于等于 0 时不限制步长。
        :param size: 组件尺寸，格式为“宽、高”。
        :param enabled: 是否允许交互。
        :param visible: 是否绘制组件。
        :param formatter: 接收数值并返回显示文本的格式化函数。
        :param display: 显示模板或回调；模板支持 label、value、value_text
            与 percent 占位符。
        :param on_change: 数值变更回调，参数为新数值。
        :param font_size: 标签字体大小；None 表示自动计算。
        :param text_color: 标签文字颜色。
        :param disabled_text_color: 禁用状态的标签文字颜色。
        """
        self.label = label
        self.min_value = min_value
        self.max_value = max_value
        self.step = step
        self.default_size = size
        self.enabled = enabled
        self.visible = visible
        self.formatter = formatter
        self.display = display
        self.on_change = on_change
        self.font_size = font_size
        self.text_color = text_color
        self.disabled_text_color = disabled_text_color

        # ---- 状态 ----
        self.rect = pygame.Rect(0, 0, *size)
        self.hovered = False  # 鼠标是否悬停在组件上
        self.focused = False  # 是否已聚焦（点击后获得，点击外部失去）
        self.dragging = False  # 是否正在拖拽滑块
        self.value = self._snap(self._clamp(value))

    # ===================== 布局 =====================

    def set_rect(self, x: int, y: int, width: int, height: int):
        """设置组件的位置和大小。"""
        self.rect = pygame.Rect(x, y, width, height)

    def contains(self, pos: tuple[int, int]) -> bool:
        """判断给定坐标是否在组件范围内。"""
        return self.visible and self.rect.collidepoint(pos)

    # ===================== 数值访问 =====================

    @property
    def percent(self) -> float:
        """当前值在 min~max 范围内的百分比 [0.0, 1.0]。"""
        span = self.max_value - self.min_value
        if span == 0:
            return 0.0
        return (self.value - self.min_value) / span

    def set_value(self, value: float, *, notify: bool = True):
        """设置新值并触发回调。

        :param value: 新值
        :param notify: 是否触发 on_change 回调

        """
        new_value = self._snap(self._clamp(value))
        if new_value == self.value:
            return
        self.value = new_value
        if notify and self.on_change is not None:
            self.on_change(self.value)

    # ===================== 事件处理 =====================

    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件，返回 True 表示事件已被消费。"""
        if not self.visible:
            return False

        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.contains(event.pos)
            if self.dragging and self.enabled:
                self._set_value_from_mouse(event.pos[0])
                return True
            return self.hovered

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(event.pos):
                self.focused = True
                if self.enabled:
                    self.dragging = True
                    self._set_value_from_mouse(event.pos[0])
                return True
            # 点击组件外部 → 失去焦点
            self.focused = False
            return False

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging:
                self.dragging = False
                return True

        if event.type == pygame.KEYDOWN and self.focused and self.enabled:
            return self._handle_keydown(event)

        return False

    # ===================== 绘制 =====================

    def draw(self, render):
        """绘制滑动条：轨道 → 滑块 → 标签文本。"""
        if not self.visible:
            return

        self._draw_track(render)
        self._draw_handle(render)
        self._draw_label(render)

    def _draw_track(self, render):
        """绘制轨道背景（高亮仅在悬停时生效，聚焦不高亮轨道）。"""
        # 轨道高亮仅在鼠标悬停时触发，聚焦时不高亮整个轨道
        texture_key = self.HIGHLIGHTED_TEXTURE if self.hovered else self.NORMAL_TEXTURE
        texture = render.client.resources_manager.get_texture_img(texture_key)
        if texture is not None:
            texture = render.scale_surface(texture, self.rect.size)
            render.blit(texture, self.rect.topleft)
            return

        # 无纹理时的回退绘制
        render.draw_rect((32, 32, 32), self.rect)
        render.draw_rect((0, 0, 0), self.rect, 3)
        render.draw_line((140, 140, 140), self.rect.topleft, self.rect.topright, 2)
        render.draw_line((140, 140, 140), self.rect.topleft, self.rect.bottomleft, 2)

    def _draw_handle(self, render):
        """绘制滑块手柄（悬停、拖拽或聚焦时高亮）。"""
        handle_rect = self._handle_rect()
        # 滑块高亮：悬停、拖拽或聚焦时均亮起
        texture_key = (
            self.HANDLE_HIGHLIGHTED_TEXTURE
            if self.hovered or self.dragging or self.focused
            else self.HANDLE_TEXTURE
        )
        texture = render.client.resources_manager.get_texture_img(texture_key)
        if texture is not None:
            texture = render.scale_surface(texture, handle_rect.size)
            render.blit(texture, handle_rect.topleft)
            return

        # 无纹理时的回退绘制
        color = (190, 190, 190) if self.enabled else (110, 110, 110)
        render.draw_rect(color, handle_rect)
        render.draw_rect((0, 0, 0), handle_rect, 2)

    def _draw_label(self, render):
        """绘制标签文本（居中显示在轨道上方）。"""
        text = self.get_display_text()
        size = self.font_size or max(16, int(self.rect.height * 0.55))
        font = render.get_font(size)
        text_w, text_h = font.size(text)
        text_pos = (
            self.rect.centerx - text_w / 2,
            self.rect.centery - text_h / 2,
        )
        color = self.text_color if self.enabled else self.disabled_text_color
        render.render_text(
            text, text_pos, color, size, shadow=True, shadow_strength=0.1
        )

    # ===================== 显示文本 =====================

    def get_display_text(self) -> str:
        """获取最终的显示文本。

        优先级: display 回调 > display 格式化字符串 > 默认 "{label}: {value}"
        """
        if callable(self.display):
            return self.display(self)
        if isinstance(self.display, str):
            try:
                return self.display.format(
                    label=self.label,
                    value=self.value,
                    value_text=self.format_value(),
                    percent=int(round(self.percent * 100)),
                )
            except (KeyError, ValueError):
                return self.display
        return f"{self.label}: {self.format_value()}"

    def format_value(self) -> str:
        """格式化数值为显示字符串（整数不显示小数）。"""
        if self.formatter is not None:
            return self.formatter(self.value)
        if float(self.value).is_integer():
            return str(int(self.value))
        return f"{self.value:.2f}".rstrip("0").rstrip(".")

    # ===================== 键盘交互 =====================

    def _handle_keydown(self, event: pygame.event.Event) -> bool:
        """处理聚焦状态下的键盘事件。"""
        delta = self.step if self.step > 0 else (self.max_value - self.min_value) / 100
        if event.key == pygame.K_LEFT:
            self.set_value(self.value - delta)
            return True
        if event.key == pygame.K_RIGHT:
            self.set_value(self.value + delta)
            return True
        if event.key == pygame.K_HOME:
            self.set_value(self.min_value)
            return True
        if event.key == pygame.K_END:
            self.set_value(self.max_value)
            return True
        return False

    # ===================== 鼠标 → 数值 =====================

    def _set_value_from_mouse(self, mouse_x: int):
        """根据鼠标 X 坐标计算并设置对应值。"""
        handle_w = self._handle_width()
        usable = max(1, self.rect.width - handle_w)  # 滑块可移动的有效宽度
        local = mouse_x - self.rect.x - handle_w / 2  # 鼠标相对于滑块中心的位置
        pct = max(0.0, min(1.0, local / usable))  # 转换为百分比
        self.set_value(self.min_value + pct * (self.max_value - self.min_value))

    # ===================== 滑块几何 =====================

    def _handle_rect(self) -> pygame.Rect:
        """返回滑块当前的矩形区域。"""
        handle_w = self._handle_width()
        usable = max(1, self.rect.width - handle_w)
        x = self.rect.x + int(round(usable * self.percent))
        return pygame.Rect(x, self.rect.y, handle_w, self.rect.height)

    def _handle_width(self) -> int:
        """滑块宽度（高度 × 0.28，限制在 8~24 像素之间）。"""
        return max(8, min(24, int(self.rect.height * 0.28)))

    # ===================== 数值工具 =====================

    def _clamp(self, value: float) -> float:
        """将值限制在 min_value ~ max_value 范围内。"""
        low = min(self.min_value, self.max_value)
        high = max(self.min_value, self.max_value)
        return max(low, min(high, value))

    def _snap(self, value: float) -> float:
        """按步长对齐数值（step <= 0 时不处理）。"""
        if self.step <= 0:
            return value
        snapped = (
            self.min_value + round((value - self.min_value) / self.step) * self.step
        )
        snapped = self._clamp(snapped)
        return round(snapped, 10)
