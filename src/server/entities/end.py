"""Authoritative 1.8 dragon steering, multipart combat and 200-tick death."""
import math
import random

from src.server.entity import Entity
from src.server.entity_registry import register_entity
from src.server.damange_type import EXPLOSION, PLAYER_EXPLOSION, GENERIC, MOB_ATTACK, THORNS
from src.server.location import Location, Vector
from src.server.dragon_geometry import dragon_parts, wrap_degrees


@register_entity(aliases=("end_crystal",))
class EnderCrystal(Entity):
    entity_id = "ender_crystal"
    translation_key = "entity.EnderCrystal.name"
    fire_immune = True

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = z
        self.width = self.height = 2.0
        self.no_physics = True
        self.max_health = self.health = 5
        self.inner_rotation = random.randrange(100000)

    def update(self):
        self.inner_rotation += 1
        if self.world.attribute.ENVIRONMENT == 1:
            from src.server.blocks import FIRE
            x, y = math.floor(self.x + self.width / 2), math.floor(self.y)
            if self.world.get_block(x, y, 1).block_id == "air":
                self.world.set_block(FIRE(), x, y, 1, block_update=False)

    def apply_damage(self, amount, damage_type=GENERIC, source=None, knockback=None, **kwargs):
        # EntityEnderCrystal breaks on any accepted attack, rather than taking
        # normal living-entity armor, hurt cooldown or knockback damage.
        if self.removed or self.health <= 0 or not self.can_take_damage(damage_type):
            return 0.0
        old_health = self.health
        self.health = 0
        self.world.remove_entity(self)
        fight = getattr(self.world, "end_fight", None)
        if fight is not None:
            fight.crystal_destroyed(self)
        self.world.spawn_explosion(Location(self.world, self.x + 1, self.y + 1, self.z),
                                   power=6.0, break_block=True, catch_fire=False, source=self)
        return old_health

    def to_entity_data(self):
        return {**super().to_entity_data(), "inner_rotation": self.inner_rotation}

    def get_persistent_data(self):
        return {"inner_rotation": self.inner_rotation}

    def read_persistent_data(self, data):
        self.inner_rotation = int(data.get("inner_rotation", self.inner_rotation))


