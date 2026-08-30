# Commented and arranged by ChatGPT
from typing import TYPE_CHECKING

from src.client.GUI.chat import ChatGUI
from src.client.GUI.inventory.backpack import Backpack
from src.client.GUI.inventory.crafting_table import CraftingTable
from src.client.GUI.inventory.creative_inventory import CreativeInventory
from src.client.GUI.inventory.hotbar import HotBar
from src.client.GUI.survival_hud import SurvivalHUD
from src.server.block_class import Block
from src.server.blocks import AIR
from src.server.entity import Entity
from abc import ABC

if TYPE_CHECKING:
    from src.client.client_player import ClientPlayer


class GameMode(ABC):
    name_id = "null"
    name = "null"
    durability_consumption = True

    def __init__(self, player: "ClientPlayer"):
        self.player = player
        self._item_use_request_active = False
        self.player.interact_range = 5
        self.player.block_interaction_range = 5
        self.update_gui()

    def update_gui(self):
        self.player.client.render.drawing_GUIs.clear()

    def left_click_on_block(self, block: Block):
        pass

    def right_click_on_block(self, block: Block):
        if self._item_use_request_active:
            self.player.client.sent_packet(
                {"__class__": "PlayerAction", "action": "continue_item_use"}
            )
            return

        target = self.player.choosing_block
        packet = {"__class__": "RightClick"}
        location = getattr(target, "location", None)
        if location is not None:
            packet.update(
                {
                    "x": int(location.x),
                    "y": int(location.y),
                    "z": int(location.z),
                }
            )
            get_context = getattr(
                self.player.client.render, "get_placement_context", None
            )
            context = (
                get_context(target, self.player) if callable(get_context) else None
            )
            if context is not None:
                packet["context"] = {
                    "hit_face": context.hit_face,
                    "ray_direction": list(context.ray_direction),
                    "target_z": int(context.target_z),
                    "fore_place": bool(context.fore_place),
                }
        self._item_use_request_active = True
        self.player.client.sent_packet(packet)

    def stop_item_use(self, *, notify_server: bool = True) -> None:
        if notify_server and self._item_use_request_active:
            self.player.client.sent_packet(
                {"__class__": "PlayerAction", "action": "stop_item_use"}
            )
        self._item_use_request_active = False

    def left_click_on_entity(self, entity: Entity):
        if entity is None or self.player.client.hold_mouse_buttons[0]:
            return
        self.player.client.sent_packet(
            {
                "__class__": "AttackEntity",
                "uuid": str(entity.uuid),
            }
        )

    def right_click_on_entity(self, entity: Entity):
        if entity is None:
            return
        if self._item_use_request_active:
            self.player.client.sent_packet(
                {"__class__": "PlayerAction", "action": "continue_item_use"}
            )
            return
        self._item_use_request_active = True
        self.player.client.sent_packet(
            {
                "__class__": "InteractEntity",
                "uuid": str(entity.uuid),
            }
        )

    def get_choosing_block(self):
        pass

    def mouse_wheel(self, direction):
        pass

    def open_inventory(self):
        pass


