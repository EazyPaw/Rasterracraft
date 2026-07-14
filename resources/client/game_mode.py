import logging
from typing import TYPE_CHECKING

from resources.client.GUI.chat import ChatGUI
from resources.client.GUI.inventory.backpack import Backpack
from resources.client.GUI.inventory.crafting_table import CraftingTable
from resources.client.GUI.inventory.hotbar import HotBar
from resources.client.GUI.survival_hud import SurvivalHUD
from resources.server.block_class import Block
from resources.server.blocks import AIR
from resources.server.entity import Entity
from resources.server.location import Location
from abc import ABC

if TYPE_CHECKING:
    from resources.client.client_player import ClientPlayer

class GameMode(ABC):

    name_id = "null"
    name = "null"

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
    name = "gameMode.creative"

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
            self.player.client.sent_packet(block, 'BreakBlock')


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
            place_location = None
            if isinstance(self.player.client.client_world.get_block(location), AIR):
                place_location = location
            else:
                other_z = 1 if location.z == 0 else 0
                alt_location = Location(location.world, location.x, location.y, other_z)
                if isinstance(self.player.client.client_world.get_block(alt_location), AIR):
                    place_location = alt_location
            if place_location is not None:
                new_block.location = place_location
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
    name = "gameMode.survival"

    def __init__(self, player: 'ClientPlayer'):
        self.break_target = None
        self.break_progress = 0.0
        self.pending_break_target = None
        self.eat_progress = 0
        self.eating_slot = None
        super().__init__(player)
        self.player.flyable = False
        self.inv = Backpack(self.player.client.render)
        self.crafting_table = CraftingTable(self.player.client.render)

    def update_gui(self):
        if self.player.client.chat_gui is None:
            self.player.client.chat_gui = ChatGUI(self.player.client.render)
        self.player.client.render.drawing_GUIs = [
            SurvivalHUD(self.player.client.render),
            self.player.client.chat_gui,
        ]

    @staticmethod
    def _target_key(block):
        location = getattr(block, "location", None)
        if location is None:
            return None
        return int(location.x), int(location.y), int(location.z), block.block_id

    def _destroy_delta(self, block: Block) -> float:
        """Java-edition destroy progress per game tick.

        progress = speed / hardness / (30 when harvestable, otherwise 100).
        The result is deliberately accumulated once per 20 TPS game tick,
        matching the rounded timings documented by the Minecraft Wiki.
        """
        hardness = float(getattr(block, "hardness", 1.5))
        if hardness < 0:
            return 0.0
        material = self.player.inventory[self.player.selected_slot].material
        speed = 1.0
        if getattr(material, "tool_type", None) == getattr(block, "preferred_tool", None):
            speed = float(getattr(material, "mining_speed", 1.0))
        if self.player.in_fluid:
            speed /= 5.0
        if not self.player.on_ground:
            speed /= 5.0
        divisor = 30.0 if block.can_harvest(material) else 100.0
        return 1.0 if hardness == 0 else speed / hardness / divisor

    def reset_breaking(self):
        self.break_target = None
        self.break_progress = 0.0

    def get_destroy_stage(self):
        if self.break_target is None or self.break_progress <= 0:
            return None
        return min(9, max(0, int(self.break_progress * 10)))

    def left_click_on_block(self, block: Block):
        target = self.player.choosing_block
        if target is None or not target.breakable or isinstance(target, AIR):
            self.pending_break_target = None
            self.reset_breaking()
            return
        key = self._target_key(target)
        if key == self.pending_break_target:
            return
        if key != self.break_target:
            self.break_target = key
            self.break_progress = 0.0
        self.break_progress += self._destroy_delta(target)
        self.player.skeleton.trigger_swing()
        if self.break_progress < 1.0:
            return

        # The server removes the block and creates its physical dropped item.
        self.pending_break_target = key
        held_item = self.player.inventory[self.player.selected_slot].material.name_id
        self.player.client.sent_packet({
            '__class__': 'BreakBlock',
            'x': target.location.x,
            'y': target.location.y,
            'z': target.location.z,
            'held_item': held_item,
        })
        self.reset_breaking()

    def right_click_on_block(self, block: Block):
        item = self.player.inventory[self.player.selected_slot]
        if self.player.choosing_block and self.player.choosing_block.block_id == "crafting_table":
            if self.crafting_table not in self.player.client.render.drawing_GUIs:
                self.player.client.render.show_gui(self.crafting_table)
            return
        if getattr(item.material, "food_value", 0):
            self._eat_selected_item(item)
            return

        location = self.player.choosing_block.location if self.player.choosing_block else None
        if location is None or item.is_empty() or not hasattr(item.material, 'target_block'):
            return
        new_block = item.material.target_block()
        world = self.player.client.client_world
        place_location = location if isinstance(world.get_block(location), AIR) else None
        if place_location is None:
            other_z = 1 if location.z == 0 else 0
            alternative = Location(location.world, location.x, location.y, other_z)
            if isinstance(world.get_block(alternative), AIR):
                place_location = alternative
        if place_location is not None:
            new_block.location = place_location
            self.player.client.resources_manager.play_sound(new_block.place_sound)
            if self.player.client.sent_packet(new_block, 'PlaceBlock'):
                item.reduce_amount(1)

    def _eat_selected_item(self, item):
        if self.player.food_level >= 20:
            self.eating_slot = None
            self.eat_progress = 0
            return
        slot = self.player.selected_slot
        if self.eating_slot != slot:
            self.eating_slot = slot
            self.eat_progress = 0
        self.eat_progress += 1
        self.player.skeleton.trigger_swing()
        if self.eat_progress < 16:  # 0.8 seconds at 20 TPS
            return
        food = getattr(item.material, "food_value", 0)
        saturation = float(getattr(item.material, "saturation_modifier", 0.0))
        self.player.food_level = min(20, self.player.food_level + food)
        self.player.saturation = min(float(self.player.food_level), self.player.saturation + food * saturation * 2)
        item.reduce_amount(1)
        self.player.client.resources_manager.play_sound("random.eat")
        self.eating_slot = None
        self.eat_progress = 0

    def tick(self):
        if self.pending_break_target is not None:
            x, y, z, block_id = self.pending_break_target
            current = self.player.client.client_world.get_block(x, y, z)
            if current.block_id != block_id:
                self.pending_break_target = None
        if not self.player.client.hold_mouse_buttons[0]:
            self.reset_breaking()
        if not self.player.client.hold_mouse_buttons[2]:
            self.eating_slot = None
            self.eat_progress = 0

    def get_choosing_block(self):
        CreativeMode.get_choosing_block(self)

    def mouse_wheel(self, direction):
        CreativeMode.mouse_wheel(self, direction)

    def open_inventory(self):
        if self.inv in self.player.client.render.drawing_GUIs:
            self.player.client.render.close_gui(self.inv)
        else:
            self.player.client.render.show_gui(self.inv)