@register_entity
class EnderDragon(Entity):
    entity_id = "ender_dragon"
    translation_key = "entity.EnderDragon.name"
    fire_immune = True
    blocks_block_placement = False
    persists_while_dying = True
    tracking_range = 160
    sounds = {"ambient": "mob.enderdragon.growl", "hurt": "mob.enderdragon.hit"}

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = z
        self.width, self.height = 16.0, 8.0
        self.max_health = self.health = 200
        self.no_physics = True
        self.persistence_required = True
        self.age = 0
        self.healing_crystal_uuid = None
        self.dragon_yaw = 90.0
        self.dragon_turn = 0.0
        self.dragon_anim = 0.0
        self.dragon_history = [(self.dragon_yaw, y + 4)] * 64
        # Continuous flight depth affects steering/orientation only. Entity.z
        # remains a valid 2.5D layer, and combat uses projected body parts.
        self.flight_depth = 0.0
        self.depth_motion = 0.0
        self.flight_target = (40.0, 100.0, 25.0)
        self.flight_player_uuid = None
        self.force_new_target = False
        self.slowed = False
        self.dying = False
        self.death_ticks = 0
        self._target_age = 0
        self._growl_ticks = random.randint(100, 200)

    def _sound(self, key, *, global_=False):
        if not self.silent:
            options = {"pitch": random.uniform(.8, 1.1)} if key == "mob.enderdragon.wings" else {}
            self.world.server.broadcast_sound(key, self.x + 8, self.y + 4, self.z,
                                              volume=5, positional=not global_, world=self.world, **options)

    def get_damage_parts(self):
        return dragon_parts(self)

    def _players(self):
        return [p for p in tuple(self.world.server.players)
                if p.world is self.world and p.health > 0 and not p.removed
                and getattr(p.gamemode, "name_id", "survival") != "spectator"]

    def _new_target(self):
        players = self._players()
        self.flight_player_uuid = None
        if players and random.randrange(2) == 0:
            self.flight_player_uuid = str(random.choice(players).uuid)
        else:
            for _ in range(16):
                target = (random.uniform(-60, 60), random.uniform(70, 120), random.uniform(-40, 40))
                if (target[0] - self.x - 8) ** 2 + (target[1] - self.y - 4) ** 2 > 100:
                    self.flight_target = target
                    break
        self.force_new_target = False
        self._target_age = 0

    def _fly(self):
        self._target_age += 1
        cx, cy = self.x + 8, self.y + 4
        tx, ty, tz = self.flight_target
        target = next((p for p in self._players() if str(p.uuid) == self.flight_player_uuid), None)
        if target is not None:
            tx, tz = target.x + target.width / 2, 0.0
            distance = math.hypot(tx - cx, tz - self.flight_depth)
            ty = target.y + min(10, .4 + distance / 80 - 1)
        elif self.flight_player_uuid is not None:
            self.force_new_target = True
        else:
            tx += random.gauss(0, 2)
            tz += random.gauss(0, 2)
        self.flight_target = tx, ty, tz
        dx, dy, dz = tx - cx, ty - cy, tz - self.flight_depth
        distance_sq = dx * dx + dy * dy + dz * dz
        # The arena is a single island; also discard unreachable stale targets
        # so a long chase cannot leave the finite fight permanently.
        if (self.force_new_target or distance_sq < 100 or distance_sq > 22500
                or self._target_age > 300 or abs(cx) > 110):
            self._new_target()
        horizontal = max(.001, math.hypot(dx, dz))
        self.motion.y += max(-.6, min(.6, dy / horizontal)) * .1
        desired = 180 - math.degrees(math.atan2(dx, dz))
        difference = max(-50, min(50, wrap_degrees(desired - self.dragon_yaw)))
        speed = math.hypot(self.motion.x, self.depth_motion)
        factor = speed + 1
        self.dragon_turn = self.dragon_turn * .8 + difference * (.7 / min(40, factor) / factor)
        self.dragon_yaw = wrap_degrees(self.dragon_yaw + self.dragon_turn * .1)
        angle = math.radians(self.dragon_yaw)
        forward = (math.sin(angle), self.motion.y, -math.cos(angle))
        length = max(.001, math.sqrt(sum(v * v for v in forward)))
        dot = sum(a * b for a, b in zip(forward, (dx, dy, dz))) / length / max(.001, math.sqrt(distance_sq))
        alignment = max(0, (dot + .5) / 1.5)
        acceleration = .06 * (alignment * 2 / (factor + 1) + (1 - 2 / (factor + 1)))
        self.motion.x += math.sin(angle) * acceleration
        self.depth_motion -= math.cos(angle) * acceleration
        slow = .8 if self.slowed else 1.0
        self.x += self.motion.x * slow
        self.y += self.motion.y * slow
        self.flight_depth += self.depth_motion * slow
        motion_len = max(.001, math.sqrt(self.motion.x ** 2 + self.motion.y ** 2 + self.depth_motion ** 2))
        aligned_motion = (self.motion.x * forward[0] + self.motion.y * forward[1] + self.depth_motion * forward[2]) / motion_len / length
        damping = .8 + .15 * (aligned_motion + 1) / 2
        self.motion.x *= damping
        self.depth_motion *= damping
        self.motion.y *= .91
        self.facing = int(math.sin(angle) >= 0)

    def _contact(self):
        parts = self.get_damage_parts()
        if self.hurt_time:
            return
        candidates = (*tuple(self.world.entities.values()), *tuple(self.world.server.players))
        for entity in candidates:
            if (entity is self or entity.world is not self.world or entity.removed or entity.health <= 0
                    or getattr(entity, "entity_id", "") in {"ender_crystal", "ender_dragon", "item", "experience_orb"}
                    or not getattr(entity, "receives_damage", True)
                    or getattr(getattr(entity, "gamemode", None), "name_id", "survival") in {"creative", "spectator"}):
                continue
            def overlaps(part, padding):
                return (entity.x + entity.width > part.x - padding and entity.x < part.x + part.width + padding
                        and entity.y + entity.height > part.y - padding and entity.y < part.y + part.height + padding)
            if overlaps(parts[0], 1):
                entity.apply_damage(10, MOB_ATTACK, source=self)
            if any(overlaps(part, 2) for part in parts[-2:]):
                delta = entity.x + entity.width / 2 - self.x - 8
                # The original inverse-distance impulse is bounded near zero
                # in this projection so crossing the center cannot launch NaNs.
                push = max(-2, min(2, 4 * delta / max(1, delta * delta)))
                if not push:
                    push = 1 if self.facing else -1
                entity.motion.x += push
                entity.motion.y += .2
                sync = getattr(entity, "sync_velocity", None)
                if callable(sync):
                    sync()

    def _break_terrain(self):
        from src.server.blocks import AIR
        protected = {"barrier", "obsidian", "end_stone", "bedrock", "command_block", "end_portal", "end_portal_frame"}
        self.slowed = False
        broken = 0
        visited = set()
        for part in self.get_damage_parts()[:2]:
            for x in range(math.floor(part.x), math.ceil(part.x + part.width)):
                if not self.world.is_chunk_loaded(x // 16):
                    continue
                for y in range(max(0, math.floor(part.y)), min(256, math.ceil(part.y + part.height))):
                    for z in (0, 1):
                        if (x, y, z) in visited:
                            continue
                        visited.add((x, y, z))
                        block = self.world.get_block(x, y, z)
                        if block.block_id == "air":
                            continue
                        if block.block_id in protected or not getattr(self.world, "mob_griefing", True):
                            self.slowed = True
                        elif broken < 48:
                            self.world.set_block(AIR(), x, y, z, block_update=False)
                            broken += 1
        if broken:
            from src.server.particles import EXPLOSION as ExplosionParticle
            self.world.spawn_particle(ExplosionParticle(self.x + 8, self.y + 4, 0))

    def update(self):
        if self.removed:
            return
        if self.health <= 0 or self.dying:
            if not self.dying:
                self.die()
            self._tick_death()
            return
        self.tick_damage_state()
        self.age += 1
        crystal = self.world.entities.get(self.healing_crystal_uuid)
        if crystal is not None and not crystal.removed and crystal.health > 0:
            if self.age % 10 == 0:
                self.health = min(self.max_health, self.health + 1)
        else:
            self.healing_crystal_uuid = None
        # Vanilla occasionally picks the closest crystal in an expanded AABB.
        if random.randrange(10) == 0:
            crystals = [e for e in tuple(self.world.entities.values())
                        if e.entity_id == "ender_crystal" and not e.removed and e.health > 0
                        and e.x + e.width > self.x - 32 and e.x < self.x + self.width + 32
                        and e.y + e.height > self.y - 32 and e.y < self.y + self.height + 32]
            nearest = min(crystals, key=lambda e: (e.x + e.width / 2 - self.x - self.width / 2) ** 2
                          + (e.y + e.height / 2 - self.y - self.height / 2) ** 2, default=None)
            self.healing_crystal_uuid = str(nearest.uuid) if nearest is not None else None
        previous_anim = self.dragon_anim
        speed = math.hypot(self.motion.x, self.depth_motion)
        self.dragon_anim += .2 / (speed * 10 + 1) * 2 ** max(-2, min(2, self.motion.y)) * (.5 if self.slowed else 1)
        if self.no_ai:
            self.dragon_anim = .5
        else:
            self._fly()
            self._contact()
            self._break_terrain()
        self.dragon_history.insert(0, (self.dragon_yaw, self.y + 4))
        del self.dragon_history[64:]
        if math.cos(previous_anim * math.tau) <= -.3 < math.cos(self.dragon_anim * math.tau):
            self._sound("mob.enderdragon.wings")
        self._growl_ticks -= 1
        if self._growl_ticks <= 0:
            self._sound("mob.enderdragon.growl")
            self._growl_ticks = random.randint(160, 320)

    def apply_damage(self, amount, damage_type=GENERIC, source=None, knockback=None, **kwargs):
        return self.apply_part_damage("body", amount, damage_type, source=source, **kwargs)

    def apply_knockback(self, *args, **kwargs):
        # Explosions also try their generic impulse when damage is rejected.
        # Dragon motion is controlled exclusively by its flight steering.
        pass

    def apply_part_damage(self, part, amount, damage_type=GENERIC, source=None, knockback=None, **kwargs):
        if self.dying or self.removed:
            return 0.0
        damage_type = damage_type or GENERIC
        if (getattr(source, "entity_id", None) != "player"
                and damage_type not in {EXPLOSION, PLAYER_EXPLOSION, THORNS}):
            return 0.0
        amount = float(amount)
        if not math.isfinite(amount) or amount <= 0:
            return 0.0
        if part != "head" and damage_type is not THORNS:
            amount = amount / 4 + 1
        # Hits redirect the flight target but never knock the huge flying root
        # back using the normal humanoid impulse.
        angle = math.radians(self.dragon_yaw)
        self.flight_target = (self.x + 8 + math.sin(angle) * 5 + random.uniform(-1, 1),
                              self.y + 5 + random.random() * 3,
                              self.flight_depth - math.cos(angle) * 5 + random.uniform(-1, 1))
        self.flight_player_uuid = None
        return super().apply_damage(amount, damage_type, source, None, **kwargs)

    def on_damage_applied(self, actual_damage, raw_damage, damage_type, source):
        self._sound("mob.enderdragon.hit")
        if self.health <= 0:
            self.die()

    def die(self):
        if self.removed or self.dying:
            return
        self.health = 0
        self.dying = True
        self.healing_crystal_uuid = None
        self.motion.x = self.motion.y = self.depth_motion = 0

    def _tick_death(self):
        from src.server.particles import EXPLOSION as ExplosionParticle, EXPLOSION_EMITTER
        self.death_ticks += 1
        self.age += 1
        if self.death_ticks == 1:
            self._sound("mob.enderdragon.end", global_=True)
        self.y += .1
        self.dragon_yaw = wrap_degrees(self.dragon_yaw + 20)
        cx, cy = self.x + 8 + random.uniform(-4, 4), self.y + 4 + random.uniform(-2, 2)
        if self.death_ticks >= 180:
            self.world.spawn_particle(EXPLOSION_EMITTER(cx, cy, 0, data={"power": 2}))
        elif self.death_ticks % 2 == 0:
            self.world.spawn_particle(ExplosionParticle(cx, cy, 0))
        if self.death_ticks > 150 and self.death_ticks % 5 == 0 and getattr(self.world, "do_mob_loot", True):
            self.world.spawn_experience(self.x + 8, self.y + 4, 0, 1000)
        if self.death_ticks >= 200:
            if getattr(self.world, "do_mob_loot", True):
                self.world.spawn_experience(self.x + 8, self.y + 4, 0, 2000)
            fight = getattr(self.world, "end_fight", None)
            if fight is not None:
                fight.dragon_died(self)
            self.world.remove_entity(self)

    def to_entity_data(self):
        return {**super().to_entity_data(), "healing_crystal_uuid": self.healing_crystal_uuid,
                "dragon_yaw": self.dragon_yaw, "dragon_turn": self.dragon_turn,
                "dragon_anim": self.dragon_anim, "dragon_age": self.age,
                "dragon_history": self.dragon_history[:24], "dragon_death_ticks": self.death_ticks,
                "dragon_dying": self.dying, "dragon_slowed": self.slowed}

    def get_persistent_data(self):
        return {"age": self.age, "healing_crystal_uuid": self.healing_crystal_uuid,
                "dragon_yaw": self.dragon_yaw, "dragon_turn": self.dragon_turn,
                "dragon_anim": self.dragon_anim, "dragon_history": self.dragon_history,
                "flight_depth": self.flight_depth, "depth_motion": self.depth_motion,
                "flight_target": self.flight_target, "flight_player_uuid": self.flight_player_uuid,
                "dying": self.dying, "death_ticks": self.death_ticks,
                "target_age": self._target_age, "slowed": self.slowed}

    def read_persistent_data(self, data):
        self.age = max(0, int(data.get("age", 0)))
        self.healing_crystal_uuid = data.get("healing_crystal_uuid")
        self.dragon_yaw = float(data.get("dragon_yaw", self.dragon_yaw))
        self.dragon_turn = float(data.get("dragon_turn", 0))
        self.dragon_anim = float(data.get("dragon_anim", 0))
        self.dragon_history = [tuple(pair) for pair in data.get("dragon_history", self.dragon_history)][:64]
        self.flight_depth = float(data.get("flight_depth", 0))
        self.depth_motion = float(data.get("depth_motion", 0))
        self.flight_target = tuple(data.get("flight_target", self.flight_target))
        self.flight_player_uuid = data.get("flight_player_uuid")
        self.dying = bool(data.get("dying", False))
        self.death_ticks = max(0, min(199, int(data.get("death_ticks", 0))))
        self._target_age = int(data.get("target_age", 0))
        self.slowed = bool(data.get("slowed", False))
