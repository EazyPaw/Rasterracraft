# Commented and arranged by ChatGPT

from __future__ import annotations

import math
import random
import time

import pygame

from src.client.entity_skeleton import BodyPart, EntitySkeleton, Pose
from src.server.entity import Entity
from src.server.item_class import ItemStack
from src.server.particles import HEART
from src.server.utils import client_method


class Animal(Entity):
    tempt_items: frozenset[str] = frozenset()
    panic_speed_modifier = 1.25
    tempt_speed_modifier = 1.1
    follow_parent_speed_modifier = 1.1
    breeding_cooldown_ticks = 6000
    baby_growth_ticks = 24000

    def __init__(self, x: float, y: float, world, z: int = 0):
        super().__init__(float(x), float(y), world)
        self.z = int(z)
        self.persistence_required = True
        self.age_ticks = 0
        self.love_ticks = 0
        self.love_cause_uuid: str | None = None
        self._adult_width = self.width
        self._adult_height = self.height

    @property
    def is_baby(self) -> bool:
        return self.age_ticks < 0

    def finish_animal_init(self, ai_type) -> None:
        self._adult_width = float(self.width)
        self._adult_height = float(self.height)
        self._refresh_age_dimensions()
        self.ai = ai_type(self)

    def _refresh_age_dimensions(self) -> None:
        scale = 0.5 if self.is_baby else 1.0
        old_width = max(0.0, float(getattr(self, "width", self._adult_width)))
        center_x = self.x + old_width * 0.5
        self.width = self._adult_width * scale
        self.height = self._adult_height * scale
        self.x = center_x - self.width * 0.5

    def set_age(self, ticks: int) -> None:
        was_baby = self.is_baby
        self.age_ticks = int(ticks)
        if was_baby != self.is_baby:
            self._refresh_age_dimensions()

    def update(self) -> None:
        if self.age_ticks < 0:
            self.set_age(self.age_ticks + 1)
        elif self.age_ticks > 0:
            self.age_ticks -= 1
        if self.love_ticks > 0:
            self.love_ticks -= 1
            if self.love_ticks % 10 == 0:
                self.spawn_heart_particles(1)
        super().update()

    def update_ai(self) -> None:
        self.ai.tick()

    def get_synced_data(self) -> dict:
        return {
            "is_baby": self.is_baby,
            "age_scale": 0.5 if self.is_baby else 1.0,
        }

    def get_persistent_data(self) -> dict:
        return {
            "age_ticks": int(self.age_ticks),
            "love_ticks": int(self.love_ticks),
            "love_cause_uuid": self.love_cause_uuid,
        }

    def read_persistent_data(self, data: dict) -> None:
        self.set_age(int(data.get("age_ticks", 0)))
        self.love_ticks = max(0, int(data.get("love_ticks", 0)))
        cause = data.get("love_cause_uuid")
        self.love_cause_uuid = str(cause) if cause else None

    def spawn_heart_particles(self, count: int = 7) -> None:
        spawner = getattr(self.world, "spawn_particle", None)
        if callable(spawner):
            spawner(
                HEART(
                    self.x + self.width * 0.5,
                    self.y + self.height * 0.7,
                    self.z,
                    count=max(1, int(count)),
                    motion=(0.0, 0.025),
                    data={"position_spread": [self.width * 0.8, self.height * 0.35]},
                )
            )

    @staticmethod
    def _player_is_creative(player) -> bool:
        return (
            getattr(getattr(player, "gamemode", None), "name_id", "survival")
            == "creative"
        )

    def _consume_held_item(self, player, held_stack) -> bool:
        if self._player_is_creative(player):
            return True
        remover = getattr(player, "remove_item_stack", None)
        return bool(callable(remover) and remover(held_stack, 1))

    def interact(self, player, held_stack) -> bool:
        if held_stack is None or held_stack.is_empty():
            return False
        item_id = str(held_stack.material.name_id)
        if item_id not in self.tempt_items:
            return False
        if self.is_baby:
            if not self._consume_held_item(player, held_stack):
                return False
            reduction = max(1, math.ceil(abs(self.age_ticks) * 0.1))
            self.set_age(min(0, self.age_ticks + reduction))
            self.spawn_heart_particles(3)
            return True
        if self.age_ticks != 0 or self.love_ticks > 0:
            return False
        if not self._consume_held_item(player, held_stack):
            return False
        self.love_ticks = 600
        self.love_cause_uuid = str(getattr(player, "uuid", "")) or None
        self.spawn_heart_particles()
        return True

    def find_breeding_mate(self):
        candidates = []
        with self.world._entities_lock:
            entities = tuple(self.world.entities.values())
        for candidate in entities:
            if type(candidate) is not type(self) or candidate is self:
                continue
            if candidate.is_baby or candidate.love_ticks <= 0 or candidate.removed:
                continue
            if candidate.z != self.z:
                continue
            dx = candidate.x - self.x
            dy = candidate.y - self.y
            if dx * dx + dy * dy <= 8.0 * 8.0:
                candidates.append(candidate)
        return min(candidates, key=self.calc_entity_distance) if candidates else None

    def find_nearest_adult(self, radius: float):
        with self.world._entities_lock:
            entities = tuple(self.world.entities.values())
        candidates = [
            candidate
            for candidate in entities
            if type(candidate) is type(self)
            and not candidate.is_baby
            and not candidate.removed
            and candidate.z == self.z
            and self.calc_entity_distance(candidate) <= radius
        ]
        return min(candidates, key=self.calc_entity_distance) if candidates else None

    def try_breed_with(self, mate) -> bool:
        if mate is None or type(mate) is not type(self):
            return False
        if self.is_baby or mate.is_baby or self.love_ticks <= 0 or mate.love_ticks <= 0:
            return False

        if str(self.uuid) > str(mate.uuid):
            return False
        child = self.create_child((self.x + mate.x) * 0.5, min(self.y, mate.y), self.z)
        if child is None:
            return False
        child.set_age(-self.baby_growth_ticks)
        self.world.spawn_entity(child)
        spawn_experience = getattr(self.world, "spawn_experience", None)
        if callable(spawn_experience):
            spawn_experience(
                child.x + child.width * 0.5,
                child.y + child.height * 0.5,
                child.z,
                random.randint(1, 7),
            )
        self.set_age(self.breeding_cooldown_ticks)
        mate.set_age(mate.breeding_cooldown_ticks)
        self.love_ticks = mate.love_ticks = 0
        self.love_cause_uuid = mate.love_cause_uuid = None
        self.spawn_heart_particles()
        mate.spawn_heart_particles()
        return True

    def create_child(self, x: float, y: float, z: int):
        return type(self)(x, y, self.world, z)

    def was_burning_when_killed(self) -> bool:
        damage_type = self.last_damage_type
        return bool(
            self.fire_ticks > 0 or getattr(damage_type, "effects", None) == "burning"
        )

    def get_drops(self):
        return [] if self.is_baby else super().get_drops()

    def get_experience_reward(self) -> int:
        return 0 if self.is_baby else random.randint(1, 3)


