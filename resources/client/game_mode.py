import logging
from typing import TYPE_CHECKING

from resources.client.GUI.inventory.backpack import Backpack
from resources.client.GUI.chat import ChatGUI
from resources.client.GUI.inventory.hotbar import HotBar
from resources.server.block_class import Block
from resources.server.blocks import AIR
from resources.server.entity import Entity
from resources.server.location import Location

import resources.server.blocks as blocks
from resources.server.material_class import BlockItem

if TYPE_CHECKING:
    from resources.client.client_player import ClientPlayer

class GameMode:

    name_id = "null"

    def __init__(self, player: 'ClientPlayer'):
        self.player = player
        self.player.interact_range = 5
        self.update_gui()

    def update_gui(self):
        self.player.client.render.drawing_GUIs.clear()

    def left_click_on_block(self, block: Block):
        pass

    def right_click_on_block(self, block: Block):
        pass

    def left_click_on_entity(self, entity: Entity):
        pass

    def right_click_on_entity(self, entity: Entity):
        pass

    def get_choosing_block(self):
        pass

    def mouse_wheel(self, direction):
        pass

    def open_inventory(self):
        pass


class CreativeMode(GameMode):
    name_id = "creative"

    def __init__(self, player: 'ClientPlayer'):
        super().__init__(player)
        self.player = player
        self.player.interact_range = 5
        self.player.flyable = True
        self.update_gui()
        self.inv = Backpack(self.player.client.render)

    def update_gui(self):
        # 确保 ChatGUI 单例存在（首次创建）
        if self.player.client.chat_gui is None:
            self.player.client.chat_gui = ChatGUI(self.player.client.render)
        self.player.client.render.drawing_GUIs = [
            HotBar(self.player.client.render),
            self.player.client.chat_gui,
        ]

    def left_click_on_block(self, block: Block):
        if self.player.client.hold_mouse_buttons[0]:
            return
        location = self.player.choosing_block.location
        block = self.player.client.client_world.get_block(location)
        if block.breakable:
            self.player.client.client_world.break_block(location)
            self.player.client.sent_packet(self.player.client.client_world.get_block(location), 'BreakBlock')


    def right_click_on_block(self, block: Block):
        if self.player.client.hold_mouse_buttons[2]:
            return
        location = self.player.choosing_block.location
        item = self.player.inventory[self.player.selected_slot]
        if hasattr(item.material, 'target_block'):
            new_block = item.material.target_block()
        else:
            new_block = AIR()
            print(type(item.material))
        logging.debug(f"Placing block {new_block.name} at {location}")
        if not self.player.choosing_block.on_right_click():
            if isinstance(self.player.client.client_world.get_block(location), AIR):
                new_block.place_at(location)
                self.player.client.resources_manager.play_sound(new_block.place_sound)
                self.player.client.sent_packet(new_block, 'PlaceBlock')
            elif new_block.place_at(location.add(0, 0, -1)):
                self.player.client.resources_manager.play_sound(new_block.place_sound)
                self.player.client.sent_packet(new_block, 'PlaceBlock')

    def get_choosing_block(self):
        block_x, block_y = self.player.client.render.choosing_position
        for z in [0, 1]:
            if not isinstance(self.player.client.client_world.get_block(block_x, block_y, z), AIR):
                self.player.choosing_block = self.player.client.client_world.get_block(block_x, block_y, z)
                return
        self.player.choosing_block = self.player.client.client_world.get_block(block_x, block_y, 1)

    def mouse_wheel(self, direction):
        if direction > 0:
            if self.player.client.client_player.selected_slot == 0:
                self.player.client.client_player.selected_slot = 8
                return
            self.player.client.client_player.selected_slot -= 1
        else:
            if self.player.client.client_player.selected_slot == 8:
                self.player.client.client_player.selected_slot = 0
                return
            self.player.client.client_player.selected_slot += 1

    def open_inventory(self):
        if self.inv in self.player.client.render.drawing_GUIs:
            self.player.client.render.close_gui(self.inv)
        else:
            self.player.client.render.show_gui(self.inv)

class SurvivalMode(GameMode):
    name_id = "survival"

    def left_click_on_block(self, block: Block):
        block.on_break()
        block.on_left_click()

    def right_click_on_block(self, block: Block):
        block.on_right_click()