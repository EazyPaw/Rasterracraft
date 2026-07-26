# Commented and arranged by ChatGPT

from __future__ import annotations

import math
import random

from resources.server.entities.collectible import CollectibleEntity
from resources.server.entity_registry import register_entity
from resources.server.experience import experience_orb_icon, split_experience


@register_entity(summonable=False)
class ExperienceOrb(CollectibleEntity):
    entity_id = "experience_orb"
    attackable = False
    scan_interval = 20
    follow_radius = 8.0
    merge_radius = 0.5

    def __init__(
        self,
        x: float,
        y: float,
        world,
        value: int,
        z: int = 0,
        *,
        count: int = 1,
    ):
        super().__init__(float(x), float(y), world)
        self.z = int(z)
        self.value = max(1, int(value))
        self.count = max(1, int(count))
        self.width = 0.5
        self.height = 0.5
        self.max_health = 5.0
        self.health = self.max_health
        self.gravity = 0.03
        self.drag_vertical = 0.98
        self.air_friction = 0.98
        self.damping = self.air_friction
        self.escape_speed = 0.1
        self.merge_group = random.randrange(40)
        self.following_player = None
        self.motion.x = random.uniform(-0.2, 0.2)
        self.motion.y = random.uniform(0.0, 0.4)

    @classmethod
    def create_from_save(cls, data: dict, world):
        payload = data.get("data", {})
        return cls(
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            world,
            max(1, int(payload.get("value", 1))),
            int(data.get("z", 0)),
            count=max(1, int(payload.get("count", 1))),
        )

    @classmethod
    def award(cls, world, x: float, y: float, z: int, amount: int):
        spawned = []
        for value in split_experience(amount):
            group = random.randrange(40)
            existing = cls._find_spawn_merge_target(world, x, y, z, value, group)
            if existing is not None:
                existing.count += 1
                existing.age = 0
                spawned.append(existing)
                continue
            orb = cls(x, y, world, value, z)
            orb.merge_group = group
            world.spawn_entity(orb)
            spawned.append(orb)
        return spawned

    @staticmethod
    def _find_spawn_merge_target(world, x, y, z, value, group):
        for entity in tuple(getattr(world, "entities", {}).values()):
            if not isinstance(entity, ExperienceOrb) or entity.removed:
                continue
            if (
                entity.z == int(z)
                and entity.value == int(value)
                and entity.merge_group == int(group)
                and abs(entity.x - float(x)) <= 0.5
                and abs(entity.y - float(y)) <= 0.5
            ):
                return entity
        return None

    @staticmethod
    def get_icon_for_value(value: int) -> int:
        return experience_orb_icon(value)

    def get_synced_data(self) -> dict:
        return {
            "experience_value": int(self.value),
            "orb_age": max(0, int(self.age)),
            "orb_count": max(1, int(self.count)),
        }

    def get_persistent_data(self) -> dict:
        return {
            **super().get_persistent_data(),
            "value": int(self.value),
            "count": max(1, int(self.count)),
            "merge_group": int(self.merge_group) % 40,
        }

    def read_persistent_data(self, data: dict) -> None:
        super().read_persistent_data(data)
        self.value = max(1, int(data.get("value", self.value)))
        self.count = max(1, int(data.get("count", self.count)))
        self.merge_group = int(data.get("merge_group", self.merge_group)) % 40

    def _scan_for_entities(self) -> None:
        players = [
            player
            for player in tuple(getattr(self.world.server, "players", ()))
            if self.is_valid_pickup_player(player)
            and self.calc_entity_distance(player) <= self.follow_radius
        ]
        self.following_player = (
            min(players, key=self.calc_entity_distance) if players else None
        )

        for other in tuple(getattr(self.world, "entities", {}).values()):
            if (
                not isinstance(other, ExperienceOrb)
                or other is self
                or other.removed
                or other.z != self.z
                or other.value != self.value
                or other.merge_group != self.merge_group
                or self.calc_entity_distance(other) > self.merge_radius
            ):
                continue
            self.count += other.count
            self.age = min(self.age, other.age)
            self.world.remove_entity(other)

    def _attract_to_player(self) -> None:
        player = self.following_player
        if player is None or not self.is_valid_pickup_player(player):
            self.following_player = None
            return
        target_x = player.x + player.width * 0.5
        target_y = player.y + player.height * 0.5
        center_x = self.x + self.width * 0.5
        center_y = self.y + self.height * 0.5
        dx, dy = target_x - center_x, target_y - center_y
        distance_sq = dx * dx + dy * dy
        if distance_sq <= 0.0 or distance_sq >= self.follow_radius**2:
            return
        distance = math.sqrt(distance_sq)
        strength = (1.0 - distance / self.follow_radius) ** 2 * 0.1
        self.motion.x += dx / distance * strength
        self.motion.y += dy / distance * strength

    def pick_up(self, player) -> bool:
        if (
            self.pickup_delay > 0
            or int(getattr(player, "take_xp_delay", 0)) > 0
            or not self.is_pickup_candidate(player)
        ):
            return False
        player.take_xp_delay = 2
        player.add_experience(self.value)
        server = getattr(self.world, "server", None)
        if server is not None:
            server.broadcast_sound("random.orb", self.x, self.y, self.z)
        self.count -= 1
        if self.count <= 0:
            self.world.remove_entity(self)
        return True

    def move_update(self):
        if not self.advance_collectible_lifetime():
            return
        pickup_delayed = self.tick_pickup_delay()
        self.escape_solid_block()
        if self.age % self.scan_interval == 1:
            self._scan_for_entities()
        self._attract_to_player()
        falling_speed = self.motion.y
        super().move_update()
        if self.on_ground and falling_speed < 0.0:
            self.motion.y = -falling_speed * 0.4
        if self.removed:
            return
        if not pickup_delayed:
            player = self.get_pickup_player()
            if player is not None:
                self.pick_up(player)

    def get_hurt_sound(self, damage_type, actual_damage: float) -> None:
        return None

    def get_drops(self):
        return []

    def die(self) -> None:
        remover = getattr(self.world, "remove_entity", None)
        if callable(remover):
            remover(self)
