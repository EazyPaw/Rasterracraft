# Commented and arranged by ChatGPT

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass
import math
import random
from typing import Literal

from src.server.damange_type import THROWN
from src.server.entity import Entity
from src.server.location import Vector


@dataclass(frozen=True, slots=True)
class ProjectileHitResult:
    """一次连续碰撞检测的结果，供具体弹射物处理命中行为。"""

    kind: Literal["block", "entity"]
    x: float
    y: float
    normal_x: float
    normal_y: float
    target: object
    block_position: tuple[int, int, int] | None = None


class Projectile(Entity, ABC):
    """服务端权威的弹射物基类。

    子类通常只需调整尺寸和物理常量，并覆写 ``on_hit_block`` 或
    ``on_hit_entity``。返回 ``True`` 表示命中后移除；箭矢一类需要插入方块的
    弹射物可以调用 ``embed_in_block`` 并返回 ``False``。
    """

    _texture_path = None
    blocks_block_placement = False
    attackable = False
    projectile_collidable = False
    persistent = False
    summonable = False

    default_speed = 1.5
    default_inaccuracy = 0.0
    air_drag = 0.99
    water_drag = 0.80
    max_lifetime = 1200
    min_world_y = -64.0
    impact_damage = 0.0
    impact_knockback = 0.0
    damage_type = THROWN

    def __init__(
        self,
        x: float,
        y: float,
        world,
        z: int = 0,
        *,
        owner=None,
    ):
        super().__init__(float(x), float(y), world)
        self.z = int(z)
        self.width = 0.25
        self.height = 0.25
        self.gravity = 0.03
        self.age = 0
        self.owner = owner
        owner_uuid = getattr(owner, "uuid", None)
        self.owner_uuid = str(owner_uuid) if owner_uuid is not None else None
        self._left_owner = owner is None
        self.in_ground = False
        self.embedded_block_position: tuple[int, int, int] | None = None

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width * 0.5, self.y + self.height * 0.5

    def set_owner(self, owner) -> None:
        self.owner = owner
        owner_uuid = getattr(owner, "uuid", None)
        self.owner_uuid = str(owner_uuid) if owner_uuid is not None else None
        self._left_owner = owner is None

    def get_owner(self):
        if self.owner is not None and not getattr(self.owner, "removed", False):
            return self.owner
        if not self.owner_uuid:
            return None

        owner = getattr(self.world, "entities", {}).get(self.owner_uuid)
        if owner is None:
            server = getattr(self.world, "server", None)
            for candidate in tuple(getattr(server, "players", ())):
                if str(getattr(candidate, "uuid", "")) == self.owner_uuid:
                    owner = candidate
                    break
        if owner is not None:
            self.owner = owner
        return owner

    def shoot(
        self,
        direction_x: float,
        direction_y: float,
        *,
        speed: float | None = None,
        inaccuracy: float | None = None,
        rng=None,
    ) -> Projectile:
        """按方向发射；``inaccuracy`` 是加入单位方向的高斯分量误差。"""

        direction_x = float(direction_x)
        direction_y = float(direction_y)
        length = math.hypot(direction_x, direction_y)
        if not math.isfinite(length) or length <= 1.0e-12:
            raise ValueError("Projectile direction must be a finite non-zero vector")

        direction_x /= length
        direction_y /= length
        spread = self.default_inaccuracy if inaccuracy is None else float(inaccuracy)
        if spread < 0.0 or not math.isfinite(spread):
            raise ValueError("Projectile inaccuracy must be a finite non-negative value")
        if spread:
            generator = rng if rng is not None else random
            direction_x += generator.gauss(0.0, spread)
            direction_y += generator.gauss(0.0, spread)
            noisy_length = math.hypot(direction_x, direction_y)
            if noisy_length > 1.0e-12:
                direction_x /= noisy_length
                direction_y /= noisy_length

        launch_speed = self.default_speed if speed is None else float(speed)
        if launch_speed < 0.0 or not math.isfinite(launch_speed):
            raise ValueError("Projectile speed must be a finite non-negative value")
        self.motion.x = direction_x * launch_speed
        self.motion.y = direction_y * launch_speed
        self.facing = 1 if self.motion.x >= 0.0 else 0
        self.look_angle = math.degrees(math.atan2(self.motion.y, self.motion.x))
        return self

    def shoot_from_rotation(
        self,
        facing: int,
        angle_degrees: float,
        *,
        speed: float | None = None,
        inaccuracy: float | None = None,
        rng=None,
    ) -> Projectile:
        angle = math.radians(float(angle_degrees))
        direction = 1.0 if int(facing) == 1 else -1.0
        return self.shoot(
            direction * math.cos(angle),
            math.sin(angle),
            speed=speed,
            inaccuracy=inaccuracy,
            rng=rng,
        )

    @classmethod
    def from_shooter(
        cls,
        shooter,
        *,
        speed: float | None = None,
        inaccuracy: float | None = None,
        angle_degrees: float | None = None,
        z: int | None = None,
        rng=None,
        **kwargs,
    ):
        """在发射者眼部前方创建已赋速的弹射物，但不自动加入世界。"""

        world = getattr(shooter, "world", None)
        if world is None:
            raise ValueError("Projectile shooter must belong to a world")
        facing = int(getattr(shooter, "facing", 1))
        angle = (
            float(getattr(shooter, "look_angle", 0.0))
            if angle_degrees is None
            else float(angle_degrees)
        )
        eye_height = float(
            getattr(shooter, "eye_height", getattr(shooter, "height", 1.0) * 0.85)
        )
        projectile = cls(
            float(shooter.x) + float(shooter.width) * 0.5,
            float(shooter.y) + eye_height,
            world,
            int(getattr(shooter, "z", 0) if z is None else z),
            owner=shooter,
            **kwargs,
        )
        projectile.x -= projectile.width * 0.5
        projectile.y -= projectile.height * 0.5
        projectile.shoot_from_rotation(
            facing,
            angle,
            speed=speed,
            inaccuracy=inaccuracy,
            rng=rng,
        )
        direction_length = max(
            math.hypot(projectile.motion.x, projectile.motion.y), 1.0e-12
        )
        projectile.x += projectile.motion.x / direction_length * 0.1
        projectile.y += projectile.motion.y / direction_length * 0.1
        return projectile

    def get_synced_data(self) -> dict:
        data = super().get_synced_data()
        data.update(
            {
                "projectile_age": int(self.age),
                "owner_uuid": self.owner_uuid,
                "in_ground": bool(self.in_ground),
            }
        )
        return data

    def get_persistent_data(self) -> dict:
        data = super().get_persistent_data()
        data.update(
            {
                "projectile_age": max(0, int(self.age)),
                "owner_uuid": self.owner_uuid,
                "in_ground": bool(self.in_ground),
                "embedded_block_position": (
                    list(self.embedded_block_position)
                    if self.embedded_block_position is not None
                    else None
                ),
            }
        )
        return data

    def read_persistent_data(self, data: dict) -> None:
        super().read_persistent_data(data)
        self.age = max(0, int(data.get("projectile_age", self.age)))
        owner_uuid = data.get("owner_uuid")
        self.owner_uuid = str(owner_uuid) if owner_uuid else None
        self.owner = None
        self._left_owner = self.owner_uuid is None
        self.in_ground = bool(data.get("in_ground", self.in_ground))
        position = data.get("embedded_block_position")
        if isinstance(position, (list, tuple)) and len(position) >= 3:
            self.embedded_block_position = (
                int(position[0]),
                int(position[1]),
                int(position[2]),
            )
        else:
            self.embedded_block_position = None
        if self.in_ground:
            self.stop_motion()

    @staticmethod
    def _segment_aabb_hit(
        origin_x: float,
        origin_y: float,
        delta_x: float,
        delta_y: float,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> tuple[float, float, float] | None:
        """返回线段进入 AABB 的比例和表面法线。"""

        epsilon = 1.0e-10
        strictly_inside = (
            min_x + epsilon < origin_x < max_x - epsilon
            and min_y + epsilon < origin_y < max_y - epsilon
        )
        if strictly_inside:
            return 0.0, 0.0, 0.0

        entry = -math.inf
        exit_ = math.inf
        normal_x = normal_y = 0.0
        for origin, delta, lower, upper, axis in (
            (origin_x, delta_x, min_x, max_x, "x"),
            (origin_y, delta_y, min_y, max_y, "y"),
        ):
            if abs(delta) <= epsilon:
                if origin < lower - epsilon or origin > upper + epsilon:
                    return None
                continue
            near = (lower - origin) / delta
            far = (upper - origin) / delta
            near_normal = -1.0 if delta > 0.0 else 1.0
            if near > far:
                near, far = far, near
            if near > entry:
                entry = near
                if axis == "x":
                    normal_x, normal_y = near_normal, 0.0
                else:
                    normal_x, normal_y = 0.0, near_normal
            exit_ = min(exit_, far)
            if entry - exit_ > epsilon:
                return None

        if entry < -epsilon or entry > 1.0 + epsilon or exit_ < -epsilon:
            return None
        return max(0.0, min(1.0, entry)), normal_x, normal_y

    def _hit_against_bounds(
        self,
        delta_x: float,
        delta_y: float,
        min_x: float,
        min_y: float,
        max_x: float,
        max_y: float,
    ) -> tuple[float, float, float] | None:
        return self._segment_aabb_hit(
            self.x,
            self.y,
            delta_x,
            delta_y,
            min_x - self.width,
            min_y - self.height,
            max_x,
            max_y,
        )

    def _find_block_hit(
        self, delta_x: float, delta_y: float
    ) -> tuple[float, ProjectileHitResult] | None:
        sweep_min_x = min(self.x, self.x + delta_x)
        sweep_max_x = max(self.x + self.width, self.x + self.width + delta_x)
        sweep_min_y = min(self.y, self.y + delta_y)
        sweep_max_y = max(self.y + self.height, self.y + self.height + delta_y)
        best = None
        z = int(getattr(self, "z", 0))

        for block_x in range(
            math.floor(sweep_min_x) - 1, math.floor(sweep_max_x) + 2
        ):
            for block_y in range(
                math.floor(sweep_min_y) - 1, math.floor(sweep_max_y) + 2
            ):
                for box in self._get_collision_boxes(block_x, block_y, z):
                    hit = self._hit_against_bounds(
                        delta_x,
                        delta_y,
                        box.min_x,
                        box.min_y,
                        box.max_x,
                        box.max_y,
                    )
                    if hit is None:
                        continue
                    fraction, normal_x, normal_y = hit
                    if best is not None and fraction >= best[0] - 1.0e-10:
                        continue
                    block = self._get_block_at(block_x, block_y, z)
                    best = (
                        fraction,
                        ProjectileHitResult(
                            "block",
                            self.x + delta_x * fraction,
                            self.y + delta_y * fraction,
                            normal_x,
                            normal_y,
                            block,
                            (block_x, block_y, z),
                        ),
                    )
        return best

    def _iter_entity_candidates(self):
        seen = {id(self)}
        for candidate in tuple(getattr(self.world, "entities", {}).values()):
            identity = id(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            yield candidate
        server = getattr(self.world, "server", None)
        for candidate in tuple(getattr(server, "players", ())):
            identity = id(candidate)
            if identity in seen:
                continue
            seen.add(identity)
            yield candidate

    @staticmethod
    def _aabb_overlaps_entity(
        x: float, y: float, width: float, height: float, target, padding: float = 0.0
    ) -> bool:
        return (
            x + width > float(target.x) - padding
            and x < float(target.x) + float(target.width) + padding
            and y + height > float(target.y) - padding
            and y < float(target.y) + float(target.height) + padding
        )

    def _update_left_owner(self) -> None:
        if self._left_owner:
            return
        owner = self.get_owner()
        if owner is None:
            self._left_owner = True
            return
        if int(getattr(owner, "z", 0)) != self.z or not self._aabb_overlaps_entity(
            self.x, self.y, self.width, self.height, owner, padding=0.1
        ):
            self._left_owner = True

    def can_hit_entity(self, target) -> bool:
        if target is self or getattr(target, "removed", False):
            return False
        if getattr(target, "world", None) is not self.world:
            return False
        if int(getattr(target, "z", 0)) != self.z:
            return False
        if not bool(getattr(target, "projectile_collidable", True)):
            return False
        if not bool(getattr(target, "attackable", True)):
            return False
        if float(getattr(target, "health", 0.0)) <= 0.0:
            return False
        if not callable(getattr(target, "apply_damage", None)):
            return False
        if not all(hasattr(target, name) for name in ("x", "y", "width", "height")):
            return False
        mode = getattr(getattr(target, "gamemode", None), "name_id", None)
        if mode == "spectator":
            return False
        owner = self.get_owner()
        return target is not owner or self._left_owner

    def _find_entity_hit(
        self, delta_x: float, delta_y: float
    ) -> tuple[float, ProjectileHitResult] | None:
        best = None
        for target in self._iter_entity_candidates():
            if not self.can_hit_entity(target):
                continue
            hit = self._hit_against_bounds(
                delta_x,
                delta_y,
                float(target.x),
                float(target.y),
                float(target.x) + float(target.width),
                float(target.y) + float(target.height),
            )
            if hit is None:
                continue
            fraction, normal_x, normal_y = hit
            if best is not None and fraction >= best[0] - 1.0e-10:
                continue
            best = (
                fraction,
                ProjectileHitResult(
                    "entity",
                    self.x + delta_x * fraction,
                    self.y + delta_y * fraction,
                    normal_x,
                    normal_y,
                    target,
                ),
            )
        return best

    def find_hit(self, delta_x: float, delta_y: float) -> ProjectileHitResult | None:
        """返回当前 tick 轨迹上最早的方块或实体命中。"""

        block_hit = self._find_block_hit(delta_x, delta_y)
        entity_hit = self._find_entity_hit(delta_x, delta_y)
        if block_hit is None:
            return entity_hit[1] if entity_hit is not None else None
        if entity_hit is None or block_hit[0] <= entity_hit[0] + 1.0e-10:
            return block_hit[1]
        return entity_hit[1]

    def get_impact_knockback(self, target) -> Vector | None:
        strength = max(0.0, float(self.impact_knockback))
        speed = math.hypot(self.motion.x, self.motion.y)
        if strength <= 0.0 or speed <= 1.0e-12:
            return None
        return Vector(
            self.motion.x / speed * strength,
            max(0.05, self.motion.y / speed * strength),
        )

    def on_hit_entity(self, result: ProjectileHitResult) -> bool:
        target = result.target
        owner = self.get_owner()
        callback = getattr(target, "on_projectile_hit", None)
        if callable(callback):
            callback(self, result)
        damage = max(0.0, float(self.impact_damage))
        if damage > 0.0:
            target.apply_damage(
                damage,
                self.damage_type,
                source=owner or self,
                knockback=self.get_impact_knockback(target),
            )
        return True

    def on_hit_block(self, result: ProjectileHitResult) -> bool:
        callback = getattr(result.target, "on_projectile_hit", None)
        if callable(callback):
            callback(self, result)
        return True

    def on_hit(self, result: ProjectileHitResult) -> None:
        should_discard = (
            self.on_hit_entity(result)
            if result.kind == "entity"
            else self.on_hit_block(result)
        )
        if should_discard and not self.removed:
            self.discard()

    def stop_motion(self) -> None:
        self.motion.x = 0.0
        self.motion.y = 0.0

    def embed_in_block(self, result: ProjectileHitResult) -> None:
        if result.kind != "block":
            raise ValueError("Only a block hit can embed a projectile")
        self.x = result.x + result.normal_x * 1.0e-4
        self.y = result.y + result.normal_y * 1.0e-4
        self.in_ground = True
        self.embedded_block_position = result.block_position
        self.stop_motion()

    def discard(self) -> None:
        remover = getattr(self.world, "remove_entity", None)
        if callable(remover):
            remover(self)
        else:
            self.removed = True

    def update(self) -> None:
        if self.removed:
            return
        self.age += 1
        if self.age >= self.max_lifetime or self.y < self.min_world_y:
            self.discard()
            return
        if self.in_ground:
            return

        self._update_left_owner()
        delta_x = float(self.motion.x)
        delta_y = float(self.motion.y)
        result = self.find_hit(delta_x, delta_y)
        if result is not None:
            self.x = result.x
            self.y = result.y
            self.on_hit(result)
            if self.removed:
                return
            if self.in_ground:
                return
        else:
            self.x += delta_x
            self.y += delta_y

        self._update_left_owner()
        self.in_fluid = bool(self._get_fluid_interaction()[0])
        self.in_water = self.in_fluid
        drag = self.water_drag if self.in_fluid else self.air_drag
        self.motion.x *= drag
        self.motion.y = self.motion.y * drag - self.gravity
        if abs(self.motion.x) < 1.0e-6:
            self.motion.x = 0.0
        if abs(self.motion.y) < 1.0e-6:
            self.motion.y = 0.0
        if self.motion.x or self.motion.y:
            self.facing = 1 if self.motion.x >= 0.0 else 0
            self.look_angle = math.degrees(math.atan2(self.motion.y, self.motion.x))
