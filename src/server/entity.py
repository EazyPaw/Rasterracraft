# Commented and arranged by ChatGPT
import ast
import logging
import math
import random
import uuid
from uuid import UUID

from src.server.damange_type import DamageType, GENERIC, MOB_ATTACK, PLAYER_ATTACK
from src.server.location import Vector
from src.server.tags import DamageTag
from src.server.utils import is_safe_value
from src.server.block_collision import EMPTY, coerce_collision_shape
from src.server.attributes import (
    AttributeMap,
    AttributeModifier,
    SPRINTING_SPEED_MODIFIER,
)


class Entity:
    entity_id = "null"
    registry_key = None
    summonable = False
    persistent = False
    sounds = {}

    blocks_block_placement = True
    attackable = True
    translation_key: str | None = None
    ambient_sound_interval = (160, 360)
    initial_ambient_sound_interval = (80, 220)

    def __init__(self, x, y, world):
        self.uuid = uuid.uuid4()
        self.entity_id = type(self).entity_id
        self.x = x
        self.y = y
        self.world = world
        self.motion = Vector(0, 0)
        self.attributes = AttributeMap(on_dirty=self._on_attribute_dirty)
        self.width = 1
        self.height = 1

        self.move_speed = 0.1
        self.movement_acceleration = 0.098
        self.air_acceleration = 0.02
        self.air_friction = 0.91
        self.damping = self.air_friction
        self.gravity = 0.08
        self.drag_vertical = 0.98

        self.fluid_move_speed_multiplier = 0.23
        self.fluid_horizontal_drag = 0.65
        self.fluid_vertical_drag = 0.65
        self.jump_height = 0.42
        self.jump_factor = 1.0
        self.speed_factor = 1.0
        self.max_health = 20
        self.health = self.max_health
        self.hurt_time = 0
        self.on_ground = False
        self.flying = False
        self.sneaking = False
        self.interact_range = 3.5
        self.facing = 0  # 0: 左边 1: 右边
        self.sprinting = False
        self.removed = False
        self.in_fluid = False
        self.in_water = False
        self.swimming_up = False
        self._jumped_this_tick = False
        self.fire_ticks = 0
        self.last_damage_type = None
        self.last_damage_source = None
        self.last_hurt_damage = 0.0
        self.knockback_resistance = 0.0
        self.attack_damage = 1.0
        self.follow_range = 35.0
        self.attack_cooldown_ticks = 0
        self.attack_interval_ticks = 20
        self.attack_animation_ticks = 0
        self.attack_animation_duration = 8
        self.target_uuid: str | None = None
        self.look_angle = 0.0
        self.no_ai = False
        self.silent = False
        self.persistence_required = False
        self.max_step_height = 0.5
        self.drops = []
        self._death_handled = False
        self._ambient_sound_cooldown = self._new_ambient_sound_delay(initial=True)

    def _on_attribute_dirty(self, instance) -> None:
        if instance.definition.id == "minecraft:max_health" and hasattr(self, "health"):
            self.health = max(0.0, min(float(self.health), instance.value))

    def refresh_attribute_modifiers(self) -> None:
        sprinting = bool(getattr(self, "sprinting", False))
        if sprinting == getattr(self, "_sprinting_attribute_state", None):
            return
        entries = (("movement_speed", SPRINTING_SPEED_MODIFIER),) if sprinting else ()
        self.attributes.replace_source("state:sprinting", entries)
        self._sprinting_attribute_state = sprinting

    def get_attribute_instance(self, attribute_id: str):
        self.refresh_attribute_modifiers()
        return self.attributes.get_instance(attribute_id)

    def get_attribute_value(self, attribute_id: str) -> float:
        self.refresh_attribute_modifiers()
        return self.attributes.get_value(attribute_id)

    def get_attribute_base_value(self, attribute_id: str) -> float:
        return self.attributes.get_base_value(attribute_id)

    def set_attribute_base_value(self, attribute_id: str, value: float) -> None:
        self.attributes.set_base_value(attribute_id, value)

    def add_attribute_modifier(
        self,
        attribute_id: str,
        modifier: AttributeModifier,
        *,
        permanent: bool = False,
        source: str | None = None,
        replace: bool = False,
    ) -> None:
        self.attributes.add_modifier(
            attribute_id,
            modifier,
            permanent=permanent,
            source=source,
            replace=replace,
        )

    def remove_attribute_modifier(self, attribute_id: str, modifier_id: str) -> bool:
        return self.attributes.remove_modifier(attribute_id, modifier_id)

    def replace_attribute_modifiers(self, source: str, entries) -> None:
        self.attributes.replace_source(source, entries)

    @property
    def max_health(self) -> float:
        return self.get_attribute_value("max_health")

    @max_health.setter
    def max_health(self, value: float) -> None:
        self.set_attribute_base_value("max_health", value)

    @property
    def scale(self) -> float:
        return self.get_attribute_value("scale")

    @scale.setter
    def scale(self, value: float) -> None:
        self.set_attribute_base_value("scale", value)

    @property
    def width(self) -> float:
        return float(getattr(self, "_base_width", 1.0)) * self.scale

    @width.setter
    def width(self, value: float) -> None:
        scale = self.scale
        self._base_width = float(value) / scale if scale else float(value)

    @property
    def height(self) -> float:
        return float(getattr(self, "_base_height", 1.0)) * self.scale

    @height.setter
    def height(self, value: float) -> None:
        scale = self.scale
        self._base_height = float(value) / scale if scale else float(value)

    @property
    def move_speed(self) -> float:
        return self.get_attribute_value("movement_speed")

    @move_speed.setter
    def move_speed(self, value: float) -> None:
        self.set_attribute_base_value("movement_speed", value)

    @property
    def gravity(self) -> float:
        return self.get_attribute_value("gravity")

    @gravity.setter
    def gravity(self, value: float) -> None:
        self.set_attribute_base_value("gravity", value)

    @property
    def jump_height(self) -> float:
        return self.get_attribute_value("jump_strength")

    @jump_height.setter
    def jump_height(self, value: float) -> None:
        self.set_attribute_base_value("jump_strength", value)

    @property
    def max_step_height(self) -> float:
        return self.get_attribute_value("step_height")

    @max_step_height.setter
    def max_step_height(self, value: float) -> None:
        self.set_attribute_base_value("step_height", value)

    @property
    def knockback_resistance(self) -> float:
        return self.get_attribute_value("knockback_resistance")

    @knockback_resistance.setter
    def knockback_resistance(self, value: float) -> None:
        self.set_attribute_base_value("knockback_resistance", value)

    @property
    def follow_range(self) -> float:
        return self.get_attribute_value("follow_range")

    @follow_range.setter
    def follow_range(self, value: float) -> None:
        self.set_attribute_base_value("follow_range", value)

    @property
    def interact_range(self) -> float:
        return self.get_attribute_value("entity_interaction_range")

    @interact_range.setter
    def interact_range(self, value: float) -> None:
        self.set_attribute_base_value("entity_interaction_range", value)

    @property
    def block_interaction_range(self) -> float:
        return self.get_attribute_value("block_interaction_range")

    @block_interaction_range.setter
    def block_interaction_range(self, value: float) -> None:
        self.set_attribute_base_value("block_interaction_range", value)

    @property
    def tempt_range(self) -> float:
        return self.get_attribute_value("tempt_range")

    @tempt_range.setter
    def tempt_range(self, value: float) -> None:
        self.set_attribute_base_value("tempt_range", value)

    def teleport_to(self, x, y, world=None):
        self.x = x
        self.y = y
        if world:
            self.world = world

    def get_safe_attributes(self):
        """
        获取当前实例的所有安全属性，返回一个字典。
        """
        safe_data = {}
        # 使用 vars(self) 获取实例变量（适用于普通类，不处理 __slots__）
        for key, value in vars(self).items():
            if is_safe_value(value):
                safe_data[key] = value
        return safe_data

    def parse_nbt(self) -> str:
        nbt = self.get_safe_attributes()
        return str(nbt)

    def to_entity_data(self) -> dict:
        self.refresh_attribute_modifiers()
        data = {
            "uuid": str(self.uuid),
            "entity_id": self.entity_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "motion": {"x": self.motion.x, "y": self.motion.y},
            "facing": self.facing,
            "sneaking": self.sneaking,
            "sprinting": self.sprinting,
            "on_ground": self.on_ground,
            "health": self.health,
            "max_health": self.max_health,
            "attributes": self.attributes.sync_snapshot(),
            "hurt_time": self.hurt_time,
            "aggressive": self.get_target() is not None,
            "look_angle": self.look_angle,
            "attack_animation_ticks": self.attack_animation_ticks,
            "attackable": bool(self.attackable),
        }
        if hasattr(self, "z"):
            data["z"] = getattr(self, "z")
        if hasattr(self, "name"):
            data["name"] = getattr(self, "name")
        block = getattr(self, "block", None)
        if block is not None:
            data["block_data"] = block.to_dict()
        item = getattr(self, "item", None)
        if item is not None:
            data["item_data"] = {
                "id": item.material.name_id,
                "amount": item.amount,
                "nbt": item.nbt,
            }

        if self.entity_id == "player" and hasattr(self, "inventory"):
            try:
                selected = int(getattr(self, "selected_slot", 0))
                selected = max(0, min(len(self.inventory) - 1, selected))
                held = self.inventory[selected]
                data["held_item_data"] = {
                    "id": held.material.name_id,
                    "amount": int(getattr(held, "amount", 0)),
                    "nbt": getattr(held, "nbt", {}),
                }
            except (AttributeError, TypeError, ValueError, IndexError):
                pass
            equipment = getattr(self, "equipment", None)
            if isinstance(equipment, dict):
                data["equipment_data"] = {
                    str(slot): {
                        "id": stack.material.name_id,
                        "amount": int(getattr(stack, "amount", 0)),
                        "nbt": getattr(stack, "nbt", {}),
                    }
                    for slot, stack in equipment.items()
                }
            breaking_target = getattr(self, "breaking_target", None)
            data["breaking"] = breaking_target is not None
            data["break_progress"] = float(getattr(self, "break_progress", 0.0))
            data["eating"] = bool(getattr(self, "eating", False))
            data["blocking"] = bool(getattr(self, "blocking", False))
            if breaking_target is not None:
                data["break_target"] = list(breaking_target[:3])
        data.update(self.get_synced_data())
        return data

    def get_synced_data(self) -> dict:
        return {}

    def get_persistent_data(self) -> dict:
        return {}

    def read_persistent_data(self, data: dict) -> None:
        pass

    def to_save_data(self) -> dict:
        registry_key = getattr(type(self), "registry_key", None)
        return {
            "id": str(registry_key) if registry_key is not None else self.entity_id,
            "uuid": str(self.uuid),
            "entity_id": self.entity_id,
            "x": float(self.x),
            "y": float(self.y),
            "z": int(getattr(self, "z", 0)),
            "motion": {"x": float(self.motion.x), "y": float(self.motion.y)},
            "health": float(self.health),
            "attributes": self.attributes.to_persistent_data(),
            "facing": int(self.facing),
            "on_ground": bool(self.on_ground),
            "sneaking": bool(self.sneaking),
            "sprinting": bool(self.sprinting),
            "fire_ticks": max(0, int(self.fire_ticks)),
            "no_ai": bool(self.no_ai),
            "silent": bool(self.silent),
            "persistence_required": bool(self.persistence_required),
            **({"name": str(self.name)} if hasattr(self, "name") else {}),
            "data": self.get_persistent_data(),
        }

    @classmethod
    def create_from_save(cls, data: dict, world):
        return cls(
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            world,
            int(data.get("z", 0)),
        )

    def restore_common_save_data(self, data: dict) -> None:
        try:
            self.uuid = UUID(str(data.get("uuid", self.uuid)))
        except (TypeError, ValueError):
            pass
        self.attributes.load_persistent_data(data.get("attributes", []))
        self.health = max(
            0.0, min(self.max_health, float(data.get("health", self.health)))
        )
        self.facing = 1 if int(data.get("facing", self.facing)) == 1 else 0
        self.on_ground = bool(data.get("on_ground", self.on_ground))
        self.sneaking = bool(data.get("sneaking", self.sneaking))
        self.sprinting = bool(data.get("sprinting", self.sprinting))
        self.fire_ticks = max(0, int(data.get("fire_ticks", self.fire_ticks)))
        self.no_ai = bool(data.get("no_ai", self.no_ai))
        self.silent = bool(data.get("silent", self.silent))
        self.persistence_required = bool(
            data.get("persistence_required", self.persistence_required)
        )
        if isinstance(data.get("name"), str):
            self.name = data["name"][:64]
        motion = data.get("motion", {})
        if isinstance(motion, dict):
            self.motion.x = float(motion.get("x", self.motion.x))
            self.motion.y = float(motion.get("y", self.motion.y))
        subtype = data.get("data", {})
        if isinstance(subtype, dict):
            self.read_persistent_data(subtype)

    def interact(self, player, held_stack) -> bool:
        return False

    @property
    def attack_damage(self):
        return self.get_attribute_value("attack_damage")

    @attack_damage.setter
    def attack_damage(self, value) -> None:
        self.set_attribute_base_value("attack_damage", value)

    def apply_summon_nbt(self, nbt: dict) -> None:
        for attribute_key in ("attributes", "Attributes"):
            if isinstance(nbt.get(attribute_key), list):
                self.attributes.load_persistent_data(nbt[attribute_key])
        aliases = {
            "Health": "health",
            "NoAI": "no_ai",
            "Silent": "silent",
            "PersistenceRequired": "persistence_required",
            "CustomName": "name",
        }
        for raw_key, value in nbt.items():
            key = aliases.get(str(raw_key), str(raw_key))
            if key in {"attributes", "Attributes"}:
                continue
            if key == "health":
                self.health = max(0.0, min(self.max_health, float(value)))
            elif key in {"no_ai", "silent", "persistence_required"}:
                setattr(self, key, bool(value))
            elif key == "name" and isinstance(value, str):
                self.name = value.strip('"')[:64]

    def write_nbt(self, nbt: str):
        nbt = ast.literal_eval(nbt)
        for key, value in nbt.items():
            if hasattr(self, key):
                current_attr = getattr(self, key)
                current_type = type(current_attr)
                if type(value) is current_type:  # 严格类型相等
                    setattr(self, key, value)
                else:
                    logging.warning(
                        f"There exists a incorrect type nbt, expect {type(current_attr)}, but got {type(value)}."
                    )
            else:
                logging.warning(f"Entity {self.uuid} has no attribute {key}.")

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        try:
            block = self.world.get_block(x, y, z)
            getter = getattr(block, "get_collision_box", None)
            shape = (
                getter() if callable(getter) else getattr(block, "collision_box", EMPTY)
            )
            return bool(coerce_collision_shape(shape))
        except (IndexError, AttributeError, TypeError, ValueError):
            return False

    def _get_collision_boxes(self, x: int, y: int, z: int = 0):
        try:
            block = self.world.get_block(x, y, z)
            getter = getattr(block, "get_collision_box", None)
            shape = coerce_collision_shape(
                getter() if callable(getter) else getattr(block, "collision_box", EMPTY)
            )
            return tuple(box.translated(x, y) for box in shape)
        except (IndexError, AttributeError, TypeError, ValueError):
            return ()

    def _get_block_at(self, x: float, y: float, z: int = 0):
        try:
            return self.world.get_block(math.floor(x), math.floor(y), z)
        except (IndexError, AttributeError, TypeError):
            return None

    def _get_fluid_interaction(self) -> tuple[bool, float, float]:
        min_x = math.floor(self.x)
        max_x = math.floor(self.x + self.width)
        min_y = math.floor(self.y)
        max_y = math.floor(self.y + self.height)

        flow_x = 0.0
        flow_y = 0.0
        touching = 0

        for block_x in range(min_x, max_x + 1):
            for block_y in range(min_y, max_y + 1):
                block = self._get_block_at(block_x, block_y)
                if not getattr(block, "is_fluid", False):
                    continue

                height_ratio = 1.0
                height_getter = getattr(block, "fluid_height_ratio", None)
                if callable(height_getter):
                    height_ratio = height_getter()
                fluid_top = block_y + max(0.0, min(1.0, height_ratio))
                entity_top = self.y + self.height
                if self.y >= fluid_top or entity_top <= block_y:
                    continue

                touching += 1
                vector_getter = getattr(block, "get_flow_vector", None)
                if callable(vector_getter):
                    fx, fy = vector_getter()
                    flow_x += fx
                    flow_y += fy

        if touching == 0:
            return False, 0.0, 0.0
        return True, flow_x / touching, flow_y / touching

    def _get_water_interaction(self) -> tuple[bool, float, float]:
        return self._get_fluid_interaction()

    def get_ground_block(self):
        return self._get_block_at(self.x + self.width * 0.5, self.y - 0.05)

    def _resolve_landing_block_overlap(self, block) -> bool:
        location = getattr(block, "location", None)
        if location is None:
            return False
        getter = getattr(block, "get_collision_box", None)
        try:
            shape = coerce_collision_shape(
                getter() if callable(getter) else getattr(block, "collision_box", EMPTY)
            )
        except (TypeError, ValueError):
            return False

        entity_top = self.y + self.height
        correction_y = self.y
        for local_box in shape:
            box = local_box.translated(location.x, location.y)
            if not box.overlaps(self.x, self.y, self.x + self.width, entity_top):
                continue
            correction_y = max(correction_y, box.max_y)

        if correction_y <= self.y or self._check_collision_at(self.x, correction_y):
            return False
        self.y = correction_y
        self.motion.y = max(0.0, self.motion.y)
        self.on_ground = bool(self._check_support_at())
        return True

    def on_landed(self, fall_distance: float) -> bool:
        ground = self.get_ground_block()
        location = getattr(ground, "location", None)
        if ground is None or location is None:
            return False
        world = location.world
        coordinates = int(location.x), int(location.y), int(location.z)
        changed = ground.on_fallen_on(self, max(0.0, float(fall_distance)))
        if not changed:
            return False
        replacement = world.get_block(*coordinates)
        return self._resolve_landing_block_overlap(replacement)

    def get_ground_friction(self) -> float:
        block = self.get_ground_block()
        return float(getattr(block, "friction", 0.6)) if block is not None else 1.0

    def get_ground_speed_factor(self) -> float:
        block = self.get_ground_block()
        return float(getattr(block, "speed_factor", 1.0)) if block is not None else 1.0

    def get_ground_jump_factor(self) -> float:
        block = self.get_ground_block()
        return float(getattr(block, "jump_factor", 1.0)) if block is not None else 1.0

    def _is_player_like(self) -> bool:
        return getattr(self, "entity_id", None) == "player" or hasattr(self, "client")

    def _check_collision_at(self, x: float, y: float) -> bool:
        min_x = math.floor(x) - 1
        max_x = math.floor(x + self.width) + 1
        min_y = math.floor(y) - 1
        max_y = math.floor(y + self.height) + 1
        for block_x in range(min_x, max_x + 1):
            for block_y in range(min_y, max_y + 1):
                for box in self._get_collision_boxes(
                    block_x, block_y, getattr(self, "z", 0)
                ):
                    if box.overlaps(x, y, x + self.width, y + self.height):
                        return True
        return False

    def _check_support_at(self, x: float | None = None, y: float | None = None) -> bool:
        x = self.x if x is None else x
        y = self.y if y is None else y
        epsilon = 1.0e-7
        min_x = math.floor(x) - 1
        max_x = math.floor(x + self.width) + 1

        for block_x in range(min_x, max_x + 1):
            for block_y in range(math.floor(y) - 2, math.floor(y) + 1):
                for box in self._get_collision_boxes(
                    block_x, block_y, getattr(self, "z", 0)
                ):
                    horizontal = (
                        box.max_x > x + epsilon and box.min_x < x + self.width - epsilon
                    )
                    top_near_feet = y - 0.01 <= box.max_y <= y + epsilon
                    if horizontal and top_near_feet:
                        return True
        return False

    def _prevent_edge_fall(self, dx: float) -> float:
        if dx == 0 or not self.on_ground or not self.sneaking:
            return dx

        candidate_x = self.x + dx
        if self._check_support_at(candidate_x, self.y):
            return dx

        low, high = 0.0, 1.0
        for _ in range(12):
            fraction = (low + high) * 0.5
            if self._check_support_at(self.x + dx * fraction, self.y):
                low = fraction
            else:
                high = fraction
        return dx * low

    def _sweep_x(self, dx: float):
        if dx == 0:
            return 0.0, False

        y_min, y_max = self.y, self.y + self.height
        leading_x = self.x + self.width if dx > 0 else self.x
        low_x, high_x = sorted((leading_x, leading_x + dx))
        best_hit = None
        for block_x in range(math.floor(low_x) - 2, math.floor(high_x) + 3):
            for block_y in range(math.floor(y_min) - 2, math.floor(y_max) + 3):
                for box in self._get_collision_boxes(
                    block_x, block_y, getattr(self, "z", 0)
                ):
                    if box.max_y <= y_min + 1e-9 or box.min_y >= y_max - 1e-9:
                        continue
                    hit_x = box.min_x if dx > 0 else box.max_x
                    distance = hit_x - leading_x
                    if (dx > 0 and distance >= -1e-9 and distance <= dx + 1e-9) or (
                        dx < 0 and distance <= 1e-9 and distance >= dx - 1e-9
                    ):
                        if best_hit is None or abs(distance) < abs(best_hit):
                            best_hit = distance
        if best_hit is None:
            return dx, False
        hit_x = leading_x + best_hit
        final_x = hit_x - self.width - 0.001 if dx > 0 else hit_x + 0.001
        return final_x - self.x, True

    def _step_height_candidates(self, dx: float) -> tuple[float, ...]:
        try:
            max_step = max(0.0, float(self.max_step_height))
        except (AttributeError, TypeError, ValueError):
            return ()
        if dx == 0 or max_step <= 0:
            return ()

        y_min, y_max = self.y, self.y + self.height
        leading_x = self.x + self.width if dx > 0 else self.x
        low_x, high_x = sorted((leading_x, leading_x + dx))
        candidates = set()
        for block_x in range(math.floor(low_x) - 2, math.floor(high_x) + 3):
            for block_y in range(math.floor(y_min) - 2, math.floor(y_max) + 3):
                for box in self._get_collision_boxes(
                    block_x, block_y, getattr(self, "z", 0)
                ):
                    if box.max_y <= y_min + 1e-9 or box.min_y >= y_max - 1e-9:
                        continue
                    hit_x = box.min_x if dx > 0 else box.max_x
                    distance = hit_x - leading_x
                    in_path = (dx > 0 and -1e-9 <= distance <= dx + 1e-9) or (
                        dx < 0 and dx - 1e-9 <= distance <= 1e-9
                    )
                    if not in_path:
                        continue
                    relative_height = box.max_y - self.y
                    if 1e-9 < relative_height <= max_step + 0.002:
                        candidates.add(round(relative_height + 0.001, 9))
        return tuple(sorted(candidates))

    def _try_step_up(self, dx: float, blocked_dx: float | None = None):
        if (
            dx == 0
            or not self.on_ground
            or self.flying
            or self.in_fluid
            or self.motion.y > 1e-9
        ):
            return None

        if blocked_dx is None:
            blocked_dx, collided = self._sweep_x(dx)
            if not collided:
                return None

        original_x, original_y = self.x, self.y
        best = None
        try:
            for lift in self._step_height_candidates(dx):
                self.x, self.y = original_x, original_y
                actual_up, _ = self._sweep_y(lift)
                if actual_up + 1e-7 < lift:
                    continue
                self.y += actual_up

                step_dx, step_collided = self._sweep_x(dx)
                if abs(step_dx) <= abs(blocked_dx) + 1e-7:
                    continue
                self.x += step_dx

                actual_down, landed = self._sweep_y(-(actual_up + 0.02))
                self.y += actual_down
                if not landed and not self._check_support_at():
                    continue

                vertical_delta = self.y - original_y
                try:
                    max_step = max(0.0, float(self.max_step_height))
                except (AttributeError, TypeError, ValueError):
                    continue
                if vertical_delta < -0.002 or vertical_delta > max_step + 0.005:
                    continue

                candidate = (step_dx, vertical_delta, step_collided)
                if best is None or abs(step_dx) > abs(best[0]) + 1e-7:
                    best = candidate
        finally:
            self.x, self.y = original_x, original_y
        return best

    def can_step_up(self, dx: float) -> bool:
        blocked_dx, collided = self._sweep_x(dx)
        return bool(collided and self._try_step_up(dx, blocked_dx) is not None)

    def _sweep_y(self, dy: float):
        if dy == 0:
            return 0.0, False

        x_min, x_max = self.x, self.x + self.width
        leading_y = self.y + self.height if dy > 0 else self.y
        low_y, high_y = sorted((leading_y, leading_y + dy))
        best_hit = None
        for block_x in range(math.floor(x_min) - 2, math.floor(x_max) + 3):
            for block_y in range(math.floor(low_y) - 2, math.floor(high_y) + 3):
                for box in self._get_collision_boxes(
                    block_x, block_y, getattr(self, "z", 0)
                ):
                    if box.max_x <= x_min + 1e-9 or box.min_x >= x_max - 1e-9:
                        continue
                    hit_y = box.min_y if dy > 0 else box.max_y
                    distance = hit_y - leading_y
                    if (dy > 0 and distance >= -1e-9 and distance <= dy + 1e-9) or (
                        dy < 0 and distance <= 1e-9 and distance >= dy - 1e-9
                    ):
                        if best_hit is None or abs(distance) < abs(best_hit):
                            best_hit = distance
        if best_hit is None:
            return dy, False
        hit_y = leading_y + best_hit
        final_y = hit_y - self.height - 0.001 if dy > 0 else hit_y + 0.001
        return final_y - self.y, True

    def collision_check(self, steps: int = 16):
        requested_dx = self.motion.x
        actual_dx, collided_x = self._sweep_x(requested_dx)
        step = self._try_step_up(requested_dx, actual_dx) if collided_x else None
        if step is not None:
            actual_dx, step_dy, collided_x = step
            self.y += step_dy
        else:
            actual_dx = self._prevent_edge_fall(actual_dx)
        self.x += actual_dx
        if collided_x:
            self.motion.x = 0

        requested_dy = self.motion.y
        actual_dy, collided_y = self._sweep_y(requested_dy)
        self.y += actual_dy
        if collided_y:
            self.motion.y = 0

        self.on_ground = (collided_y and requested_dy < 0) or self._check_support_at()

    def escape_solid_block(self) -> bool:
        if not self._check_collision_at(self.x, self.y):
            return False

        boxes = []
        min_block_x = math.floor(self.x) - 1
        max_block_x = math.floor(self.x + self.width) + 2
        min_block_y = math.floor(self.y) - 1
        max_block_y = math.floor(self.y + self.height) + 2
        for block_x in range(min_block_x, max_block_x):
            for block_y in range(min_block_y, max_block_y):
                boxes.extend(
                    self._get_collision_boxes(block_x, block_y, getattr(self, "z", 0))
                )
        overlapping = [
            box
            for box in boxes
            if box.overlaps(self.x, self.y, self.x + self.width, self.y + self.height)
        ]
        if not overlapping:
            return False

        epsilon = 0.001
        side_candidates = []
        upward_candidates = []
        for box in overlapping:
            side_candidates.extend(
                (
                    box.min_x - self.width - epsilon,
                    box.max_x + epsilon,
                )
            )
            upward_candidates.append(box.max_y + epsilon)

        speed = max(0.0, float(getattr(self, "escape_speed", 0.1)))
        for candidate_x in sorted(
            set(side_candidates), key=lambda candidate: abs(candidate - self.x)
        ):
            if not self._check_collision_at(candidate_x, self.y):
                self.motion.x = -speed if candidate_x < self.x else speed
                return True
        for candidate_y in sorted(
            set(upward_candidates), key=lambda candidate: abs(candidate - self.y)
        ):
            if not self._check_collision_at(self.x, candidate_y):
                self.motion.y = max(speed, self.motion.y)
                return True
        return False

    def _movement_multiplier(self) -> float:
        multiplier = (
            self.get_attribute_value("sneaking_speed") if self.sneaking else 1.0
        )
        if self.sprinting:
            multiplier *= 2.0 if self.flying else 1.0
        multiplier *= self.speed_factor
        if self.in_fluid and not self.flying:
            efficiency = self.get_attribute_value("water_movement_efficiency")
            multiplier *= (
                self.fluid_move_speed_multiplier
                + (1.0 - self.fluid_move_speed_multiplier) * efficiency
            )
        return multiplier

    def get_move_acceleration(self) -> float:

        base = (
            0.049
            if self.flying
            else (
                self.movement_acceleration if self.on_ground else self.air_acceleration
            )
        )

        try:
            if self.flying:
                speed_scale = max(0.0, self.get_attribute_value("flying_speed") / 0.4)
            else:
                speed_scale = max(0.0, float(getattr(self, "move_speed", 0.1)) / 0.1)
        except (TypeError, ValueError):
            speed_scale = 1.0
        base *= speed_scale

        block_factor = 1.0
        if self.on_ground and not self.flying and not self.in_fluid:
            block_factor = self.get_ground_speed_factor()
            efficiency = self.get_attribute_value("movement_efficiency")
            block_factor += (1.0 - block_factor) * efficiency
        return base * self._movement_multiplier() * block_factor

    def move_right(self):
        self.motion.x += self.get_move_acceleration()

    def move_left(self):
        self.motion.x -= self.get_move_acceleration()

    def handle_gravity(self):
        self.motion.y -= self.gravity

    def jump(self):
        if self.on_ground:
            self.motion.y = self.jump_height * self.get_ground_jump_factor()
            self._jumped_this_tick = True
        elif self.flying:
            self.motion += Vector(0, self.jump_height * 1.5)
        elif self._get_fluid_interaction()[0]:
            self.swimming_up = True
            self.motion.y = max(self.motion.y, self.jump_height * 0.08)

    def handle_shift(self):
        if self.flying:
            self.motion -= Vector(0, self.jump_height * 1.5)
        elif self._get_fluid_interaction()[0]:
            self.motion.y -= self.jump_height * 0.2

    def switch_sprint(self, mode=None):
        if mode is None:
            self.sprinting = not self.sprinting
        else:
            self.sprinting = mode

    def update_damping(self):
        if self.flying:
            self.damping = self.air_friction
            return
        if self.in_fluid:
            self.damping = self.fluid_horizontal_drag
            return

        block_below = self.get_ground_block()
        if (
            block_below is None
            or getattr(block_below, "block_id", "air") == "air"
            or not self.on_ground
        ):
            self.damping = self.air_friction
        else:
            self.damping = self.air_friction * self.get_ground_friction()

    def move_update(self):
        self.in_fluid, flow_x, flow_y = self._get_fluid_interaction()
        self.in_water = self.in_fluid
        if self.flying:
            self.motion.y *= 0.5
            if abs(self.motion.y) < 0.1:
                self.motion.y = 0
        elif self.in_fluid:
            self.motion.x += flow_x * 0.018
            self.motion.y += flow_y * 0.018
            if self._is_player_like():
                if self.swimming_up:
                    self.motion.y += self.jump_height * 0.035
                else:
                    self.motion.y -= self.gravity * 0.08
            else:
                self.motion.y -= self.gravity * 0.2
            if not self._is_player_like() and self.motion.y < 0.04:
                self.motion.y += 0.025
        elif not self._jumped_this_tick:
            self.handle_gravity()

        if self.on_ground:
            self.flying = False

        self.collision_check(steps=4)

        self.motion.y *= (
            self.fluid_vertical_drag if self.in_fluid else self.drag_vertical
        )
        self.update_damping()
        self.motion.x *= self.damping
        if abs(self.motion.x) < 0.001:
            self.motion.x = 0

        self.swimming_up = False
        self._jumped_this_tick = False

    def update(self):
        self.tick_damage_state()
        if self.health <= 0:
            self.die()
            return
        if self.attack_cooldown_ticks > 0:
            self.attack_cooldown_ticks -= 1
        if self.attack_animation_ticks > 0:
            self.attack_animation_ticks -= 1
        self.update_ai()
        self._tick_ambient_sound()
        self.move_update()

    def update_ai(self) -> None:
        pass

    def get_target(self):
        ai = getattr(self, "ai", None)
        getter = getattr(ai, "get_target", None)
        return getter() if callable(getter) else None

    def _new_ambient_sound_delay(self, *, initial: bool = False) -> int:
        interval = (
            self.initial_ambient_sound_interval
            if initial
            else self.ambient_sound_interval
        )
        low, high = int(interval[0]), int(interval[1])
        return random.randint(min(low, high), max(low, high))

    def _tick_ambient_sound(self) -> None:
        sound = self.get_sound("ambient")
        if self.silent or not sound:
            return
        self._ambient_sound_cooldown -= 1
        if self._ambient_sound_cooldown > 0:
            return
        self._ambient_sound_cooldown = self._new_ambient_sound_delay()
        server = getattr(self.world, "server", None)
        if server is not None:
            server.broadcast_sound(
                sound, self.x, self.y, getattr(self, "z", 0), volume=0.9
            )

    def tick_damage_state(self) -> None:
        if self.hurt_time <= 0:
            self.hurt_time = 0
            self.last_hurt_damage = 0.0
            return
        self.hurt_time -= 1
        if self.hurt_time <= 0:
            self.hurt_time = 0
            self.last_hurt_damage = 0.0

    def can_take_damage(self, damage_type: type[DamageType] = GENERIC) -> bool:
        return not self.removed and self.health > 0

    @staticmethod
    def _damage_type_has_tag(damage_type, tag: DamageTag) -> bool:
        checker = getattr(damage_type, "has_tag", None)
        if callable(checker):
            return bool(checker(tag))
        tags = getattr(damage_type, "tags", ())
        return tag in tags or tag.value in tags

    @staticmethod
    def calculate_armor_reduction(
        damage: float, armor: float, toughness: float
    ) -> float:
        damage = max(0.0, float(damage))
        armor = max(0.0, min(30.0, float(armor)))
        toughness = max(0.0, min(20.0, float(toughness)))
        effective_armor = min(
            20.0,
            max(armor * 0.2, armor - damage / (2.0 + toughness * 0.25)),
        )
        return damage * (1.0 - effective_armor / 25.0)

    def modify_damage_for_armor(
        self, damage: float, damage_type: type[DamageType]
    ) -> float:
        if self._damage_type_has_tag(damage_type, DamageTag.BYPASSES_ARMOR):
            return max(0.0, float(damage))
        try:
            armor, toughness = self.get_armor_attr()
            return self.calculate_armor_reduction(damage, armor, toughness)
        except (TypeError, ValueError):
            return max(0.0, float(damage))

    def apply_knockback(self, knockback: Vector) -> None:
        if not isinstance(knockback, Vector):
            raise TypeError("knockback must be a Vector")
        resistance = max(
            0.0,
            min(1.0, self.get_attribute_value("knockback_resistance")),
        )
        adjusted = knockback * (1.0 - resistance)
        self.motion.x += adjusted.x
        self.motion.y = max(self.motion.y, adjusted.y)

    def apply_damage(
        self,
        amount: float,
        damage_type: type[DamageType] = GENERIC,
        source=None,
        knockback: Vector | None = None,
    ) -> float:
        try:
            raw_damage = max(0.0, float(amount))
        except (TypeError, ValueError):
            return 0.0
        if raw_damage <= 0 or not self.can_take_damage(damage_type):
            return 0.0

        bypasses_cooldown = self._damage_type_has_tag(
            damage_type, DamageTag.BYPASSES_COOLDOWN
        )
        already_hurt = self.hurt_time > 0 and not bypasses_cooldown
        if already_hurt:
            if raw_damage <= self.last_hurt_damage:
                return 0.0
            damage_to_process = raw_damage - self.last_hurt_damage
            self.last_hurt_damage = raw_damage
        else:
            damage_to_process = raw_damage
            self.last_hurt_damage = raw_damage
            self.hurt_time = 10

        reduced_damage = self.modify_damage_for_armor(damage_to_process, damage_type)
        old_health = float(self.health)
        self.health = max(0.0, old_health - reduced_damage)
        actual_damage = old_health - self.health
        if actual_damage <= 0:
            return 0.0

        self.last_damage_type = damage_type
        self.last_damage_source = source
        if knockback is not None:
            self.apply_knockback(knockback)
        self.on_damage_applied(actual_damage, raw_damage, damage_type, source)
        return actual_damage

    def on_damage_applied(
        self,
        actual_damage: float,
        raw_damage: float,
        damage_type: type[DamageType],
        source,
    ) -> None:
        sound = self.get_hurt_sound(damage_type, actual_damage)
        server = getattr(self.world, "server", None)
        if sound and server is not None:
            server.broadcast_sound(sound, self.x, self.y, getattr(self, "z", 0))
        ai = getattr(self, "ai", None)
        notifier = getattr(ai, "on_hurt", None)
        if callable(notifier) and self.health > 0:
            notifier(source)

    def get_hurt_sound(
        self, damage_type: type[DamageType], actual_damage: float
    ) -> str | None:
        return None if self.health <= 0 else self.get_sound("hurt")

    def get_sound(self, event: str) -> str | None:
        sound = self.sounds.get(event)
        return str(sound) if sound else None

    def get_attack_damage(self, target=None) -> float:
        return max(0.0, float(getattr(self, "attack_damage", 1.0)))

    def get_attack_knockback(self, target) -> Vector:
        source_center = self.x + self.width * 0.5
        target_center = target.x + target.width * 0.5
        delta_x = target_center - source_center
        if abs(delta_x) < 1e-8:
            delta_x = 1.0 if int(getattr(self, "facing", 1)) == 1 else -1.0
        strength = 0.4 + self.get_attribute_value("attack_knockback")
        return Vector(strength if delta_x > 0 else -strength, 0.2)

    def attack(
        self,
        target,
        damage_type: type[DamageType] | None = None,
        amount: float | None = None,
        knockback: Vector | None = None,
    ) -> float:
        if target is self or not hasattr(target, "apply_damage"):
            return 0.0
        if damage_type is None:
            damage_type = PLAYER_ATTACK if self.entity_id == "player" else MOB_ATTACK
        if amount is None:
            amount = self.get_attack_damage(target)
        if knockback is None:
            knockback = self.get_attack_knockback(target)
        return target.apply_damage(
            amount, damage_type, source=self, knockback=knockback
        )

    def try_attack(self, target) -> bool:
        if self.attack_cooldown_ticks > 0:
            return False
        self.attack_cooldown_ticks = self.attack_interval_ticks
        self.attack_animation_ticks = self.attack_animation_duration
        return self.attack(target) > 0

    def get_display_name_data(self):
        custom_name = getattr(self, "name", None)
        if custom_name:
            return str(custom_name)
        if self.translation_key:
            return {"translate": self.translation_key}
        return self.entity_id.replace("_", " ").title()

    def get_death_message(self) -> dict:
        damage_type = self.last_damage_type or GENERIC
        message_id = getattr(damage_type, "message_id", "generic") or "generic"
        args = [self.get_display_name_data()]
        source = self.last_damage_source
        if source is not None:
            name_getter = getattr(source, "get_display_name_data", None)
            args.append(name_getter() if callable(name_getter) else str(source))
        builder = getattr(damage_type, "get_death_info", None)
        if callable(builder):
            return builder(*args)
        return {"key": f"death.attack.{message_id}", "args": args}

    def die(self) -> None:
        if not self.emit_death_effects():
            return
        remover = getattr(self.world, "remove_entity", None)
        if callable(remover):
            remover(self)

    def emit_death_effects(self) -> bool:
        if self._death_handled or self.removed:
            return False
        self._death_handled = True
        server = getattr(self.world, "server", None)
        death_sound = self.get_sound("death")
        if death_sound and not self.silent and server is not None:
            server.broadcast_sound(death_sound, self.x, self.y, getattr(self, "z", 0))
        self.spawn_death_particles()
        self.spawn_drops()
        self.spawn_experience_reward()
        return True

    def get_experience_reward(self) -> int:
        return max(0, int(getattr(self, "experience_reward", 0)))

    def spawn_experience_reward(self) -> None:
        source = self.last_damage_source
        if getattr(source, "entity_id", None) != "player":
            return
        reward = self.get_experience_reward()
        spawner = getattr(self.world, "spawn_experience", None)
        if reward > 0 and callable(spawner):
            spawner(
                self.x + self.width * 0.5,
                self.y + self.height * 0.5,
                getattr(self, "z", 0),
                reward,
            )

    def spawn_death_particles(self) -> None:
        spawn_particle = getattr(self.world, "spawn_particle", None)
        if not callable(spawn_particle):
            return
        from src.server.particles import GENERIC

        spawn_particle(
            GENERIC(
                self.x + self.width * 0.5,
                self.y + self.height * 0.5,
                getattr(self, "z", 0),
                count=20,
                motion=(0.0, 0.025),
                data={
                    "position_spread": [self.width * 0.65, self.height * 0.65],
                    "motion_spread": [0.07, 0.05],
                },
            )
        )

    def drop_item_stack(self, stack, *, speed: float = 0.3, pickup_delay: int = 10):
        if stack is None or stack.is_empty() or stack.amount <= 0:
            return None
        spawn_entity = getattr(self.world, "spawn_entity", None)
        if not callable(spawn_entity):
            return None
        from src.server.entities.item import Item

        direction = 1.0 if int(getattr(self, "facing", 1)) == 1 else -1.0
        angle = math.radians(float(getattr(self, "look_angle", 0.0)))
        forward_x = direction * math.cos(angle)
        forward_y = direction * math.sin(angle)
        head_x = self.x + self.width * 0.5
        head_y = self.y + max(0.1, self.height * 0.85)
        launch_offset = max(0.2, self.width * 0.5 + 0.08)
        dropped = Item(
            head_x + forward_x * launch_offset,
            head_y + forward_y * launch_offset,
            self.world,
            stack,
            int(getattr(self, "z", 0)),
        )
        launch_speed = max(0.0, float(speed))
        dropped.motion.x = forward_x * launch_speed
        dropped.motion.y = forward_y * launch_speed
        dropped.pickup_delay = max(0, int(pickup_delay))
        spawn_entity(dropped)
        return dropped

    def spawn_drops(self) -> None:
        for stack in self.get_drops():
            if stack is None or stack.is_empty() or stack.amount <= 0:
                continue
            self.drop_item_stack(stack, speed=0.1, pickup_delay=10)

    def get_armor_attr(self):
        """
        返回实体的护甲值和盔甲韧性
        :return:
        """
        return (
            self.get_attribute_value("armor"),
            self.get_attribute_value("armor_toughness"),
        )

    def calc_entity_distance(self, other: UUID | str) -> float:
        """
        计算实体到另一个实体之间的距离
        :param other: 可为实体对象/实体UUID/实体UUID的字符串形式
        :return: float 距离
        """
        if isinstance(other, UUID):
            other: Entity = self.world.entities[str(other)]
        if isinstance(other, str):
            other: Entity = self.world.entities[other]
        xd = self.x - other.x
        yd = self.y - other.y
        distance = math.sqrt(xd**2 + yd**2)
        return distance

    def get_drops(self):
        from src.server.item_class import ItemStack

        result = []
        for stack in self.drops:
            if stack is None or getattr(stack, "amount", 0) <= 0:
                continue
            result.append(
                ItemStack(
                    stack.material,
                    int(stack.amount),
                    dict(getattr(stack, "nbt", {})),
                )
            )
        return result
