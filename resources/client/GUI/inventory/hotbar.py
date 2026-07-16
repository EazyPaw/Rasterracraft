import logging
import time

from resources.client.GUI.gui import GUI


class HotBar(GUI):
    _texture_path = "gui.sprites.hud.hotbar"

    def __init__(self, render):
        super().__init__(render)
        self.bar_height = 22
        self.bar_width = 182
        self.selection_texture = self.get_texture(self.render.gui_scale, self.render.client, "gui.sprites.hud.hotbar_selection")
        self._item_name = ""
        self._item_name_fade_starts_at = 0.0
        self._item_name_expires_at = 0.0

    def show_item_name(self, name: str, duration: float = 1.6, fade_duration: float = 0.4):
        """显示名称；新名称会立即替换旧名称并重置显示时间。"""
        self._item_name = str(name).strip()
        if not self._item_name:
            self._item_name_fade_starts_at = 0.0
            self._item_name_expires_at = 0.0
            return

        now = time.monotonic()
        self._item_name_fade_starts_at = now + duration
        self._item_name_expires_at = self._item_name_fade_starts_at + fade_duration

    def draw(self):
        self._draw_hotbar()
        self.draw_item_name()

    def _draw_hotbar(self):
        # 竞态条件保护：start_game() 在另一个线程中将 HotBar 添加到
        # drawing_GUIs，但 client_player 的赋值可能尚未完成。
        if self.render.client.client_player is None:
            return

        texture = self.get_texture(self.render.gui_scale, self.render.client)

        x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        y = self.render.SCREEN_HEIGHT - texture.get_height()

        self.render.blit(texture, (x, y))

        slot_width = (self.render.gui_scale * self.bar_width - 6) / 9
        x_start = x + self.render.gui_scale * self.bar_width / 36

        for i in range(9):
            item = self.render.client.client_player.inventory[i]
            # 计算当前槽位的起始x坐标
            slot_x = x_start + i * slot_width

            # 绘制选择框
            if self.render.client.client_player.selected_slot == i:
                sx = x + i * slot_width - self.render.gui_scale
                sy = y - self.render.gui_scale
                self.render.blit(self.selection_texture, (sx, sy))

            if item.is_empty():
                continue
            texture_ = item.get_texture(self.render.gui_scale * 0.7, shadow=True)

            if texture_ is None:
                continue

            # 物品在槽位内水平居中
            item_x = slot_x + (slot_width - texture_.get_width()) / 2 - self.render.gui_scale * self.bar_width / 48

            # 物品在槽位内垂直居中
            item_y = y + self.render.gui_scale * self.bar_height / 2 - texture_.get_height() / 2

            self.render.blit(texture_, (item_x, item_y))

            # 绘制物品数量
            if item.amount > 1:
                a = self.render.get_font(20).render(str(item.amount), True, (255, 255, 255))
                c = len(str(abs(item.amount))) - 1 # 物品数量位数，用于确定偏移量
                self.render.screen.blit(a, (x + (i + 1) * slot_width - self.render.gui_scale * (4 + c * 4), y + self.render.gui_scale * 15))

    def draw_item_name(self, bottom_y: float | None = None):
        """在屏幕中下方绘制物品名称，并在结束前渐隐。"""
        now = time.monotonic()
        if not self._item_name or now >= self._item_name_expires_at:
            return

        fade_duration = max(0.001, self._item_name_expires_at - self._item_name_fade_starts_at)
        alpha = 255
        if now >= self._item_name_fade_starts_at:
            alpha = round(255 * (self._item_name_expires_at - now) / fade_duration)

        window_scale = min(self.render.SCREEN_WIDTH / 800, self.render.SCREEN_HEIGHT / 600)
        font_size = max(14, min(36, round(18 * window_scale)))
        font = self.render.get_font(font_size)
        text = font.render(self._item_name, True, (255, 255, 255))
        shadow = font.render(self._item_name, True, (0, 0, 0))
        text.set_alpha(alpha)
        shadow.set_alpha(round(alpha * 0.7))

        # 使用窗口比例而非固定像素：无论分辨率如何都保持在中下方。
        y = int(self.render.SCREEN_HEIGHT * 0.8)
        if bottom_y is not None:
            y = min(y, int(bottom_y - font_size))
        position = text.get_rect(center=(self.render.SCREEN_WIDTH // 2, y))
        shadow_position = position.move(max(1, font_size // 10), max(1, font_size // 10))
        self.render.screen.blit(shadow, shadow_position)
        self.render.screen.blit(text, position)



