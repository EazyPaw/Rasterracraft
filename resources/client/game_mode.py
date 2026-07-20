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

    def get_block_placement_location(self, block: Block):
        """统一构造放置上下文，再交给待放置方块解释。"""
        target = self.player.choosing_block
        if target is None:
            return None
        get_context = getattr(self.player.client.render, "get_placement_context", None)
        context = get_context(target, self.player) if callable(get_context) else None
        return block.get_placement_location(
            target,
            player=self.player,
            fore_place=getattr(self.player, "fore_place", False),
            context=context,
        )

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
        self.crafting_table = CraftingTable(self.player.client.render)

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
        if self.player.choosing_block and self.player.choosing_block.block_id == "crafting_table":
            if self.crafting_table not in self.player.client.render.drawing_GUIs:
                self.player.client.render.show_gui(self.crafting_table)
            return
        if self.player.choosing_block is None:
            return
        location = self.player.choosing_block.location
        item = self.player.inventory[self.player.selected_slot]
        # 空手、食物或其它非方块物品对着空气右键不应伪造 AIR 放置包。
        create_block = getattr(item.material, 'create_block', None)
        if item.is_empty() or not callable(create_block):
            return
        new_block = create_block()
        if self.player.choosing_block.on_right_click():
            return
        place_location = self.get_block_placement_location(new_block)
        if place_location is None:
            return
        new_block.location = place_location
        logging.debug(
            "Placing block %s at (%s, %s, %s)",
            new_block.name,
            place_location.x,
            place_location.y,
            place_location.z,
        )
        self.player.client.resources_manager.play_sound(new_block.place_sound)
        self.player.client.sent_packet(new_block, 'PlaceBlock')

    def get_choosing_block(self):
        block_x, block_y = self.player.client.render.choosing_position
        if self.player.fore_place:
            foreground = self.player.client.client_world.get_block(block_x, block_y, 0)
            if getattr(foreground, "solid", False):
                self.player.choosing_block = foreground
                return
            background = self.player.client.client_world.get_block(block_x, block_y, 1)
            if getattr(background, "solid", False):
                self.player.choosing_block = background
                return
            if not isinstance(foreground, AIR):
                self.player.choosing_block = foreground
                return
            self.player.choosing_block = foreground
            return
        for z in [0, 1]:
            if not isinstance(self.player.client.client_world.get_block(block_x, block_y, z), AIR):
                self.player.choosing_block = self.player.client.client_world.get_block(block_x, block_y, z)
                return
        self.player.choosing_block = self.player.client.client_world.get_block(block_x, block_y, 1)

    def mouse_wheel(self, direction):
        # 物品名称必须在渲染循环中持续绘制；直接在事件处理阶段调用
        # render_text() 会在下一帧场景重绘时被覆盖。
        hotbar_slots = min(9, len(self.player.inventory))
        if direction == 0 or hotbar_slots == 0:
            return

        slot_delta = -1 if direction > 0 else 1
        self.player.selected_slot = (self.player.selected_slot + slot_delta) % hotbar_slots
        self.player.client.sent_packet({
            "__class__": "SelectHotbarSlot", "slot": self.player.selected_slot,
        })

        item_stack = self.player.inventory[self.player.selected_slot]
        item_name = "" if item_stack.is_empty() else item_stack.get_name()
        for gui in self.player.client.render.drawing_GUIs:
            if isinstance(gui, HotBar):
                gui.show_item_name(item_name)
                break

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
        self.player.client.sent_packet({
            '__class__': 'BreakBlock',
            'x': target.location.x,
            'y': target.location.y,
            'z': target.location.z,
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
        create_block = getattr(item.material, 'create_block', None)
        if location is None or item.is_empty() or not callable(create_block):
            return
        new_block = create_block()
        if self.player.choosing_block.on_right_click():
            return
        place_location = self.get_block_placement_location(new_block)
        if place_location is None:
            return
        new_block.location = place_location
        self.player.client.resources_manager.play_sound(new_block.place_sound)
        self.player.client.sent_packet(new_block, 'PlaceBlock')

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
        self.player.client.resources_manager.play_sound("random.eat")
        self.player.client.sent_packet({"__class__": "ConsumeItem"})
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

_GAMEMODE_REGISTRY: dict[str, type] = None  # None = 尚未构建


def _build_gamemode_id_cache() -> dict[str, type]:
    cache: dict[str, type] = {}

    def collect(cls):
        for subclass in cls.__subclasses__():
            bid = getattr(subclass, 'name_id', None)
            if bid is not None:
                cache[bid] = subclass
            collect(subclass)

    collect(GameMode)
    return cache

def get_gamemode_by_id(gamemode_id: str) -> type:
    global _GAMEMODE_REGISTRY
    if _GAMEMODE_REGISTRY is None:
        _GAMEMODE_REGISTRY = _build_gamemode_id_cache()

    cls = _GAMEMODE_REGISTRY.get(gamemode_id)
    if cls is not None:
        return cls
    raise ValueError(f"Unknown gamemode ID: {gamemode_id}")
