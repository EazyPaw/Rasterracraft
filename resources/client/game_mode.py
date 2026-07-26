import logging
import logging
from typing import TYPE_CHECKING

from resources.client.GUI.chat import ChatGUI
from resources.client.GUI.inventory.backpack import Backpack
from resources.client.GUI.inventory.crafting_table import CraftingTable
from resources.client.GUI.inventory.hotbar import HotBar
from resources.client.GUI.survival_hud import SurvivalHUD
from resources.server.block_class import Block
from resources.server.blocks import AIR
from resources.server.attributes import EATING_SPEED_MODIFIER
from resources.server.entity import Entity
from resources.server.material_class import Food
from abc import ABC

if TYPE_CHECKING:
    from resources.client.client_player import ClientPlayer

class GameMode(ABC):

    name_id = "null"
    name = "null"
    durability_consumption = True

    def __init__(self, player: 'ClientPlayer'):
        self.player = player
        self.player.interact_range = 5
        self.player.block_interaction_range = 5
        self.update_gui()

    def update_gui(self):
        self.player.client.render.drawing_GUIs.clear()

    def left_click_on_block(self, block: Block):
        pass

    def right_click_on_block(self, block: Block):
        pass

    def left_click_on_entity(self, entity: Entity):
        if entity is None or self.player.client.hold_mouse_buttons[0]:
            return
        self.player.client.sent_packet({
            "__class__": "AttackEntity",
            "uuid": str(entity.uuid),
        })

    def right_click_on_entity(self, entity: Entity):
        if entity is None or self.player.client.hold_mouse_buttons[2]:
            return
        self.player.client.sent_packet({
            "__class__": "InteractEntity",
            "uuid": str(entity.uuid),
        })

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

    def try_use_selected_item_on_block(self) -> bool:
        target = self.player.choosing_block
        if target is None:
            return False
        stack = self.player.inventory[self.player.selected_slot]
        if stack.is_empty() or not target.accepts_item_use(stack.material):
            return False
        # Item-on-block interactions fire once per physical press.  Returning
        # True while the button remains held also prevents falling through to
        # placement logic during the same interaction.
        if self.player.client.hold_mouse_buttons[2]:
            return True
        location = target.location
        self.player.skeleton.trigger_swing()
        self.player.client.sent_packet({
            "__class__": "UseBlock",
            "x": location.x,
            "y": location.y,
            "z": location.z,
        })
        return True

    def try_open_furnace(self) -> bool:
        target = self.player.choosing_block
        if target is None or target.block_id != "furnace":
            return False
        if self.player.client.hold_mouse_buttons[2]:
            return True
        location = target.location
        self.player.client.sent_packet({
            "__class__": "OpenFurnace",
            "x": int(location.x),
            "y": int(location.y),
            "z": int(location.z),
        })
        return True

    def mouse_wheel(self, direction):
        pass

    def open_inventory(self):
        pass

