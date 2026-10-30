"""Enderman behavior adapted from MCP 1.8.9 EntityEnderman to a 2-D plane."""

import math
import random

from src.server.attributes import AttributeModifier
from src.server.biome import get_precipitation_type
from src.server.block_collision import FULL_BLOCK, coerce_collision_shape
from src.server.damange_type import ARROW, DROWN, MOB_PROJECTILE, THROWN
from src.server.entity import Entity
from src.server.entity_AI import (
    EntityAI, HostileMobAI, FloatGoal, MeleeAttackGoal,
    RandomStrollGoal, LookAtPlayerGoal, RandomLookAroundGoal,
)
from src.server.entity_registry import register_entity
from src.server.item_class import ItemStack
from src.server.materials import get_material_by_id
from src.server.particles import PORTAL
from src.server.tags import DamageTag


class EndermanMeleeGoal(MeleeAttackGoal):
    def tick(self):
        target = self.ai.get_target()
        if target is not None and self.entity.is_stared_at_by(target):
            self.ai.look_control.look_at(target.x + target.width / 2,
                                         target.y + target.height * 0.85)
            return
        super().tick()


class EndermanAI(HostileMobAI):
    def __init__(self, entity):
        self.staring_player = None
        self.stare_ticks = 0
        self.teleport_ticks = 0
        super().__init__(entity)

    def register_goals(self):
        self.goal_selector.add(0, FloatGoal(self))
        self.goal_selector.add(2, EndermanMeleeGoal(self))
        self.goal_selector.add(7, RandomStrollGoal(self))
        self.goal_selector.add(8, LookAtPlayerGoal(self))
        self.goal_selector.add(8, RandomLookAroundGoal(self))

    def set_target(self, target):
        super().set_target(target)
        self.entity.screaming = target is not None
        self.entity.attributes.replace_source("enderman:attacking", (
            [("movement_speed", AttributeModifier("enderman:attacking", 0.15))]
            if target is not None else []
        ))

    def on_hurt(self, source):
        if self.can_target(source):
            self.set_target(source)

    def get_target(self):
        target = super().get_target()
        return target if target is not None else self.entity.world.entities.get(self.entity.target_uuid)

    def is_in_attack_reach(self, target):
        return (super().is_in_attack_reach(target)
                and self.entity.has_clear_view(
                    (self.entity.x + self.entity.width / 2, self.entity.y + 1.0),
                    (target.x + target.width / 2, target.y + target.height / 2)))

    def tick(self):
        if self.entity.no_ai:
            return
        if self.entity.screaming and self.get_target() is None and random.randrange(100) == 0:
            self.entity.screaming = False
        target = self.get_target()
        if target is None and self.entity.target_uuid is not None:
            self.set_target(None)
        if target is not None and not self.can_target(target, extra_range=8.0):
            self.set_target(None)
            target = None
        if target is None:
            players = getattr(self.entity.world.server, "players", ())
            candidates = [p for p in players if self.can_target(p)
                          and self.entity.is_stared_at_by(p)]
            player = min(candidates, key=self.distance_squared_to) if candidates else None
            if player is None or player is not self.staring_player:
                self.stare_ticks = 0
            self.staring_player = player
            if player is not None:
                self.stare_ticks += 1
                self.look_control.look_at(player.x + player.width / 2,
                                          player.y + player.height * 0.85)
                if self.stare_ticks >= 5:
                    self.set_target(player)
                    self.entity.play_ender_sound("mob.endermen.stare")
                    self.staring_player = None
                    self.stare_ticks = 0
            else:
                mites = [e for e in tuple(self.entity.world.entities.values())
                         if e.entity_id == "endermite" and e.player_spawned and self.can_target(e)]
                if mites:
                    self.set_target(min(mites, key=self.distance_squared_to))
        else:
            if self.entity.is_stared_at_by(target):
                if self.distance_squared_to(target) < 16.0:
                    self.entity.teleport_randomly()
                self.teleport_ticks = 0
            elif self.distance_squared_to(target) > 256.0:
                self.teleport_ticks += 1
                if self.teleport_ticks >= 30 and self.entity.teleport_towards(target):
                    self.teleport_ticks = 0
            else:
                self.teleport_ticks = 0
        EntityAI.tick(self)