def crop_x_side(
    texture: pygame.Surface,
    uv: tuple[int, int],
    size: tuple[int, int, int],
    *,
    positive: bool = False,
) -> pygame.Surface:
    u, v = uv
    dx, dy, dz = size
    x = u + dz + dx if positive else u
    return texture.subsurface((x, v + dz, dz, dy)).copy()


def crop_rotated_body(
    texture: pygame.Surface,
    uv: tuple[int, int],
    size: tuple[int, int, int],
) -> pygame.Surface:
    return pygame.transform.rotate(crop_x_side(texture, uv, size), -90)


class AnimalSkeleton(EntitySkeleton):
    @client_method
    def __init__(self, entity, texture_key: str, *, client=None):
        super().__init__(client, texture_key, entity)
        self.walk_time = 0.0
        self._last_update_time = time.perf_counter()
        self._last_x = entity.x
        self._age_scale = float(getattr(entity, "age_scale", 1.0))
        self.facing = int(getattr(entity, "facing", self.RIGHT))
        self.model_width = float(getattr(entity, "width", 1.0))

    def pose_anchor(
        self, name: str, anchor: tuple[float, float], flip: bool
    ) -> tuple[float, float]:
        if not flip:
            return anchor

        return (self.model_width - anchor[0], anchor[1])

    def _update_clock(self) -> float:
        now = time.perf_counter()
        dt = min(max(now - self._last_update_time, 0.0), 0.05)
        self._last_update_time = now
        dx = self.entity.x - self._last_x
        self._last_x = self.entity.x
        speed = max(
            abs(getattr(self.entity.motion, "x", 0.0)), abs(dx) / max(dt, 0.001)
        )
        self.walk_time += dt * (9.0 if speed > 0.015 else 2.0)
        return speed

    def update(self):
        packet_facing = int(getattr(self.entity, "facing", self.facing))
        if packet_facing in (self.LEFT, self.RIGHT):
            self.facing = packet_facing
        speed = self._update_clock()
        age_scale = float(getattr(self.entity, "age_scale", 1.0))
        if age_scale != self._age_scale:
            self._age_scale = age_scale
            self.last_size = None
        self.apply_pose(speed)
        super().update()

    def apply_pose(self, speed: float) -> None:
        raise NotImplementedError


