import pygame

from resources.client.GUI.gui import GUI
from resources.server.item_class import EmptyItemStack
from resources.server.utils import reverse_search_dict


class Backpack(GUI):
    _texture_path = "gui.container.inventory"
    def __init__(self, render):
        super().__init__(render)
        self.solt_pos = []
        self.selection_texture = self.get_texture(self.render.gui_scale, self.render.client
                                                  , "gui.sprites.container.slot_highlight_back")

        self.priority = 10
        self.dragging_item = None
        self.selecting_item = None
        self.selecting_solt = None

        self.slot_rows = 4
        self.slot_cols = 9
        self.slot_size = 18


    def draw(self):
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        self.render.blit(self.render.ig_gui_layer, (0, 0))
        # 居中渲染
        x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        self.render.blit(texture, (x, y))
        
        # 清空并重新计算槽位坐标
        self.solt_pos = []
        
        # 计算槽位起始位置（相对于背包纹理左上角的偏移）
        # Minecraft 标准物品栏槽位区域通常在纹理内部有一定边距
        slot_area_x = x + 7 * self.render.gui_scale  # 左边距
        slot_area_y = y + 83 * self.render.gui_scale  # 上边距
        
        # 每个槽位的实际像素大小
        slot_pixel_size = self.render.gui_scale * self.slot_size
        
        # 遍历所有槽位（3行9列的主物品栏）
        for row in range(self.slot_rows):
            for col in range(self.slot_cols):
                slot_x = slot_area_x + col * slot_pixel_size
                if row == 3:
                    slot_y = slot_area_y + row * slot_pixel_size + 4 * self.render.gui_scale
                else:
                    slot_y = slot_area_y + row * slot_pixel_size
                self.solt_pos.append((slot_x, slot_y))

                # 检测鼠标是否在当前槽位内
                if  slot_x <= self.render.mouse_x <= slot_x + slot_pixel_size \
                        and slot_y <= self.render.mouse_y <= slot_y + slot_pixel_size:
                    self.render.blit(self.selection_texture, (slot_x + self.render.gui_scale, slot_y + self.render.gui_scale))
                    self.selecting_solt = row * self.slot_cols + col
                    self.selecting_item = self.render.client.client_player.inventory[self.selecting_solt]
                # else:
                #     self.selecting_item = None
                
                # 绘制该槽位中的物品
                slot_index = row * self.slot_cols + col
                if slot_index < len(self.render.client.client_player.inventory):
                    item = self.render.client.client_player.inventory[slot_index]
                    texture_item = item.get_texture(self.render.gui_scale * 0.7, self.render.client, True)
                    
                    if texture_item is not None:
                        # 物品在槽位内居中
                        item_x = slot_x + (slot_pixel_size - texture_item.get_width()) / 2
                        item_y = slot_y + (slot_pixel_size - texture_item.get_height()) / 2
                        self.render.blit(texture_item, (item_x, item_y))
                        
                        # 绘制物品数量
                        if hasattr(item, 'amount') and item.amount > 1:
                            font_size = int(20 * self.render.gui_scale / 3.5)
                            #amount_text = self.render.get_font(font_size).render(str(item.amount), True, (255, 255, 255))
                            digit_count = len(str(abs(item.amount)))
                            text_x = slot_x + slot_pixel_size - self.render.gui_scale * (3 + digit_count * 3)
                            text_y = slot_y + slot_pixel_size - self.render.gui_scale * 5 - 6
                            #self.render.screen.blit(amount_text, (text_x, text_y))
                            self.render.render_text(str(item.amount), (text_x, text_y), (255, 255, 255), font_size, True)

        # 绘制拖拽物品
        if self.dragging_item and not self.dragging_item.is_empty():
            texture_item = self.dragging_item.get_texture(self.render.gui_scale * 0.7, self.render.client, True)
            if texture_item is not None:
                self.render.blit(texture_item, (self.render.mouse_x - texture_item.get_width() // 2, self.render.mouse_y - texture_item.get_height() // 2))
                self.render.render_text(str(self.dragging_item.amount), (self.render.mouse_x + texture_item.get_width() // 4, self.render.mouse_y + texture_item.get_height() // 4)
                                        , (255, 255, 255), int(20 * self.render.gui_scale / 3.5), True)

    def handle_events(self, events):
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self.dragging_item = self.selecting_item
                    self.render.client.client_player.inventory[self.selecting_solt] = EmptyItemStack()
            if event.type in reverse_search_dict(self.render.client.key_map, self.render.client.client_player.game_mode.open_inventory):
                ...

    def on_open(self):
        self.render.client.game_manager.ing_mouse_lock += 1

    def on_close(self):
        self.render.client.game_manager.ing_mouse_lock -= 1

