import logging

from resources.client.GUI.gui import GUI


class HotBar(GUI):
    _texture_path = "gui.sprites.hud.hotbar"

    def __init__(self, render):
        super().__init__(render)
        self.bar_height = 22
        self.bar_width = 182
        self.selection_texture = self.get_texture(self.render.gui_scale, self.render.client, "gui.sprites.hud.hotbar_selection")

    def draw(self):
        texture = self.get_texture(self.render.gui_scale, self.render.client)

        x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        y = self.render.SCREEN_HEIGHT - texture.get_height()

        self.render.blit(texture, (x, y))

        slot_width = (self.render.gui_scale * self.bar_width - 6) / 9
        x_start = x + self.render.gui_scale * self.bar_width / 36

        for i in range(9):
            item = self.render.client.client_player.inventory[i]
            if item.is_empty():
                continue
            texture_ = item.get_texture(self.render.gui_scale * 0.7, shadow=True)

            if texture_ is None:
                continue

            # 计算当前槽位的起始x坐标
            slot_x = x_start + i * slot_width

            # 物品在槽位内水平居中
            item_x = slot_x + (slot_width - texture_.get_width()) / 2 - self.render.gui_scale * self.bar_width / 48

            # 物品在槽位内垂直居中
            item_y = y + self.render.gui_scale * self.bar_height / 2 - texture_.get_height() / 2

            self.render.blit(texture_, (item_x, item_y))

            # 绘制选择框
            if self.render.client.client_player.selected_slot == i:
                sx = x + i * slot_width - self.render.gui_scale
                sy = y - self.render.gui_scale
                self.render.blit(self.selection_texture, (sx, sy))

            # 绘制物品数量
            if item.amount > 1:
                a = self.render.get_font(20).render(str(item.amount), True, (255, 255, 255))
                c = len(str(abs(item.amount))) - 1 # 物品数量位数，用于确定偏移量
                self.render.screen.blit(a, (x + (i + 1) * slot_width - self.render.gui_scale * (4 + c * 4), y + self.render.gui_scale * 15))