class CreativeMode(GameMode):
    name_id = "creative"
    name = "gameMode.creative"
    durability_consumption = False

    def __init__(self, player: 'ClientPlayer'):
        super().__init__(player)
        self.player = player
        self.player.interact_range = 5
        self.player.block_interaction_range = 5
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
            self.player.client.sent_packet({
                '__class__': 'PlayerAction',
                'action': 'continue_breaking',
                'x': location.x,
                'y': location.y,
                'z': location.z,
            })
            self.player.client.client_world.break_block(location)
            self.player.client.sent_packet({
                '__class__': 'BreakBlock',
                'x': location.x,
                'y': location.y,
                'z': location.z,
            })


    def right_click_on_block(self, block: Block):
        if self.player.client.hold_mouse_buttons[2]:
            return
        if self.try_open_furnace():
            return
        if self.player.choosing_block and self.player.choosing_block.block_id == "crafting_table":
            if self.crafting_table not in self.player.client.render.drawing_GUIs:
                self.player.client.render.show_gui(self.crafting_table)
            return
        if self.player.choosing_block is None:
            return
        if self.try_use_selected_item_on_block():
            return
        item = self.player.inventory[self.player.selected_slot]
        # 空手、食物或其它非方块物品对着空气右键不应伪造 AIR 放置包。
        create_block = getattr(item.material, 'create_block', None)
        if item.is_empty() or not callable(create_block):
            return
        new_block = create_block()
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
        self._breaking_request_active = False
        self.pending_break_target = None
        self.eat_progress = 0
        self.eating_slot = None
        self._eating_request_active = False
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

    def reset_breaking(self, *, notify_server: bool = False):
        old_target = self.break_target
        if notify_server and self._breaking_request_active:
            self.player.client.sent_packet({
                '__class__': 'PlayerAction',
                'action': 'abort_breaking',
            })
        self.break_target = None
        self.break_progress = 0.0
        self._breaking_request_active = False
        if old_target is not None:
            miner_uuid = str(
                getattr(self.player.client, 'server_player_uuid', None)
                or self.player.uuid
            )
            self.player.client.client_world.update_break_progress({
                'miner_uuid': miner_uuid,
                'active': False,
            })

    def _destroy_delta(self, block: Block) -> float:
        hardness = float(getattr(block, 'hardness', 1.5))
        if hardness < 0:
            return 0.0
        material = self.player.inventory[self.player.selected_slot].material
        speed = 1.0
        if getattr(material, 'tool_type', None) == getattr(block, 'preferred_tool', None):
            speed = max(0.0, float(getattr(material, 'mining_speed', 1.0)))
        inside_block = bool(self.player._check_collision_at(self.player.x, self.player.y))
        if not inside_block:
            if self.player.in_fluid:
                speed /= 5.0
            if not self.player.on_ground:
                speed /= 5.0
        divisor = 30.0 if block.can_harvest(material) else 100.0
        return 1.0 if hardness == 0 else speed / hardness / divisor

    def _publish_local_break_progress(self) -> None:
        if self.break_target is None:
            return
        x, y, z = self.break_target[:3]
        miner_uuid = str(
            getattr(self.player.client, 'server_player_uuid', None)
            or self.player.uuid
        )
        self.player.client.client_world.update_break_progress({
            'miner_uuid': miner_uuid,
            'x': x, 'y': y, 'z': z,
            'progress': self.break_progress,
            'active': True,
        })

    def handle_break_result(self, x: int, y: int, z: int) -> None:
        if self.pending_break_target is not None and self.pending_break_target[:3] == (x, y, z):
            self.pending_break_target = None

    def reconcile_attribute_predictions(self) -> None:
        """Reapply the local eating prediction after an authoritative snapshot."""
        movement = self.player.attributes.get_instance("movement_speed")
        if self._eating_request_active:
            movement.add_modifier(
                EATING_SPEED_MODIFIER,
                source="prediction:eating",
                replace=True,
            )
        else:
            # This also removes a delayed authoritative copy with the same id,
            # so releasing use restores local movement on the current frame.
            movement.remove_modifier(EATING_SPEED_MODIFIER.id)

    def _stop_eating(self, *, notify_server: bool) -> None:
        if notify_server and self._eating_request_active:
            self.player.client.sent_packet({
                '__class__': 'PlayerAction', 'action': 'stop_eating'
            })
        self._eating_request_active = False
        self.eating_slot = None
        self.eat_progress = 0
        self.reconcile_attribute_predictions()

    def left_click_on_block(self, block: Block):
        target = self.player.choosing_block
        if not target.on_left_click(self.player):
            if target is None or not target.breakable or isinstance(target, AIR):
                self.reset_breaking(notify_server=True)
                return
            key = self._target_key(target)
            if (
                self.pending_break_target is not None
                and self.pending_break_target[:3] == key[:3]
            ):
                return
            if self.break_target is None or tuple(self.break_target[:3]) != key[:3]:
                self.reset_breaking()
                self.break_target = key
                self.break_progress = 0.0
            self._breaking_request_active = True
            self.break_progress = min(1.0, self.break_progress + self._destroy_delta(target))
            self.player.client.sent_packet({
                '__class__': 'PlayerAction',
                'action': 'continue_breaking',
                'x': target.location.x,
                'y': target.location.y,
                'z': target.location.z,
            })
            self._publish_local_break_progress()
            self.player.skeleton.trigger_swing()
            if self.break_progress < 1.0:
                return

            x, y, z, _block_id = key
            self.pending_break_target = key
            self.player.client.client_world.break_block(x, y, z)
            self.player.client.sent_packet({
                '__class__': 'BreakBlock',
                'x': x, 'y': y, 'z': z,
            })
            self.reset_breaking()

    def right_click_on_block(self, block: Block):
        item = self.player.inventory[self.player.selected_slot]
        if self.try_open_furnace():
            return
        if self.player.choosing_block and self.player.choosing_block.block_id == "crafting_table":
            if self.crafting_table not in self.player.client.render.drawing_GUIs:
                self.player.client.render.show_gui(self.crafting_table)
            return
        if self.try_use_selected_item_on_block():
            return
        if isinstance(item.material, Food):
            self._eat_selected_item(item)
            return

        if self.player.client.hold_mouse_buttons[2]:
            return

        location = self.player.choosing_block.location if self.player.choosing_block else None
        create_block = getattr(item.material, 'create_block', None)
        if location is None or item.is_empty() or not callable(create_block):
            return
        new_block = create_block()
        place_location = self.get_block_placement_location(new_block)
        if place_location is None:
            return
        new_block.location = place_location
        self.player.client.resources_manager.play_sound(new_block.place_sound)
        self.player.client.sent_packet(new_block, 'PlaceBlock')

    def _eat_selected_item(self, item):
        food = item.material
        if not isinstance(food, Food) or not food.can_consume(self.player):
            self._stop_eating(notify_server=True)
            return
        slot = self.player.selected_slot
        if self.eating_slot != slot:
            self.eating_slot = slot
            self.eat_progress = 0
        self.eat_progress += 1
        if not self._eating_request_active:
            self._eating_request_active = True
            # Predict on the input frame; the packet below no longer needs to
            # make a round trip before movement becomes slower.
            self.reconcile_attribute_predictions()
        self.player.client.sent_packet({
            '__class__': 'PlayerAction',
            'action': 'continue_eating',
        })
        self.player.skeleton.trigger_swing()
        if self.eat_progress < food.consume_duration_ticks:
            return
        self.eating_slot = None
        self.eat_progress = 0

    def tick(self):
        if not self.player.client.hold_mouse_buttons[0]:
            self.reset_breaking(notify_server=True)
        if not self.player.client.hold_mouse_buttons[2]:
            self._stop_eating(notify_server=True)

    def get_choosing_block(self):
        CreativeMode.get_choosing_block(self)

    def mouse_wheel(self, direction):
        if direction != 0:
            self._stop_eating(notify_server=True)
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
