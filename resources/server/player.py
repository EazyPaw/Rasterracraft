import math as _math
import random as _random

from resources.client.game_mode import SurvivalMode
from resources.server.damange_type import DamageType, FALL, GENERIC
from resources.server.entity import Entity
from resources.server.inventory import Inventory, serialize_inventory, stack_to_payload
from resources.server.item_class import EmptyItemStack, ItemStack
from resources.server.location import Location, decide_x_or_loc
from resources.server.particles import SPRINT_STEP
from resources.server.world_class import World


class Player(Entity):
    sounds = {
        "hurt": "game.player.hurt",
        "fall_big": "game.player.hurt.fall.big",
        "fall_small": "game.player.hurt.fall.small",
        "death": "game.player.die",
    }

    def __init__(self, x, y, world, gamemode = None):
        super().__init__(x, y, world)
        self.world: World = world
        self.entity_id = "player"
        self.loading_regions = []
        # Regions whose payload has been atomically installed by the client.
        # ``loading_regions`` only means that the server sent the packet.
        self.client_loaded_regions: set[int] = set()
        self.initial_load_complete_sent = False
        self.name = "Player_" + self.uuid.hex[:8]
        self.is_operator = False
        self.width = 0.6
        self.height = 1.8
        self.max_health = 20
        self.health = self.max_health
        self.attack_damage = 1.0
        self.interact_range = 5.0
        self.food_level = 20
        self.saturation = 5.0
        self.experience = 0
        self.experience_level = 0
        self.gamemode = gamemode if gamemode is not None else SurvivalMode
        self.inventory = Inventory(36)
        self.crafting_grid = Inventory(9)
        self.cursor_stack = EmptyItemStack()
        self._initialize_inventory()
        self.selected_slot = 0
        # A client may already have PlayerMove packets queued when the server
        # teleports it.  Do not let one of those stale packets overwrite the
        # authoritative destination before the client has received the
        # Teleport packet.
        self._teleport_id = 0
        self._pending_teleport_id: int | None = None
        # 疾跑粒子节流：避免每帧都生成粒子造成刷屏
        self._sprint_particle_timer: int = 0
        self._last_sprint_particle_x: float | None = None
        self.spawn_point = 0

    def _initialize_inventory(self) -> None:
        """Create the same starter inventory as the client for new worlds."""
        from resources.server.materials import APPLE, BREAD, GLOWSTONE, SAND, WATER
        if getattr(self.gamemode, "name_id", "survival") == "creative":
            for i in range(4):
                self.inventory[i] = ItemStack(GLOWSTONE(), 64)
            for i in range(8, 16):
                self.inventory[i] = ItemStack(SAND(), 64)
            for i in range(4, 8):
                self.inventory[i] = ItemStack(WATER(), 64)
        else:
            self.inventory[0] = ItemStack(APPLE(), 3)
            self.inventory[1] = ItemStack(BREAD(), 2)

    def give_item_stack(self, stack: ItemStack, *, sync: bool = True) -> int:
        """Give as much of ``stack`` as fits; return the number accepted."""
        before = max(0, int(stack.amount))
        self.inventory.add_item(stack)
        added = before - max(0, int(stack.amount))
        if added and sync:
            self.sync_inventory()
        return added

    def give_item(self, material, amount: int = 1, nbt=None, *, sync: bool = True) -> int:
        """Public server-side item grant hook used by commands and gameplay."""
        if isinstance(material, str):
            from resources.server.materials import get_material_by_id
            material = get_material_by_id(material)
        return self.give_item_stack(ItemStack(material, max(0, int(amount)), nbt), sync=sync)

    def inventory_packet(self) -> dict:
        return {
            "__class__": "InventoryUpdate",
            "inventory": serialize_inventory(self.inventory),
            "crafting": serialize_inventory(self.crafting_grid),
            "cursor": stack_to_payload(self.cursor_stack),
            "selected_slot": int(self.selected_slot),
            "health": float(self.health),
            "food_level": int(self.food_level),
            "saturation": float(self.saturation),
        }

    def sync_inventory(self) -> None:
        self.world.server.send_client_socket(self, self.inventory_packet(), "Forward")

    def can_take_damage(self, damage_type: type[DamageType] = GENERIC) -> bool:
        mode = getattr(self.gamemode, "name_id", "survival")
        return mode not in {"creative", "spectator"} and super().can_take_damage(damage_type)

    def get_attack_damage(self, target=None) -> float:
        try:
            held = self.inventory[self.selected_slot]
            held_damage = getattr(held.material, "attack_damage", None)
            if held_damage is not None:
                return max(0.0, float(held_damage))
        except (AttributeError, IndexError, TypeError, ValueError):
            pass
        return super().get_attack_damage(target)

    def get_hurt_sound(self, damage_type: type[DamageType], actual_damage: float) -> str | None:
        if self.health <= 0:
            return None
        if damage_type is FALL:
            return self.get_sound("fall_big" if actual_damage >= 5 else "fall_small")
        return self.get_sound("hurt")

    def on_damage_applied(self, actual_damage: float, raw_damage: float,
                          damage_type: type[DamageType], source) -> None:
        super().on_damage_applied(actual_damage, raw_damage, damage_type, source)
        server = getattr(self.world, "server", None)
        if server is None:
            return
        # Ignore queued pre-hit PlayerMove health until the client has received
        # and begun reporting the authoritative result.
        self._server_health_lock_until = server.server_ticks + self.hurt_time
        packet = {
            "__class__": "PlayerHurt",
            "health": self.health,
            "hurt_time": self.hurt_time,
            "last_hurt_damage": self.last_hurt_damage,
            "cause": getattr(damage_type, "message_id", "generic"),
            "damage": actual_damage,
            "motion": {"x": self.motion.x, "y": self.motion.y},
        }
        if self.health <= 0:
            self.emit_death_effects()
            packet["death_message"] = self.get_death_message()
        server.send_client_socket(self, packet, "Forward")
        for other in tuple(server.players):
            if other is self or other.world is not self.world:
                continue
            if other.is_loading_position(int(self.x), int(self.y), getattr(self, "z", 0)):
                server.send_client_socket(other, self, "EntityUpdate")

    def _click_inventory(self, slot: int, button: int) -> None:
        self._click_container(self.inventory, slot, button)

    def _click_container(self, container, slot: int, button: int) -> None:
        if not 0 <= int(slot) < len(container) or button not in (1, 3):
            return
        slot = int(slot)
        target = container[slot]
        cursor = self.cursor_stack
        if cursor.is_empty():
            if target.is_empty():
                return
            if button == 1:
                self.cursor_stack = target
                container[slot] = EmptyItemStack()
            else:
                take = (target.amount + 1) // 2
                self.cursor_stack = ItemStack(target.material, take, target.nbt)
                target.amount -= take
                if target.amount <= 0:
                    container[slot] = EmptyItemStack()
            return
        if target.is_empty():
            amount = cursor.amount if button == 1 else 1
            container[slot] = ItemStack(cursor.material, amount, cursor.nbt)
            cursor.amount -= amount
        elif target.material == cursor.material and target.nbt == cursor.nbt:
            amount = min(cursor.amount if button == 1 else 1, target.max_stack_size - target.amount)
            target.amount += max(0, amount)
            cursor.amount -= max(0, amount)
        else:
            container[slot], self.cursor_stack = cursor, target
            return
        if cursor.amount <= 0:
            self.cursor_stack = EmptyItemStack()

    def inventory_click(self, slot: int, button: int) -> None:
        self._click_inventory(slot, button)
        self.sync_inventory()

    def crafting_click(self, slot: int, button: int) -> None:
        self._click_container(self.crafting_grid, slot, button)
        self.sync_inventory()

    def crafting_take(self, width: int = 2, height: int = 2) -> None:
        from resources.server.crafting import find_recipe
        if width not in (2, 3) or height not in (2, 3) or width * height > len(self.crafting_grid):
            self.sync_inventory()
            return
        match = find_recipe(list(self.crafting_grid)[:width * height], width, height)
        if match is None:
            self.sync_inventory()
            return
        result, inputs = match
        cursor = self.cursor_stack
        if cursor.is_empty():
            self.cursor_stack = ItemStack(result.material, result.amount, result.nbt)
        elif cursor.material == result.material and cursor.nbt == result.nbt:
            if cursor.amount + result.amount > cursor.max_stack_size:
                self.sync_inventory()
                return
            cursor.amount += result.amount
        else:
            self.sync_inventory()
            return
        for index in inputs:
            self.crafting_grid[index].reduce_amount(1)
            if self.crafting_grid[index].is_empty():
                self.crafting_grid[index] = EmptyItemStack()
        self.sync_inventory()

    def crafting_close(self) -> None:
        for index in range(len(self.crafting_grid)):
            stack = self.crafting_grid[index]
            if stack.is_empty():
                continue
            self.give_item_stack(stack, sync=False)
            if stack.amount > 0:
                from resources.server.entities.item import Item
                self.world.spawn_entity(Item(self.x + self.width / 2, self.y + 0.5, self.world, stack))
            self.crafting_grid[index] = EmptyItemStack()
        self.sync_inventory()

    def inventory_drag(self, slots, button: int) -> None:
        self._drag_container(self.inventory, slots, button)
        self.sync_inventory()

    def crafting_drag(self, slots, button: int) -> None:
        self._drag_container(self.crafting_grid, slots, button)
        self.sync_inventory()

    def _drag_container(self, container, slots, button: int) -> None:
        valid = []
        for slot in slots if isinstance(slots, list) else []:
            try:
                slot = int(slot)
            except (TypeError, ValueError):
                continue
            if 0 <= slot < len(container) and slot not in valid:
                valid.append(slot)
        if not self.cursor_stack.is_empty() and valid:
            if button == 1:
                each = self.cursor_stack.amount // len(valid)
                for slot in valid:
                    if each:
                        self._place_into_container(container, slot, each)
            elif button == 3:
                for slot in valid:
                    if self.cursor_stack.is_empty():
                        break
                    self._place_into_container(container, slot, 1)

    def _place_into_container(self, container, slot: int, amount: int) -> None:
        target = container[slot]
        if target.is_empty():
            moved = min(amount, self.cursor_stack.amount, self.cursor_stack.max_stack_size)
            container[slot] = ItemStack(self.cursor_stack.material, moved, self.cursor_stack.nbt)
        elif target.material == self.cursor_stack.material and target.nbt == self.cursor_stack.nbt:
            moved = min(amount, self.cursor_stack.amount, target.max_stack_size - target.amount)
            target.amount += max(0, moved)
        else:
            return
        self.cursor_stack.amount -= max(0, moved)
        if self.cursor_stack.amount <= 0:
            self.cursor_stack = EmptyItemStack()

    def drop_inventory(self, cursor: bool = True, slot: int | None = None, amount: int | None = None) -> None:
        stack = self.cursor_stack if cursor else self.inventory[int(slot)]
        if stack.is_empty():
            self.sync_inventory()
            return
        if amount is not None and int(amount) <= 0:
            self.sync_inventory()
            return
        amount = stack.amount if amount is None else max(1, min(int(amount), stack.amount))
        dropped = ItemStack(stack.material, amount, stack.nbt)
        stack.amount -= amount
        if stack.amount <= 0:
            if cursor:
                self.cursor_stack = EmptyItemStack()
            else:
                self.inventory[int(slot)] = EmptyItemStack()
        from resources.server.entities.item import Item
        self.world.spawn_entity(Item(self.x + self.width / 2, self.y + 0.5, self.world, dropped))
        self.sync_inventory()

    def count_item_stack(self, item_stack: ItemStack) -> int:
        """Return the total matching amount across the player's inventory."""
        return sum(
            stack.amount for stack in self.inventory
            if not stack.is_empty()
            and stack.material == item_stack.material
            and stack.nbt == item_stack.nbt
        )

    def has_item_stack(self, item_stack: ItemStack, amount: int = 1) -> bool:
        return amount >= 0 and self.count_item_stack(item_stack) >= amount

    def remove_item_stack(self, item_stack: ItemStack, amount: int = 1, *, sync: bool = True) -> bool:
        """Atomically consume ``amount`` matching items, if available."""
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return False
        if amount < 0 or not self.has_item_stack(item_stack, amount):
            return False
        remaining = amount
        for index in range(len(self.inventory)):
            if remaining <= 0:
                break
            slot = self.inventory[index]
            if slot.is_empty() or slot.material != item_stack.material or slot.nbt != item_stack.nbt:
                continue
            removed = min(remaining, slot.amount)
            slot.amount -= removed
            remaining -= removed
            if slot.amount <= 0:
                self.inventory[index] = EmptyItemStack()
        if sync:
            self.sync_inventory()
        return True

    def discard_inventory_item(self, slot: int, amount: int) -> bool:
        """Drop a specified number of items from one inventory slot."""
        try:
            slot, amount = int(slot), int(amount)
        except (TypeError, ValueError):
            return False
        if not 0 <= slot < len(self.inventory) or amount <= 0:
            return False
        before = self.inventory[slot].amount
        if before <= 0 or self.inventory[slot].is_empty():
            return False
        self.drop_inventory(cursor=False, slot=slot, amount=min(amount, before))
        return True

    def on_moving(self):
        rx = int(self.x // 16)
        for x in range(rx - self.world.server.view_distance, rx + self.world.server.view_distance + 1):
            if x not in self.loading_regions and x in self.world.regions:
                self.world.server.send_client_socket(self, self.world.regions[x])
        if self.sprinting:
            self._spawn_sprint_particles()
        else:
            self._last_sprint_particle_x = self.x
            self._sprint_particle_timer = 0

    def _spawn_sprint_particles(self) -> None:
        """疾跑时在脚底生成脚下方块的碎片粒子。

        每 3 帧生成一次（避免粒子过密），方向感知：
        粒子主要向玩家身后散射，模拟跑步扬尘的物理效果。
        玩家原地不动时不生成粒子。
        """
        # 玩家没有水平移动时不生成粒子
        last_x = self._last_sprint_particle_x
        self._last_sprint_particle_x = self.x
        if last_x is None:
            return
        # 粒子只应出现在真正高速疾跑时；按本 tick 的水平位移和状态
        # 过滤掉原地切换疾跑、缓慢起步以及飞行/流体中的移动。
        speed = abs(self.x - last_x)
        if (
            speed < 0.001
            or not self.on_ground
            or self.in_fluid
            or self.flying
            # 客户端移动包只携带位置，不保证服务端 motion 已同步；用相邻
            # 包的位移作为每 tick 速度。0.22 可过滤普通行走的低速阶段。
            or speed < 0.22
        ):
            return

        self._sprint_particle_timer += 1
        if self._sprint_particle_timer % 3 != 0:
            return

        # 获取脚下方块，空气方块不生成粒子
        foot_block_x = _math.floor(self.x + self.width / 2)
        foot_block_y = _math.floor(self.y - 0.05)
        try:
            block_below = self.world.get_block(foot_block_x, foot_block_y, 0)
        except (IndexError, AttributeError, TypeError):
            return
        if block_below is None or getattr(block_below, "block_id", None) == "air":
            return

        # 粒子生成位置：脚底，略微偏向身体中心
        base_x = self.x + self.width / 2
        foot_y = self.y

        # 根据朝向确定身后方向（粒子踢向身后）
        # facing: 0=左(RIGHT), 1=右(LEFT)
        behind_dir = -1.0 if self.facing == 0 else 1.0

        for _ in range(2):
            # 随机偏移：粒子散布在脚底附近
            offset_x = _random.uniform(-0.15, 0.15)
            offset_y = _random.uniform(0.0, 0.1)

            # 水平速度：向身后 + 随机扰动
            vel_x = behind_dir * _random.uniform(0.02, 0.08) + _random.uniform(-0.03, 0.03)
            vel_y = _random.uniform(0.01, 0.06)  # 轻微上扬

            self.world.spawn_particle(SPRINT_STEP(
                base_x + offset_x,
                foot_y + offset_y,
                0,
                count=1,
                motion=(vel_x, vel_y),
                data={"block_id": block_below.block_id},
            ))

    def teleport_to(self, x, y, world = None):
        self.x = x
        self.y = y
        if world:
            self.world = world
        self._teleport_id += 1
        self._pending_teleport_id = self._teleport_id
        self.world.server.send_client_socket(self, self, "Teleport")

    def confirm_teleport(self, teleport_id) -> bool:
        """Accept a client acknowledgement for the most recent teleport."""
        try:
            teleport_id = int(teleport_id)
        except (TypeError, ValueError):
            return False
        if teleport_id != self._pending_teleport_id:
            return False
        self._pending_teleport_id = None
        return True

    @property
    def is_awaiting_teleport_confirmation(self) -> bool:
        return self._pending_teleport_id is not None

    def is_loading_position(self, x_loc: int | Location, y = None, z = None) -> bool:
        """
        检测某个位置是否被改玩家加载
        :param x_loc: 可传入 x 坐标或 Location
        :param y: 可不填写
        :param z: 可不填写
        :return:
        """
        x, y, z = decide_x_or_loc(x_loc, y, z)
        rx = int(x // 16)
        return rx in self.loading_regions

    def __str__(self):
        return self.name
