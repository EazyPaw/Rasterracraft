import math as _math
import random as _random

from resources.client.game_mode import SurvivalMode
from resources.server.attributes import EATING_SPEED_MODIFIER
from resources.server.damange_type import DamageType, FALL, GENERIC, STARVE
from resources.server.entity import Entity
from resources.server.inventory import Inventory, serialize_inventory, stack_to_payload
from resources.server.item_class import EmptyItemStack, ItemStack
from resources.server.location import Location, decide_x_or_loc
from resources.server.material_class import Food
from resources.server.particles import ITEM, SPRINT_STEP
from resources.server.world_class import World


class Player(Entity):
    # Mining remains server-timed, but action packets and the 20 TPS loop can
    # drift briefly under latency.  Slow actions (especially underwater)
    # should not lose all accumulated progress because of one short gap.
    BREAK_KEEPALIVE_GRACE_TICKS = 10
    BREAK_MIN_PROGRESS_TOLERANCE = 0.04
    BREAK_MAX_PROGRESS_TOLERANCE = 0.12
    BREAK_FINISH_GRACE_TICKS = 4
    MAX_FOOD_LEVEL = 20
    EXHAUSTION_THRESHOLD = 4.0
    NATURAL_REGEN_FOOD_LEVEL = 18
    NATURAL_REGEN_TICKS = 80
    STARVATION_TICKS = 80

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
        self.block_interaction_range = 5.0
        self.interact_range = 5.0
        self.set_attribute_base_value("waypoint_receive_range", 60_000_000.0)
        self.set_attribute_base_value("waypoint_transmit_range", 60_000_000.0)
        self._equipment_attribute_signature = None
        self.food_level = 20
        self.saturation = 5.0
        self.experience = 0
        self.experience_level = 0
        self.gamemode = gamemode if gamemode is not None else SurvivalMode
        self.inventory = Inventory(36)
        self.equipment = {
            slot: EmptyItemStack()
            for slot in ("offhand", "head", "chest", "legs", "feet")
        }
        self.crafting_grid = Inventory(9)
        self.cursor_stack = EmptyItemStack()
        self._initialize_inventory()
        self.selected_slot = 0
        # The miner predicts progress locally.  The 20 TPS server keeps an
        # independent verifier timeline and broadcasts it to observers; a
        # premature finish request is rejected with an authoritative block.
        self.breaking_target: tuple[int, int, int, str] | None = None
        self.break_progress = 0.0
        self._breaking_tool_key = None
        self._last_break_action_tick = -10_000
        self.eating = False
        self._eating_slot: int | None = None
        self._eating_material_id: str | None = None
        self._eat_progress = 0
        self._last_eat_action_tick = -10_000
        self._last_move_tick = -1
        self.attack_strength_ticker = 20
        self._last_attribute_attack_tick: int | None = None
        self.exhaustion = 0.0
        self.food_tick_timer = 0
        self.fall_distance = 0.0
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
        from resources.server.materials import (
            APPLE, BREAD, FLINT_AND_STEEL, GLOWSTONE, SAND, WATER,
            get_material_by_id,
        )
        if getattr(self.gamemode, "name_id", "survival") == "creative":
            for i in range(4):
                self.inventory[i] = ItemStack(GLOWSTONE(), 64)
            for i in range(8, 16):
                self.inventory[i] = ItemStack(SAND(), 64)
            for i in range(4, 8):
                self.inventory[i] = ItemStack(WATER(), 64)
            self.inventory[9] = ItemStack(get_material_by_id("tnt"), 64)
            self.inventory[10] = ItemStack(FLINT_AND_STEEL(), 1)
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

    def get_equipped_item(self, slot: str) -> ItemStack:
        slot = str(slot).lower().replace("_", "")
        if slot == "mainhand":
            return self.inventory[self.selected_slot]
        if slot not in self.equipment:
            raise ValueError(f"unknown equipment slot: {slot}")
        return self.equipment[slot]

    def set_equipped_item(self, slot: str, stack: ItemStack, *, sync: bool = True) -> None:
        """Server-side equipment hook for armor, offhand items, and future UI."""
        slot = str(slot).lower().replace("_", "")
        if slot == "mainhand":
            self.inventory[self.selected_slot] = stack
        elif slot in self.equipment:
            self.equipment[slot] = stack
        else:
            raise ValueError(f"unknown equipment slot: {slot}")
        self._equipment_attribute_signature = None
        if sync:
            self.sync_inventory()

    def inventory_packet(self) -> dict:
        self.refresh_attribute_modifiers()
        return {
            "__class__": "InventoryUpdate",
            "inventory": serialize_inventory(self.inventory),
            "equipment": {
                slot: stack_to_payload(stack) for slot, stack in self.equipment.items()
            },
            "crafting": serialize_inventory(self.crafting_grid),
            "cursor": stack_to_payload(self.cursor_stack),
            "selected_slot": int(self.selected_slot),
            "health": float(self.health),
            "food_level": int(self.food_level),
            "saturation": float(self.saturation),
            "attributes": self.attributes.sync_snapshot(),
        }

    def sync_inventory(self) -> None:
        self.world.server.send_client_socket(self, self.inventory_packet(), "Forward")

    def can_reach_block(self, x: int, y: int, z: int) -> bool:
        """Return whether a block action is valid from the server position."""
        if self.health <= 0 or z not in (0, 1):
            return False
        if getattr(self.gamemode, "name_id", "survival") == "spectator":
            return False
        center_x = self.x + self.width * 0.5
        center_y = self.y + self.height * 0.5
        dx = x + 0.5 - center_x
        dy = y + 0.5 - center_y
        reach = max(0.0, float(self.block_interaction_range)) + 0.75
        return dx * dx + dy * dy <= reach * reach

    def _send_break_progress(self, target, progress: float, active: bool) -> None:
        if target is None:
            return
        x, y, z, _block_id = target
        packet = {
            "__class__": "BlockBreakProgress",
            "miner_uuid": str(self.uuid),
            "x": x,
            "y": y,
            "z": z,
            "progress": max(0.0, min(1.0, float(progress))),
            "active": bool(active),
        }
        for observer in tuple(self.world.server.players):
            if observer.world is self.world and observer.is_loading_position(x, y, z):
                self.world.server.send_client_socket(observer, packet, "Forward")

    def _broadcast_action_state(self) -> None:
        for observer in tuple(self.world.server.players):
            if observer is self or observer.world is not self.world:
                continue
            if observer.is_loading_position(int(self.x), int(self.y), getattr(self, 'z', 0)):
                self.world.server.send_client_socket(observer, self, "EntityUpdate")

    def clear_breaking(self, *, notify: bool = True) -> None:
        old_target = self.breaking_target
        self.breaking_target = None
        self.break_progress = 0.0
        self._breaking_tool_key = None
        if notify and old_target is not None:
            self._send_break_progress(old_target, 0.0, False)

    def request_breaking(self, x: int, y: int, z: int) -> bool:
        """Accept one keepalive for a server-authoritative mining action."""
        if self.eating:
            self.clear_eating()
        world = self.world
        if not (0 <= y < world.attribute.MAX_BUILD_HEIGHT and z in (0, 1)):
            self.clear_breaking()
            return False
        if x // 16 not in self.client_loaded_regions or not world.is_chunk_loaded(x // 16):
            self.clear_breaking()
            return False
        if not self.can_reach_block(x, y, z):
            self.clear_breaking()
            return False
        block = world.get_block(x, y, z)
        if not getattr(block, "breakable", False) or getattr(block, "block_id", "air") == "air":
            self.clear_breaking()
            return False

        held = self.inventory[self.selected_slot]
        tool_key = (
            getattr(held.material, 'name_id', 'air'),
            repr(getattr(held, 'nbt', {})),
        )
        target = (x, y, z, str(block.block_id))
        if target != self.breaking_target or tool_key != self._breaking_tool_key:
            self.clear_breaking()
            self.breaking_target = target
            self.break_progress = 0.0
            self._breaking_tool_key = tool_key
            self._send_break_progress(target, 0.0, True)
        self._last_break_action_tick = int(getattr(world.server, "server_ticks", 0))
        return True

    def _destroy_delta(self, block) -> float:
        if getattr(self.gamemode, "name_id", "survival") == "creative":
            return 1.0
        hardness = float(getattr(block, "hardness", 1.5))
        if hardness < 0:
            return 0.0
        held = self.inventory[self.selected_slot].material
        speed = 1.0
        if getattr(held, "tool_type", None) == getattr(block, "preferred_tool", None):
            speed = max(0.0, float(getattr(held, "mining_speed", 1.0)))
            speed += self.get_attribute_value("mining_efficiency")
        speed *= self.get_attribute_value("block_break_speed")
        # Do not trust the client's in-fluid/on-ground flags for mining speed.
        inside_block = bool(self._check_collision_at(self.x, self.y))
        if not inside_block:
            if self._get_fluid_interaction()[0]:
                speed *= self.get_attribute_value("submerged_mining_speed")
            if not self._check_support_at():
                speed /= 5.0
        divisor = 30.0 if block.can_harvest(held) else 100.0
        return 1.0 if hardness == 0 else speed / hardness / divisor

    def tick_breaking(self) -> None:
        target = self.breaking_target
        if target is None:
            return
        current_tick = int(getattr(self.world.server, "server_ticks", 0))
        # A bounded grace period absorbs socket/server thread scheduling
        # jitter. Progress is still advanced only by this authoritative loop.
        if current_tick - self._last_break_action_tick > self.BREAK_KEEPALIVE_GRACE_TICKS:
            self.clear_breaking()
            return
        x, y, z, block_id = target
        block = self.world.get_block(x, y, z)
        if (
            getattr(block, "block_id", "air") != block_id
            or not getattr(block, "breakable", False)
            or not self.can_reach_block(x, y, z)
        ):
            self.clear_breaking()
            return

        self.break_progress = min(1.0, self.break_progress + self._destroy_delta(block))
        self._send_break_progress(target, self.break_progress, True)

    def finish_breaking(self, x: int, y: int, z: int) -> bool:
        """Verify a predicted client break and either accept or correct it."""
        world = self.world
        if (
            not (0 <= y < world.attribute.MAX_BUILD_HEIGHT)
            or z not in (0, 1)
            or x // 16 not in self.client_loaded_regions
            or not world.is_chunk_loaded(x // 16)
        ):
            self.clear_breaking()
            return False
        target = self.breaking_target
        block = world.get_block(x, y, z)
        held_stack = self.inventory[self.selected_slot]
        current_tool_key = (
            getattr(held_stack.material, 'name_id', 'air'),
            repr(getattr(held_stack, 'nbt', {})),
        )
        valid_target = (
            target is not None
            and target[:3] == (x, y, z)
            and getattr(block, 'block_id', 'air') == target[3]
            and getattr(block, 'breakable', False)
            and self.can_reach_block(x, y, z)
            and current_tool_key == self._breaking_tool_key
        )
        # Permit a small bounded difference between client and server clocks.
        # The percentage floor matters for slow underwater mining, while the
        # per-tick allowance keeps quick blocks from gaining a large shortcut.
        destroy_delta = self._destroy_delta(block) if valid_target else 0.0
        progress_tolerance = min(
            self.BREAK_MAX_PROGRESS_TOLERANCE,
            max(
                self.BREAK_MIN_PROGRESS_TOLERANCE,
                destroy_delta * self.BREAK_FINISH_GRACE_TICKS,
            ),
        )
        enough_progress = valid_target and (
            destroy_delta >= 1.0
            or self.break_progress >= 1.0 - progress_tolerance - 1.0e-9
        )
        if not enough_progress:
            self.clear_breaking()
            world.server.send_client_socket(self, {
                '__class__': 'BlockBreakCorrection',
                'x': x, 'y': y, 'z': z,
                'block_data': block.to_dict(),
            }, 'Forward')
            return False

        tool = held_stack.material
        self.clear_breaking(notify=False)
        experience = world.break_block(x, y, z, tool=tool)
        self.add_exhaustion(0.005)
        self._send_break_progress(target, 0.0, False)
        if experience:
            self.experience += experience
            world.server.send_client_socket(
                self, {'__class__': 'Experience', 'amount': experience}, 'Forward'
            )
        return True

    def request_eating(self) -> bool:
        if self.breaking_target is not None:
            self.clear_breaking()
        held = self.inventory[self.selected_slot]
        material_id = getattr(held.material, 'name_id', 'air')
        food = held.material
        if held.is_empty() or not isinstance(food, Food) or not food.can_consume(self):
            self.clear_eating()
            return False
        if self._eating_slot != self.selected_slot or self._eating_material_id != material_id:
            self.clear_eating()
            self.eating = True
            self._eating_slot = self.selected_slot
            self._eating_material_id = material_id
            self._eat_progress = 0
            self.replace_attribute_modifiers("state:eating", (
                ("movement_speed", EATING_SPEED_MODIFIER),
            ))
            self._broadcast_action_state()
        self._last_eat_action_tick = int(getattr(self.world.server, 'server_ticks', 0))
        return True

    def can_consume_food(self, food: Food) -> bool:
        if self.health <= 0:
            return False
        if getattr(self.gamemode, "name_id", "survival") != "survival":
            return False
        return bool(food.always_edible or self.food_level < self.MAX_FOOD_LEVEL)

    def consume_food(self, food: Food) -> None:
        """Apply one completed food use using Bedrock hunger values."""
        nutrition = max(0, int(food.food_value))
        saturation_gain = nutrition * max(0.0, float(food.saturation_modifier)) * 2.0
        self.food_level = min(self.MAX_FOOD_LEVEL, self.food_level + nutrition)
        self.saturation = min(
            float(self.food_level),
            max(0.0, self.saturation) + saturation_gain,
        )
        # Bedrock grants one additional heart once when food is completed
        # while natural regeneration is available.  It is paid for through
        # the same 6 exhaustion per health point as timed regeneration.
        if self.food_level >= self.NATURAL_REGEN_FOOD_LEVEL and self.health < self.max_health:
            healed = min(2.0, float(self.max_health) - float(self.health))
            self.health += healed
            self.add_exhaustion(6.0 * healed)

    def clear_eating(self) -> None:
        was_eating = self.eating
        self.eating = False
        self.replace_attribute_modifiers("state:eating", ())
        self._eating_slot = None
        self._eating_material_id = None
        self._eat_progress = 0
        if was_eating:
            self._broadcast_action_state()

    def _mouth_position(self) -> tuple[float, float, int]:
        direction = 1.0 if int(self.facing) == 1 else -1.0
        angle = _math.radians(float(self.look_angle))
        forward = 0.27 * direction
        down = -0.06
        return (
            self.x + self.width * 0.5 + forward * _math.cos(angle) - down * _math.sin(angle),
            self.y + 1.55 + forward * _math.sin(angle) + down * _math.cos(angle),
            int(getattr(self, 'z', 0)),
        )

    def _spawn_eating_particles(self, material_id: str) -> None:
        mouth_x, mouth_y, z = self._mouth_position()
        direction = 1.0 if int(self.facing) == 1 else -1.0
        self.world.spawn_particle(ITEM(
            mouth_x,
            mouth_y,
            z,
            count=3,
            motion=(-0.018 * direction, -0.035),
            data={
                'item_id': material_id,
                'position_spread': (0.04, 0.025),
                'motion_spread': (0.025, 0.018),
            },
        ))

    def tick_eating(self) -> None:
        if not self.eating:
            return
        current_tick = int(getattr(self.world.server, 'server_ticks', 0))
        if current_tick - self._last_eat_action_tick > 2:
            self.clear_eating()
            return
        held = self.inventory[self.selected_slot]
        material_id = getattr(held.material, 'name_id', 'air')
        food = held.material
        if (
            self.selected_slot != self._eating_slot
            or material_id != self._eating_material_id
            or held.is_empty()
            or not isinstance(food, Food)
            or not food.can_consume(self)
        ):
            self.clear_eating()
            return
        self._eat_progress += 1
        if self._eat_progress % 4 == 0:
            self._spawn_eating_particles(material_id)
        if self._eat_progress < food.consume_duration_ticks:
            return
        food.on_consume(self)
        held.reduce_amount(1)
        mouth_x, mouth_y, z = self._mouth_position()
        self.world.server.broadcast_sound('random.eat', mouth_x, mouth_y, z)
        self.sync_inventory()
        self.clear_eating()

    def record_server_movement(self, previous_y: float, was_on_ground: bool,
                               horizontal_distance: float) -> None:
        """Update server-owned fall and exhaustion state after an accepted move."""
        distance = max(0.0, float(horizontal_distance))
        if self.in_fluid:
            swim_distance = _math.hypot(distance, float(self.y) - float(previous_y))
            self.add_exhaustion(swim_distance * 0.01)
        elif self.sprinting:
            self.add_exhaustion(distance * 0.1)
        if (
            not self.in_fluid
            and not self.flying
            and was_on_ground
            and not self.on_ground
            and self.y > previous_y
        ):
            self.add_exhaustion(0.2 if self.sprinting else 0.05)
        if self.in_fluid or self.flying:
            self.fall_distance = 0.0
            return
        fallen = previous_y - self.y
        if fallen > 0:
            self.fall_distance += fallen
        if self.on_ground and not was_on_ground:
            landing_distance = self.fall_distance
            position_corrected = self.on_landed(landing_distance)
            if position_corrected:
                # The acknowledgement gate prevents already queued client
                # movement from restoring the now-embedded position.
                self.teleport_to(self.x, self.y)
            if (
                getattr(self.gamemode, "name_id", "survival") == "survival"
                and landing_distance > self.get_attribute_value("safe_fall_distance")
            ):
                safe_distance = self.get_attribute_value("safe_fall_distance")
                fall_damage = int(
                    (landing_distance - safe_distance)
                    * self.get_attribute_value("fall_damage_multiplier")
                    + 0.999
                )
                self.apply_damage(fall_damage, FALL, source=None)
            self.fall_distance = 0.0

    def _tick_survival_state(self) -> None:
        if getattr(self.gamemode, "name_id", "survival") != "survival":
            return
        if self.health <= 0:
            return

        state_changed = False
        # Vanilla caps queued exhaustion at 40 and performs at most one
        # four-point drain per game tick.
        if self.exhaustion >= self.EXHAUSTION_THRESHOLD:
            self.exhaustion -= self.EXHAUSTION_THRESHOLD
            if self.saturation > 0:
                self.saturation = max(0.0, self.saturation - 1.0)
                state_changed = True
            elif self.food_level > 0:
                self.food_level -= 1
                state_changed = True
        if self.food_level <= 6:
            self.sprinting = False

        if self.food_level >= self.NATURAL_REGEN_FOOD_LEVEL and self.health < self.max_health:
            self.food_tick_timer += 1
            if self.food_tick_timer >= self.NATURAL_REGEN_TICKS:
                healed = min(1.0, float(self.max_health) - float(self.health))
                self.health += healed
                self.add_exhaustion(6.0 * healed)
                self.food_tick_timer = 0
                state_changed = True
        elif self.food_level == 0:
            self.food_tick_timer += 1
            if self.food_tick_timer >= self.STARVATION_TICKS:
                self.apply_damage(1, STARVE, source=None)
                self.food_tick_timer = 0
        else:
            self.food_tick_timer = 0
        if state_changed:
            self.sync_inventory()

    def add_exhaustion(self, amount: float) -> None:
        if getattr(self.gamemode, "name_id", "survival") != "survival" or self.health <= 0:
            return
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return
        if amount > 0:
            self.exhaustion = min(40.0, self.exhaustion + amount)

    def tick_server(self) -> None:
        """Advance state which must never be supplied by a client packet."""
        self.tick_damage_state()
        if self.attack_cooldown_ticks > 0:
            self.attack_cooldown_ticks -= 1
        if self.attack_animation_ticks > 0:
            self.attack_animation_ticks -= 1
        self.attack_strength_ticker += 1
        self._tick_survival_state()
        self.tick_breaking()
        self.tick_eating()
        self._sync_modified_attributes()

    def _sync_modified_attributes(self) -> None:
        """Flush server-owned syncable attribute changes to tracking clients."""
        self.refresh_attribute_modifiers()
        if not self.attributes.take_dirty_syncable():
            return
        server = getattr(self.world, "server", None)
        if server is None or not hasattr(server, "send_client_socket"):
            return
        server.send_client_socket(self, {
            "__class__": "AttributeUpdate",
            "uuid": str(self.uuid),
            "attributes": self.attributes.sync_snapshot(),
            "max_health": float(self.max_health),
        }, "Forward")
        for observer in tuple(getattr(server, "players", ())):
            if observer is self or observer.world is not self.world:
                continue
            if observer.is_loading_position(int(self.x), int(self.y), getattr(self, "z", 0)):
                server.send_client_socket(observer, self, "EntityUpdate")

    def can_take_damage(self, damage_type: type[DamageType] = GENERIC) -> bool:
        mode = getattr(self.gamemode, "name_id", "survival")
        return mode not in {"creative", "spectator"} and super().can_take_damage(damage_type)

    def attack(self, target, damage_type: type[DamageType] | None = None,
               amount: float | None = None, knockback=None) -> float:
        current_tick = int(getattr(getattr(self.world, "server", None), "server_ticks", 0))
        if self._last_attribute_attack_tick is not None:
            self.attack_strength_ticker = max(
                self.attack_strength_ticker,
                current_tick - self._last_attribute_attack_tick,
            )
        if amount is None:
            strength = self.get_attack_strength_scale(0.5)
            amount = self.get_attack_damage(target) * (0.2 + strength * strength * 0.8)
        self.attack_strength_ticker = 0
        self._last_attribute_attack_tick = current_tick
        actual_damage = super().attack(target, damage_type, amount, knockback)
        if actual_damage > 0:
            self.add_exhaustion(0.1)
        return actual_damage

    def get_attack_strength_scale(self, partial_tick: float = 0.0) -> float:
        """Return Java's 0..1 attack recharge strength from attack_speed."""
        attack_speed = self.get_attribute_value("attack_speed")
        if attack_speed <= 0.0:
            return 0.0
        recharge_ticks = 20.0 / attack_speed
        return max(0.0, min(1.0, (self.attack_strength_ticker + partial_tick) / recharge_ticks))

    def get_attack_damage(self, target=None) -> float:
        return super().get_attack_damage(target)

    def refresh_attribute_modifiers(self) -> None:
        """Install modifiers from the authoritative selected server stack."""
        super().refresh_attribute_modifiers()
        try:
            selected = max(0, min(len(self.inventory) - 1, int(self.selected_slot)))
            equipped = {"mainhand": self.inventory[selected], **self.equipment}
            signature = tuple(
                (
                    slot,
                    getattr(stack.material, "name_id", "air"),
                    repr(getattr(stack, "nbt", {})),
                    int(getattr(stack, "amount", 0)),
                )
                for slot, stack in equipped.items()
            )
        except (AttributeError, IndexError, TypeError, ValueError):
            signature = None
            equipped = {}
        if signature == getattr(self, "_equipment_attribute_signature", None):
            return
        entries = tuple(
            entry
            for slot, stack in equipped.items()
            for entry in stack.get_attribute_modifiers(slot)
        )
        self.attributes.replace_source("equipment", entries)
        self._equipment_attribute_signature = signature

    def get_hurt_sound(self, damage_type: type[DamageType], actual_damage: float) -> str | None:
        if self.health <= 0:
            return None
        if damage_type is FALL:
            return self.get_sound("fall_big" if actual_damage >= 5 else "fall_small")
        return self.get_sound("hurt")

    def on_damage_applied(self, actual_damage: float, raw_damage: float,
                          damage_type: type[DamageType], source) -> None:
        super().on_damage_applied(actual_damage, raw_damage, damage_type, source)
        self.add_exhaustion(getattr(damage_type, "exhaustion", 0.0))
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
        self.motion.x = 0.0
        self.motion.y = 0.0
        self.fall_distance = 0.0
        self._last_move_tick = -1
        self.clear_breaking()
        self.clear_eating()
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

    def get_held_item(self) -> ItemStack:
        """
        获取玩家手持物品
        :return:
        """
        return self.inventory[self.selected_slot]