class CreativeMode(GameMode):
    name_id = "creative"
    name = "gameMode.creative"
    durability_consumption = False

    def __init__(self, player: "ClientPlayer"):
        super().__init__(player)
        self.player = player
        self.player.interact_range = 5
        self.player.block_interaction_range = 5
        self.player.flyable = True
        self.update_gui()
        self.inv = CreativeInventory(self.player.client.render)
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
            self.player.client.sent_packet(
                {
                    "__class__": "PlayerAction",
                    "action": "continue_breaking",
                    "x": location.x,
                    "y": location.y,
                    "z": location.z,
                }
            )
            self.player.client.client_world.break_block(location)
            self.player.client.sent_packet(
                {
                    "__class__": "BreakBlock",
                    "x": location.x,
                    "y": location.y,
                    "z": location.z,
                }
            )

    def right_click_on_block(self, block: Block):
        super().right_click_on_block(block)

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
            if not isinstance(
                self.player.client.client_world.get_block(block_x, block_y, z), AIR
            ):
                self.player.choosing_block = self.player.client.client_world.get_block(
                    block_x, block_y, z
                )
                return
        self.player.choosing_block = self.player.client.client_world.get_block(
            block_x, block_y, 1
        )

    def mouse_wheel(self, direction):
        # 物品名称必须在渲染循环中持续绘制；直接在事件处理阶段调用
        # render_text() 会在下一帧场景重绘时被覆盖。
        hotbar_slots = min(9, len(self.player.inventory))
        if direction == 0 or hotbar_slots == 0:
            return

        slot_delta = -1 if direction > 0 else 1
        self.player.selected_slot = (
            self.player.selected_slot + slot_delta
        ) % hotbar_slots
        self.player.client.sent_packet(
            {
                "__class__": "SelectHotbarSlot",
                "slot": self.player.selected_slot,
            }
        )

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

    def __init__(self, player: "ClientPlayer"):
        self.break_target = None
        self.break_progress = 0.0
        self._breaking_request_active = False
        self.pending_break_target = None
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
            self.player.client.sent_packet(
                {
                    "__class__": "PlayerAction",
                    "action": "abort_breaking",
                }
            )
        self.break_target = None
        self.break_progress = 0.0
        self._breaking_request_active = False
        if old_target is not None:
            miner_uuid = str(
                getattr(self.player.client, "server_player_uuid", None)
                or self.player.uuid
            )
            self.player.client.client_world.update_break_progress(
                {
                    "miner_uuid": miner_uuid,
                    "active": False,
                }
            )

    def _destroy_delta(self, block: Block) -> float:
        hardness = float(getattr(block, "hardness", 1.5))
        if hardness < 0:
            return 0.0
        material = self.player.inventory[self.player.selected_slot].material
        speed = 1.0
        if getattr(material, "tool_type", None) == getattr(
            block, "preferred_tool", None
        ):
            speed = max(0.0, float(getattr(material, "mining_speed", 1.0)))
        inside_block = bool(
            self.player._check_collision_at(self.player.x, self.player.y)
        )
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
            getattr(self.player.client, "server_player_uuid", None) or self.player.uuid
        )
        self.player.client.client_world.update_break_progress(
            {
                "miner_uuid": miner_uuid,
                "x": x,
                "y": y,
                "z": z,
                "progress": self.break_progress,
                "active": True,
            }
        )

    def handle_break_result(self, x: int, y: int, z: int) -> None:
        if self.pending_break_target is not None and self.pending_break_target[:3] == (
            x,
            y,
            z,
        ):
            self.pending_break_target = None

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
            self.break_progress = min(
                1.0, self.break_progress + self._destroy_delta(target)
            )
            self.player.client.sent_packet(
                {
                    "__class__": "PlayerAction",
                    "action": "continue_breaking",
                    "x": target.location.x,
                    "y": target.location.y,
                    "z": target.location.z,
                }
            )
            self._publish_local_break_progress()
            self.player.skeleton.trigger_swing()
            if self.break_progress < 1.0:
                return

            x, y, z, _block_id = key
            self.pending_break_target = key
            self.player.client.client_world.break_block(x, y, z)
            self.player.client.sent_packet(
                {
                    "__class__": "BreakBlock",
                    "x": x,
                    "y": y,
                    "z": z,
                }
            )
            self.reset_breaking()

    def right_click_on_block(self, block: Block):
        super().right_click_on_block(block)

    def tick(self):
        if not self.player.client.hold_mouse_buttons[0]:
            self.reset_breaking(notify_server=True)

    def get_choosing_block(self):
        CreativeMode.get_choosing_block(self)

    def mouse_wheel(self, direction):
        if direction != 0:
            self.stop_item_use(notify_server=True)
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
            bid = getattr(subclass, "name_id", None)
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
