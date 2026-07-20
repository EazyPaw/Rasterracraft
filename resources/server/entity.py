import ast
import logging
import math
import random
import uuid
from uuid import UUID

from resources.server.damange_type import DamageType, GENERIC, MOB_ATTACK, PLAYER_ATTACK
from resources.server.location import Vector
from resources.server.tags import DamageTag
from resources.server.utils import is_safe_value
from resources.server.block_collision import EMPTY, coerce_collision_shape


class Entity:
    sounds = {}
    translation_key: str | None = None
    ambient_sound_interval = (160, 360)
    initial_ambient_sound_interval = (80, 220)

    def __init__(self, x, y, world):
        self.uuid = uuid.uuid4()
        self.entity_id = "null"
        self.x = x
        self.y = y
        self.world = world
        self.motion = Vector(0, 0)
        self.width = 1
        self.height = 1
        # Movement constants use Minecraft's block/tick units (the game runs
        # at 20 ticks per second).  Keeping these on the base entity makes the
        # same integration code usable by players, items and falling blocks.
        self.move_speed = 0.1  # vanilla generic.movement_speed
        self.movement_acceleration = 0.098  # 0.1 * 0.98, per tick
        self.air_acceleration = 0.02
        self.air_friction = 0.91
        self.damping = self.air_friction
        self.gravity = 0.08
        self.drag_vertical = 0.98  # v <- (v - gravity) * 0.98
        # Water has both slower input acceleration and stronger drag.  Keep
        # these separate from air/flying damping so movement can never build
        # up faster in water than it does while flying.
        # With the water drag below this gives the documented ~1.295 blocks/s
        # swim speed (0.098 * 0.23 / (1 - 0.65) * 20).
        self.fluid_move_speed_multiplier = 0.23
        self.fluid_horizontal_drag = 0.65
        self.fluid_vertical_drag = 0.65
        self.jump_height = 0.42  # vanilla jump initial velocity
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

    def teleport_to(self, x, y, world = None):
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
        data = {
            'uuid': str(self.uuid),
            'entity_id': self.entity_id,
            'x': self.x,
            'y': self.y,
            'width': self.width,
            'height': self.height,
            'motion': {'x': self.motion.x, 'y': self.motion.y},
            'facing': self.facing,
            'sneaking': self.sneaking,
            'sprinting': self.sprinting,
            'on_ground': self.on_ground,
            'health': self.health,
            'hurt_time': self.hurt_time,
            'aggressive': self.get_target() is not None,
            'look_angle': self.look_angle,
            'attack_animation_ticks': self.attack_animation_ticks,
        }
        if hasattr(self, 'z'):
            data['z'] = getattr(self, 'z')
        if hasattr(self, 'name'):
            data['name'] = getattr(self, 'name')
        block = getattr(self, 'block', None)
        if block is not None:
            data['block_data'] = block.to_dict()
        item = getattr(self, 'item', None)
        if item is not None:
            data['item_data'] = {
                'id': item.material.name_id,
                'amount': item.amount,
                'nbt': item.nbt,
            }
        # Players do not expose their inventory wholesale in entity packets,
        # but other clients still need the currently selected stack to render
        # the hand-held item.  Keep this small payload on normal spawn/update
        # packets so it also changes when the hotbar selection changes.
        if self.entity_id == 'player' and hasattr(self, 'inventory'):
            try:
                selected = int(getattr(self, 'selected_slot', 0))
                selected = max(0, min(len(self.inventory) - 1, selected))
                held = self.inventory[selected]
                data['held_item_data'] = {
                    'id': held.material.name_id,
                    'amount': int(getattr(held, 'amount', 0)),
                    'nbt': getattr(held, 'nbt', {}),
                }
            except (AttributeError, TypeError, ValueError, IndexError):
                pass
            breaking_target = getattr(self, 'breaking_target', None)
            data['breaking'] = breaking_target is not None
            data['break_progress'] = float(getattr(self, 'break_progress', 0.0))
            data['eating'] = bool(getattr(self, 'eating', False))
            if breaking_target is not None:
                data['break_target'] = list(breaking_target[:3])
        return data

    def apply_summon_nbt(self, nbt: dict) -> None:
        """Apply common living-entity summon data before subtype-specific data."""
        aliases = {
            "Health": "health",
            "NoAI": "no_ai",
            "Silent": "silent",
            "PersistenceRequired": "persistence_required",
            "CustomName": "name",
        }
        for raw_key, value in nbt.items():
            key = aliases.get(str(raw_key), str(raw_key))
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
                    logging.warning(f"There exists a incorrect type nbt, expect {type(current_attr)}, but got {type(value)}.")
            else:
                logging.warning(f"Entity {self.uuid} has no attribute {key}.")

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        """Compatibility name for a block collision query.

        Older callers use this helper, but collision is now determined by the
        block's shape rather than its unrelated ``solid`` flag.
        """
        try:
            block = self.world.get_block(x, y, z)
            getter = getattr(block, "get_collision_box", None)
            shape = getter() if callable(getter) else getattr(block, "collision_box", EMPTY)
            return bool(coerce_collision_shape(shape))
        except (IndexError, AttributeError, TypeError, ValueError):
            return False

    def _get_collision_boxes(self, x: int, y: int, z: int = 0):
        """Return world-space collision boxes for one block cell."""
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
        """Return the block under the entity's feet, if any."""
        return self._get_block_at(self.x + self.width * 0.5, self.y - 0.05)

    def get_ground_friction(self) -> float:
        """Vanilla horizontal multiplier for the current surface."""
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
        """Return whether the entity's *open* AABB overlaps a solid block.

        The old inclusive ``floor(x + width)`` test treated an entity that was
        merely touching a block face as already inside it.  That produced
        sticky walls and, more importantly, made the ground test report true
        when the player was touching a wall.
        """
        min_x = math.floor(x) - 1
        max_x = math.floor(x + self.width) + 1
        min_y = math.floor(y) - 1
        max_y = math.floor(y + self.height) + 1
        for block_x in range(min_x, max_x + 1):
            for block_y in range(min_y, max_y + 1):
                for box in self._get_collision_boxes(block_x, block_y, getattr(self, "z", 0)):
                    if box.overlaps(x, y, x + self.width, y + self.height):
                        return True
        return False

    def _check_support_at(self, x: float | None = None, y: float | None = None) -> bool:
        """Check only the blocks immediately below the entity's feet."""
        x = self.x if x is None else x
        y = self.y if y is None else y
        epsilon = 1.0e-7
        min_x = math.floor(x) - 1
        max_x = math.floor(x + self.width) + 1
        # Collision resolution leaves a tiny gap to avoid re-entering a face.
        for block_x in range(min_x, max_x + 1):
            for block_y in range(math.floor(y) - 2, math.floor(y) + 1):
                for box in self._get_collision_boxes(block_x, block_y, getattr(self, "z", 0)):
                    horizontal = box.max_x > x + epsilon and box.min_x < x + self.width - epsilon
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

        # Find the last point that still has a supporting block.  A binary
        # search handles both directions and worlds with irregular block
        # edges, without assuming that ``floor(self.x)`` is the supporting
        # block (which fails for negative coordinates).
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
                for box in self._get_collision_boxes(block_x, block_y, getattr(self, "z", 0)):
                    if box.max_y <= y_min + 1e-9 or box.min_y >= y_max - 1e-9:
                        continue
                    hit_x = box.min_x if dx > 0 else box.max_x
                    distance = hit_x - leading_x
                    if (dx > 0 and distance >= -1e-9 and distance <= dx + 1e-9) or \
                            (dx < 0 and distance <= 1e-9 and distance >= dx - 1e-9):
                        if best_hit is None or abs(distance) < abs(best_hit):
                            best_hit = distance
        if best_hit is None:
            return dx, False
        hit_x = leading_x + best_hit
        final_x = hit_x - self.width - 0.001 if dx > 0 else hit_x + 0.001
        return final_x - self.x, True

    def _step_height_candidates(self, dx: float) -> tuple[float, ...]:
        """Return lifts that could clear horizontal obstacles in ``dx``.

        Candidate heights come from the actual collision-box tops in the
        swept path, so slabs, snow layers and custom collision shapes all use
        the same polymorphic block geometry as ordinary movement.
        """
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
                for box in self._get_collision_boxes(block_x, block_y, getattr(self, "z", 0)):
                    if box.max_y <= y_min + 1e-9 or box.min_y >= y_max - 1e-9:
                        continue
                    hit_x = box.min_x if dx > 0 else box.max_x
                    distance = hit_x - leading_x
                    in_path = (
                        dx > 0 and -1e-9 <= distance <= dx + 1e-9
                    ) or (
                        dx < 0 and dx - 1e-9 <= distance <= 1e-9
                    )
                    if not in_path:
                        continue
                    relative_height = box.max_y - self.y
                    if 1e-9 < relative_height <= max_step + 0.002:
                        # The extra millimetre keeps the open AABB just above
                        # the obstacle top during the horizontal sweep.
                        candidates.add(round(relative_height + 0.001, 9))
        return tuple(sorted(candidates))

    def _try_step_up(self, dx: float, blocked_dx: float | None = None):
        """Find a direct step-up route without permanently moving the entity.

        Returns ``(horizontal_delta, vertical_delta, collided_x)`` when a
        route makes more horizontal progress than the ordinary sweep.
        """
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

                # Settle back down.  This either leaves the feet on the
                # obstacle top or returns them to the original floor after a
                # very narrow shape has been crossed.
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
        """Return whether ``max_step_height`` allows progress through ``dx``."""
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
                for box in self._get_collision_boxes(block_x, block_y, getattr(self, "z", 0)):
                    if box.max_x <= x_min + 1e-9 or box.min_x >= x_max - 1e-9:
                        continue
                    hit_y = box.min_y if dy > 0 else box.max_y
                    distance = hit_y - leading_y
                    if (dy > 0 and distance >= -1e-9 and distance <= dy + 1e-9) or \
                            (dy < 0 and distance <= 1e-9 and distance >= dy - 1e-9):
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

    def _movement_multiplier(self) -> float:
        multiplier = 0.3 if self.sneaking else 1.0
        if self.sprinting:
            multiplier *= 2.0 if self.flying else 1.3
        multiplier *= self.speed_factor
        if self.in_fluid and not self.flying:
            multiplier *= self.fluid_move_speed_multiplier
        return multiplier

    def get_move_acceleration(self) -> float:
        """Horizontal input acceleration for this tick."""
        # Creative flight uses 0.049 blocks/tick² (ten times the walking
        # acceleration), yielding 10.889 blocks/s with 0.91 drag.
        base = 0.049 if self.flying else (
            self.movement_acceleration if self.on_ground else self.air_acceleration
        )
        # ``move_speed`` is the entity's movement-speed attribute.  Older
        # movement code only used ``movement_acceleration`` and therefore
        # changing a mob's speed attribute had no effect.  Keep 0.1 as the
        # vanilla/player reference value and scale the same acceleration path
        # for every entity, including hostile mobs.
        try:
            speed_scale = max(0.0, float(getattr(self, "move_speed", 0.1)) / 0.1)
        except (TypeError, ValueError):
            speed_scale = 1.0
        base *= speed_scale

        block_factor = 1.0
        if self.on_ground and not self.flying and not self.in_fluid:
            block_factor = self.get_ground_speed_factor()
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

    def switch_sprint(self, mode = None):
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
        if block_below is None or getattr(block_below, "block_id", "air") == 'air' or not self.on_ground:
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

        self.motion.y *= self.fluid_vertical_drag if self.in_fluid else self.drag_vertical
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
        """Subtype hook for one AI tick."""

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
            server.broadcast_sound(sound, self.x, self.y, getattr(self, "z", 0), volume=0.9)

    def tick_damage_state(self) -> None:
        """Advance the shared post-hit immunity state by one game tick."""
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
    def calculate_armor_reduction(damage: float, armor: float, toughness: float) -> float:
        """Apply Java's armor/toughness formula, capped at 80% reduction."""
        damage = max(0.0, float(damage))
        armor = max(0.0, min(30.0, float(armor)))
        toughness = max(0.0, min(20.0, float(toughness)))
        effective_armor = min(
            20.0,
            max(armor * 0.2, armor - damage / (2.0 + toughness * 0.25)),
        )
        return damage * (1.0 - effective_armor / 25.0)

    def modify_damage_for_armor(self, damage: float, damage_type: type[DamageType]) -> float:
        if self._damage_type_has_tag(damage_type, DamageTag.BYPASSES_ARMOR):
            return max(0.0, float(damage))
        try:
            armor, toughness = self.get_armor_attr()
            return self.calculate_armor_reduction(damage, armor, toughness)
        except (TypeError, ValueError):
            return max(0.0, float(damage))

    def apply_knockback(self, knockback: Vector) -> None:
        """Apply a directional knockback vector after resistance."""
        if not isinstance(knockback, Vector):
            raise TypeError("knockback must be a Vector")
        resistance = max(
            0.0,
            min(1.0, float(getattr(self, "knockback_resistance", 0.0))),
        )
        adjusted = knockback * (1.0 - resistance)
        self.motion.x += adjusted.x
        self.motion.y = max(self.motion.y, adjusted.y)

    def apply_damage(self, amount: float, damage_type: type[DamageType] = GENERIC,
                     source=None, knockback: Vector | None = None) -> float:
        """Apply one damage event and return the amount of health actually lost.

        During the ten-tick post-hit immunity window, only the amount by which
        a stronger raw hit exceeds the previous raw hit is processed. Armor is
        applied after that comparison, matching Java's ordering.
        """
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

    def on_damage_applied(self, actual_damage: float, raw_damage: float,
                          damage_type: type[DamageType], source) -> None:
        sound = self.get_hurt_sound(damage_type, actual_damage)
        server = getattr(self.world, "server", None)
        if sound and server is not None:
            server.broadcast_sound(sound, self.x, self.y, getattr(self, "z", 0))

    def get_hurt_sound(self, damage_type: type[DamageType], actual_damage: float) -> str | None:
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
        return Vector(0.4 if delta_x > 0 else -0.4, 0.2)

    def attack(self, target, damage_type: type[DamageType] | None = None,
               amount: float | None = None, knockback: Vector | None = None) -> float:
        if target is self or not hasattr(target, "apply_damage"):
            return 0.0
        if damage_type is None:
            damage_type = PLAYER_ATTACK if self.entity_id == "player" else MOB_ATTACK
        if amount is None:
            amount = self.get_attack_damage(target)
        if knockback is None:
            knockback = self.get_attack_knockback(target)
        return target.apply_damage(amount, damage_type, source=self, knockback=knockback)

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
        """Run shared death effects, drops and removal exactly once."""
        if not self.emit_death_effects():
            return
        remover = getattr(self.world, "remove_entity", None)
        if callable(remover):
            remover(self)

    def emit_death_effects(self) -> bool:
        """Play shared death effects once without deciding entity removal."""
        if self._death_handled or self.removed:
            return False
        self._death_handled = True
        server = getattr(self.world, "server", None)
        death_sound = self.get_sound("death")
        if death_sound and not self.silent and server is not None:
            server.broadcast_sound(
                death_sound, self.x, self.y, getattr(self, "z", 0)
            )
        self.spawn_death_particles()
        self.spawn_drops()
        return True

    def spawn_death_particles(self) -> None:
        spawn_particle = getattr(self.world, "spawn_particle", None)
        if not callable(spawn_particle):
            return
        from resources.server.particles import GENERIC

        spawn_particle(GENERIC(
            self.x + self.width * 0.5,
            self.y + self.height * 0.5,
            getattr(self, "z", 0),
            count=20,
            motion=(0.0, 0.025),
            data={
                "position_spread": [self.width * 0.65, self.height * 0.65],
                "motion_spread": [0.07, 0.05],
            },
        ))

    def spawn_drops(self) -> None:
        spawn_entity = getattr(self.world, "spawn_entity", None)
        if not callable(spawn_entity):
            return
        from resources.server.entities.item import Item

        for stack in self.get_drops():
            if stack is None or stack.is_empty() or stack.amount <= 0:
                continue
            spawn_entity(Item(
                self.x + self.width * 0.5,
                self.y + min(self.height * 0.5, 0.5),
                self.world,
                stack,
                getattr(self, "z", 0),
            ))

    def get_armor_attr(self):
        """
        返回实体的护甲值和盔甲韧性
        :return:
        """
        return 0, 0

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
        distance = math.sqrt(xd ** 2 + yd ** 2)
        return distance

    def get_drops(self):
        from resources.server.item_class import ItemStack

        result = []
        for stack in self.drops:
            if stack is None or getattr(stack, "amount", 0) <= 0:
                continue
            result.append(ItemStack(
                stack.material,
                int(stack.amount),
                dict(getattr(stack, "nbt", {})),
            ))
        return result