class QuadrupedSkeleton(AnimalSkeleton):
    def configure_quadruped(
        self,
        *,
        body_uv: tuple[int, int],
        body_size: tuple[int, int, int],
        head_uv: tuple[int, int],
        head_size: tuple[int, int, int],
        leg_uv: tuple[int, int],
        leg_size: tuple[int, int, int],
        body_anchor: tuple[float, float],
        head_anchor: tuple[float, float],
        rear_leg_anchor: tuple[float, float],
        front_leg_anchor: tuple[float, float],
    ) -> None:
        body = crop_rotated_body(self.texture, body_uv, body_size)
        head = crop_x_side(self.texture, head_uv, head_size)
        leg = crop_x_side(self.texture, leg_uv, leg_size)

        near_rear = (rear_leg_anchor[0] + 0.03, rear_leg_anchor[1] - 0.04)
        near_front = (front_leg_anchor[0] - 0.03, front_leg_anchor[1] - 0.04)
        self._base_anchors = {
            "body": body_anchor,
            "head": head_anchor,
            "far_back_leg": rear_leg_anchor,
            "far_front_leg": front_leg_anchor,
            "near_back_leg": near_rear,
            "near_front_leg": near_front,
        }
        leg_pivot = (leg.get_width() / 2, 0)
        head_pivot = (head.get_width() / 2, head.get_height() / 2)
        self.body = {
            "far_back_leg": BodyPart(
                "far_back_leg", leg, rear_leg_anchor, leg_pivot, layer=0
            ),
            "far_front_leg": BodyPart(
                "far_front_leg", leg, front_leg_anchor, leg_pivot, layer=0
            ),
            "body": BodyPart("body", body, body_anchor, (0, 0), layer=1),
            "near_back_leg": BodyPart(
                "near_back_leg", leg, near_rear, leg_pivot, layer=2
            ),
            "near_front_leg": BodyPart(
                "near_front_leg", leg, near_front, leg_pivot, layer=2
            ),
            "head": BodyPart("head", head, head_anchor, head_pivot, layer=3),
        }

    def apply_pose(self, speed: float) -> None:
        moving = speed > 0.015
        amplitude = min(28.0, 12.0 + speed * 32.0) if moving else 0.0
        swing = math.sin(self.walk_time) * amplitude
        flip = self.facing == self.LEFT
        self.body["body"].set_pose(
            Pose(
                self.pose_anchor("body", self._base_anchors["body"], flip),
                (0, 0),
                0,
                True,
                flip,
            )
        )

        self.body["far_back_leg"].set_pose(
            Pose(
                self.pose_anchor(
                    "far_back_leg", self._base_anchors["far_back_leg"], flip
                ),
                self.body["far_back_leg"].target_pivot,
                swing,
                True,
                flip,
            )
        )
        self.body["far_front_leg"].set_pose(
            Pose(
                self.pose_anchor(
                    "far_front_leg", self._base_anchors["far_front_leg"], flip
                ),
                self.body["far_front_leg"].target_pivot,
                -swing,
                True,
                flip,
            )
        )

        self.body["near_back_leg"].set_pose(
            Pose(
                self.pose_anchor(
                    "near_back_leg", self._base_anchors["near_back_leg"], flip
                ),
                self.body["near_back_leg"].target_pivot,
                -swing,
                True,
                flip,
            )
        )
        self.body["near_front_leg"].set_pose(
            Pose(
                self.pose_anchor(
                    "near_front_leg", self._base_anchors["near_front_leg"], flip
                ),
                self.body["near_front_leg"].target_pivot,
                swing,
                True,
                flip,
            )
        )
        head_angle = float(getattr(self.entity, "look_angle", 0.0)) * 0.35
        head_anchor = self.get_head_anchor()
        self.body["head"].set_pose(
            Pose(
                self.pose_anchor("head", head_anchor, flip),
                self.body["head"].target_pivot,
                head_angle,
                True,
                flip,
            )
        )
        self.apply_extra_pose(flip, swing)

    def get_head_anchor(self) -> tuple[float, float]:
        return self._base_anchors["head"]

    def apply_extra_pose(self, flip: bool, swing: float) -> None:
        pass

    def draw(self):
        old_size = self.size
        self.size = old_size * self._age_scale
        try:
            super().draw()
        finally:
            self.size = old_size