@register_entity
class Enderman(Entity):
    entity_id = "enderman"
    translation_key = "entity.Enderman.name"
    experience_reward = 5
    eye_height = 2.55
    DAYLIGHT_CHECK_INTERVAL = 20
    DAYLIGHT_TELEPORT_COOLDOWN = 400
    sounds = {"ambient": "mob.endermen.idle", "hurt": "mob.endermen.hit",
              "death": "mob.endermen.death"}
    CARRIABLE_BLOCKS = frozenset({
        "grass", "grass_block", "dirt", "sand", "gravel", "yellow_flower",
        "red_flower", "dandelion", "poppy", "brown_mushroom", "red_mushroom",
        "tnt", "cactus", "clay", "pumpkin", "melon_block", "melon", "mycelium",
    })

    def __init__(self, x, y, world, z=0):
        super().__init__(float(x), float(y), world)
        self.z = int(z)
        self.width, self.height = 0.6, 2.9
        self.max_health = self.health = 40.0
        self.move_speed = 0.3
        self.attack_damage = 7.0
        self.follow_range = 64.0
        self.interact_range = 0.8
        self.max_step_height = 1.0
        self.screaming = False
        self.carried_block = None
        self.teleport_revision = 0
        self._ender_ticks = 0
        self._daylight_teleport_cooldown = 0
        # EntityEnderman#dropFewItems uses nextInt(2), i.e. 0 or 1 pearl.
        self.drops = ([ItemStack(get_material_by_id("ender_pearl"), 1)]
                      if random.randrange(2) else [])
        self.ai = EndermanAI(self)

    def play_ender_sound(self, sound, x=None, y=None):
        if not self.silent:
            self.world.server.broadcast_sound(
                sound, self.x if x is None else x, self.y if y is None else y,
                self.z, world=self.world,
            )

    def get_sound(self, event):
        if event == "ambient" and self.screaming:
            return "mob.endermen.scream"
        return super().get_sound(event)

    def get_synced_data(self):
        return {"screaming": self.screaming, "carried_block": self.carried_block,
                "teleport_revision": self.teleport_revision}

    def get_persistent_data(self):
        return {"carried_block": self.carried_block}

    def read_persistent_data(self, data):
        block = data.get("carried_block")
        self.carried_block = (dict(block) if isinstance(block, dict)
                              and block.get("id") in self.CARRIABLE_BLOCKS else None)

    def has_clear_view(self, start, end):
        # Test actual collision boxes, including slabs, along the sight ray.
        from src.server.entities.projectile import Projectile

        dx, dy = end[0] - start[0], end[1] - start[1]
        for x in range(math.floor(min(start[0], end[0])),
                       math.floor(max(start[0], end[0])) + 1):
            for y in range(math.floor(min(start[1], end[1])),
                           math.floor(max(start[1], end[1])) + 1):
                for box in self._get_collision_boxes(x, y, self.z):
                    hit = Projectile._segment_aabb_hit(
                        *start, dx, dy, box.min_x, box.min_y, box.max_x, box.max_y)
                    if hit is not None and 1e-6 < hit[0] < 1.0 - 1e-6:
                        return False
        return True

    def is_stared_at_by(self, player):
        if getattr(player, "entity_id", "") != "player" or int(getattr(player, "z", 0)) != self.z:
            return False
        helmet = getattr(player, "equipment", {}).get("head")
        if helmet is not None and getattr(helmet.material, "name_id", "") == "pumpkin":
            return False
        start = (player.x + player.width / 2,
                 player.y + float(getattr(player, "eye_height", player.height * 0.85)))
        end = (self.x + self.width / 2, self.y + self.height / 2)
        dx, dy = end[0] - start[0], end[1] - start[1]
        distance = math.hypot(dx, dy)
        if distance < 1e-6:
            return False
        angle = math.radians(float(player.look_angle))
        direction = 1 if int(player.facing) == 1 else -1
        dot = direction * (math.cos(angle) * dx + math.sin(angle) * dy) / distance
        return dot > 1.0 - 0.025 / distance and self.has_clear_view(start, end)

    def _teleport_collision_boxes(self, x, y):
        # Unlike ordinary movement helpers, teleport validation must never turn
        # a failed block lookup into an empty collision shape.
        block = self.world.get_block(x, y, self.z)
        shape = coerce_collision_shape(block.get_collision_box())
        return block, tuple(box.translated(x, y) for box in shape)

    def _find_teleport_landing(self, x, y):
        if (not math.isfinite(x) or not math.isfinite(y)
                or self.z not in (0, 1) or y < 1
                or y >= self.world.attribute.MAX_BUILD_HEIGHT):
            return None
        left, right = math.floor(x), math.floor(x + self.width - 1e-9)
        # Include neighboring cells: fences and other shapes can extend beyond
        # their owning block, including upward into the destination hitbox.
        if not all(self.world.is_position_loaded(bx, 0, self.z)
                   for bx in range(left - 1, right + 2)):
            return None
        landing = None
        for by in range(math.floor(y), -1, -1):
            surfaces = []
            for bx in range(left - 1, right + 2):
                block, boxes = self._teleport_collision_boxes(bx, by)
                if getattr(block, "is_fluid", False) or block.block_id in {"fire", "cactus"}:
                    continue
                surfaces.extend(box.max_y for box in boxes
                                if box.min_x < x + self.width - 1e-9
                                and box.max_x > x + 1e-9 and box.max_y <= y + 1e-9)
            if surfaces:
                landing = max(surfaces)
                break
        if landing is None or landing + self.height >= self.world.attribute.MAX_BUILD_HEIGHT:
            return None
        for bx in range(left - 1, right + 2):
            for by in range(max(0, math.floor(landing) - 2),
                            min(self.world.attribute.MAX_BUILD_HEIGHT, math.ceil(landing + self.height) + 1)):
                block, boxes = self._teleport_collision_boxes(bx, by)
                if any(box.overlaps(x, landing, x + self.width, landing + self.height)
                       for box in boxes):
                    return None
                if (left <= bx <= right and by + 1 > landing
                        and by < landing + self.height
                        and (getattr(block, "is_fluid", False)
                             or block.block_id in {"fire", "cactus"})):
                    return None
        occupants = tuple(self.world.entities.values()) + tuple(self.world.server.players)
        if any(other is not self and other.world is self.world
               and int(getattr(other, "z", 0)) == self.z
               and not getattr(other, "removed", False)
               and getattr(other, "blocks_block_placement", True)
               and other.x < x + self.width and other.x + other.width > x
               and other.y < landing + self.height and other.y + other.height > landing
               for other in occupants):
            return None
        # A missing chunk is unknown terrain, never an air-filled destination.
        if not all(self.world.is_position_loaded(bx, math.floor(landing), self.z)
                   for bx in range(left - 1, right + 2)):
            return None
        return landing

    def try_teleport(self, x, y):
        try:
            landing = self._find_teleport_landing(x, y)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            # A temporarily unavailable block/shape cannot certify a safe landing.
            return False
        if landing is None:
            return False
        old_x, old_y = self.x, self.y
        self.teleport_to(float(x), float(landing))
        self.motion.x = self.motion.y = 0.0
        self.on_ground = True
        self.in_fluid = self.in_water = self.in_lava = False
        self.fluid_type = None
        self._active_fluid_block = None
        self.teleport_revision += 1
        self.world.spawn_particle(PORTAL(
            old_x + self.width / 2, old_y, self.z, count=128,
            data={"kind": "teleport", "trail_end": (self.x + self.width / 2, self.y)},
        ))
        for px, py in ((old_x, old_y), (self.x, self.y)):
            self.play_ender_sound("mob.endermen.portal", px, py)
        return True

    def teleport_randomly(self):
        return self.try_teleport(self.x + random.uniform(-32, 32),
                                 self.y + random.randrange(64) - 32)

    def teleport_towards(self, target):
        dx = self.x - target.x
        dy = self.y + self.height / 2 - (target.y + target.height * 0.85)
        length = max(1e-6, math.hypot(dx, dy))
        return self.try_teleport(self.x + random.uniform(-4, 4) - dx / length * 16,
                                 self.y + random.randrange(16) - 8 - dy / length * 16)

    def evade_projectile(self):
        self.screaming = True
        for _ in range(64):
            if self.teleport_randomly():
                break

    def on_projectile_hit(self, projectile, result):
        self.evade_projectile()
        return True

    def apply_damage(self, amount, damage_type=None, source=None, knockback=None,
                     *, allow_zero_damage=False):
        if damage_type in {ARROW, THROWN, MOB_PROJECTILE} and self.can_take_damage(damage_type):
            self.evade_projectile()
            return 0.0
        from src.server.damange_type import GENERIC

        damage_type = damage_type or GENERIC
        damage = super().apply_damage(amount, damage_type, source, knockback,
                                      allow_zero_damage=allow_zero_damage)
        if damage > 0 and damage_type.has_tag(DamageTag.BYPASSES_ARMOR) and random.randrange(10) != 0:
            self.teleport_randomly()
        return damage

    def exposed_to_sky(self):
        if not self.world.attribute.HAS_SKY:
            return False
        x = math.floor(self.x + self.width / 2)
        return not any(self._is_block_solid(x, y, self.z)
                       for y in range(math.ceil(self.y + self.height),
                                      self.world.attribute.MAX_BUILD_HEIGHT))

    def update_ai(self):
        if self.no_ai:
            return
        self._ender_ticks += 1
        if self._daylight_teleport_cooldown > 0:
            self._daylight_teleport_cooldown -= 1
        if not self.world.is_position_loaded(math.floor(self.x), math.floor(self.y), self.z):
            return
        rainy = (getattr(getattr(self.world, "weather", None), "value", "clear") == "rain"
                 and self.exposed_to_sky()
                 and get_precipitation_type(self.world.get_biome(
                     math.floor(self.x), math.floor(self.y)), self.y) == "rain")
        if self.in_water or rainy:
            self.apply_damage(1.0, DROWN)
            if self.health <= 0:
                return
        if (self._daylight_teleport_cooldown == 0
                and self._ender_ticks % self.DAYLIGHT_CHECK_INTERVAL == 0
                and self.world.world_time % 24000 < 12000
                and self.exposed_to_sky()
                and self.world.get_sky_light(math.floor(self.x), math.floor(self.y)) > 7
                and random.random() < 0.04):
            self._daylight_teleport_cooldown = self.DAYLIGHT_TELEPORT_COOLDOWN
            self.ai.set_target(None)
            self.teleport_randomly()
        self.ai.tick()
        self.tick_carried_block()
        self.world.spawn_particle(PORTAL(
            self.x + self.width / 2, self.y, self.z, count=2,
            data={"kind": "ambient"},
        ))

    def tick_carried_block(self):
        if not getattr(self.world, "mob_griefing", True):
            return
        carrying = self.carried_block is not None
        if random.randrange(2000 if carrying else 20) != 0:
            return
        radius, height = (1, 2) if carrying else (2, 3)
        x = math.floor(self.x + random.uniform(-radius, radius))
        y = math.floor(self.y + random.random() * height)
        if not self.world.is_position_loaded(x, y, self.z):
            return
        block = self.world.get_block(x, y, self.z)
        from src.server.blocks import AIR, get_block_by_id

        if not carrying:
            if block.block_id in self.CARRIABLE_BLOCKS:
                self.carried_block = block.to_dict()
                self.world.set_block(AIR(), x, y, self.z)
            return
        support = self.world.get_block(x, y - 1, self.z)
        if block.block_id != "air" or support.get_collision_box() != FULL_BLOCK:
            return
        # Placing a block must not trap a player or another mob.
        occupants = tuple(self.world.entities.values()) + tuple(self.world.server.players)
        if any(e.world is self.world and int(getattr(e, "z", 0)) == self.z
               and not getattr(e, "removed", False)
               and e.x < x + 1 and e.x + e.width > x
               and e.y < y + 1 and e.y + e.height > y for e in occupants):
            return
        carried = get_block_by_id(self.carried_block["id"])
        carried.write_nbt(self.carried_block.get("nbt", {}))
        from src.server.location import Location

        can_place = getattr(carried, "can_place_at", None)
        if callable(can_place) and not can_place(Location(self.world, x, y, self.z)):
            return
        self.world.set_block(carried, x, y, self.z)
        self.carried_block = None
