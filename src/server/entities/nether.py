"""Legacy Nether mobs and their server-authoritative attacks."""
import math
import random

from src.server.entity import Entity
from src.server.entity_AI import HostileMobAI
from src.server.entity_registry import register_entity
from src.server.entities.projectile import Projectile
from src.server.damange_type import FIREBALL, GENERIC
from src.server.item_class import ItemStack
from src.server.materials import get_material_by_id
from src.server.status_effects import StatusEffectInstance
from src.server.location import Location


def loot(*entries):
    return [ItemStack(get_material_by_id(item), count) for item, count in entries if count > 0]


def visible(mob, target):
    sx, sy = mob.x + mob.width / 2, mob.y + mob.height * 0.8
    dx, dy = target.x + target.width / 2 - sx, target.y + target.height * 0.7 - sy
    steps = max(1, math.ceil(math.hypot(dx, dy) * 2))
    for i in range(1, steps):
        if mob.world.get_block(math.floor(sx + dx * i / steps),
                               math.floor(sy + dy * i / steps), mob.z).get_collision_box():
            return False
    return True


class PigZombieAI(HostileMobAI):
    def can_target(self, player, extra_range=0.0):
        return (self.entity.anger_ticks > 0
                and str(getattr(player, "uuid", "")) == self.entity.anger_target
                and super().can_target(player, extra_range))


@register_entity(aliases=("pig_zombie", "zombie_pigman"))
class ZombiePigman(Entity):
    entity_id = "zombie_pigman"
    translation_key = "entity.PigZombie.name"
    fire_immune = True
    experience_reward = 5
    sounds = {"ambient": "mob.zombiepig.zpig", "hurt": "mob.zombiepig.zpighurt",
              "death": "mob.zombiepig.zpigdeath"}

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = z
        self.width, self.height = 0.6, 1.95
        self.max_health = self.health = 20
        self.attack_damage = 5
        self.move_speed = 0.1
        self.movement_acceleration = 0.05
        self.interact_range = 1.2
        self.anger_ticks = 0
        self.anger_target = ""
        self.ai = PigZombieAI(self)
        self.held_item = ItemStack(get_material_by_id("golden_sword"), 1)
        self.drops = loot(("rotten_flesh", random.randint(0, 1)),
                          ("gold_nugget", random.randint(0, 1)))

    def update_ai(self):
        self.anger_ticks = max(0, self.anger_ticks - 1)
        self.ai.tick()

    def apply_damage(self, amount, damage_type=GENERIC, source=None, knockback=None, **kwargs):
        result = super().apply_damage(amount, damage_type, source, knockback, **kwargs)
        if result > 0 and getattr(source, "entity_id", "") == "player":
            for other in (self, *tuple(self.world.entities.values())):
                if isinstance(other, ZombiePigman) and abs(other.x - self.x) <= 32 and abs(other.y - self.y) <= 10:
                    other.anger_ticks = random.randint(400, 799)
                    other.anger_target = str(source.uuid)
                    other.target_uuid = str(source.uuid)
        return result

    def get_persistent_data(self):
        return {"anger_ticks": self.anger_ticks, "anger_target": self.anger_target}

    def read_persistent_data(self, data):
        self.anger_ticks = max(0, int(data.get("anger_ticks", 0)))
        self.anger_target = str(data.get("anger_target", ""))


class RangedMob(Entity):
    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = z
        self.ai = HostileMobAI(self)
        self.shot_ticks = 0
        self.wander_ticks = 0
        self.wander_x = 0.0

    def choose_target(self):
        if self.no_ai:
            self.ai.set_target(None)
            return None
        players = [p for p in tuple(self.world.server.players) if self.ai.can_target(p)]
        target = min(players, key=self.ai.distance_squared_to) if players else None
        self.ai.set_target(target)
        if target is not None:
            dx = target.x - self.x
            self.facing = 1 if dx >= 0 else 0
            self.look_angle = math.degrees(math.atan2(target.y - self.y, abs(dx) or 0.001))
        return target

    def shoot_at(self, target, projectile_type, speed=0.6, **kwargs):
        shot = projectile_type(self.x + self.width / 2, self.y + self.height * 0.65,
                               self.world, self.z, owner=self, **kwargs)
        shot.shoot(target.x + target.width / 2 - shot.x,
                   target.y + target.height / 2 - shot.y, speed=speed,
                   inaccuracy=0.03)
        self.world.spawn_entity(shot)


@register_entity(summonable=False, persistent=False)
class SmallFireball(Projectile):
    entity_id = "small_fireball"
    fire_immune = True
    has_visual_fire = True
    damage_type = FIREBALL
    impact_damage = 5
    air_drag = 1.0
    max_lifetime = 200

    def __init__(self, x, y, world, z=0, *, owner=None):
        super().__init__(x, y, world, z, owner=owner)
        self.gravity = 0.0
        self.width = self.height = 0.3125

    def on_hit_entity(self, result):
        if not getattr(result.target, "fire_immune", False):
            if not super().on_hit_entity(result):
                return False
            result.target.set_seconds_on_fire(5)
        return True

    def on_hit_block(self, result):
        from src.server.blocks import FIRE
        x = math.floor(result.x + result.normal_x * 0.51)
        y = math.floor(result.y + result.normal_y * 0.51)
        if self.world.get_block(x, y, self.z).block_id == "air":
            self.world.set_block(FIRE(), x, y, self.z)
        return True


@register_entity(summonable=False, persistent=False)
class LargeFireball(SmallFireball):
    entity_id = "fireball"
    attackable = True
    projectile_collidable = True
    impact_damage = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.width = self.height = 1.0

    def on_hit(self, result):
        if result.kind == "entity":
            callback = getattr(result.target, "on_projectile_hit", None)
            if callable(callback) and callback(self, result) is True:
                return
            returned = (getattr(result.target, "entity_id", "") == "ghast"
                        and getattr(self.get_owner(), "entity_id", "") == "player")
            result.target.apply_damage(1000 if returned else 6, GENERIC if returned else FIREBALL,
                                       source=self.get_owner() or self)
        self.world.spawn_explosion(Location(self.world, result.x, result.y, self.z),
                                   power=1, catch_fire=True, source=self.get_owner())
        self.discard()

    def apply_damage(self, amount, damage_type=GENERIC, source=None, knockback=None, **kwargs):
        if source is None:
            return 0.0
        previous = self.get_owner()
        self.set_owner(source)
        dx = (previous.x - self.x) if previous is not None else (1 if source.facing else -1)
        dy = (previous.y + previous.height / 2 - self.y) if previous is not None else 0
        self.shoot(dx, dy, speed=0.9)
        return float(amount)


@register_entity
class Ghast(RangedMob):
    entity_id = "ghast"
    translation_key = "entity.Ghast.name"
    fire_immune = True
    experience_reward = 5
    sounds = {"ambient": "mob.ghast.moan", "hurt": "mob.ghast.scream", "death": "mob.ghast.death"}

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world, z)
        self.width = self.height = 4.0
        self.max_health = self.health = 10
        self.follow_range = 100
        self.gravity = 0.0
        self.drops = loot(("ghast_tear", random.randint(0, 1)), ("gunpowder", random.randint(0, 2)))

    def update_ai(self):
        if self.no_ai:
            return
        target = self.choose_target()
        self.wander_ticks -= 1
        if self.wander_ticks <= 0 or self.horizontal_collision or self.vertical_collision:
            self.wander_ticks = random.randint(20, 60)
            self.wander_x = random.uniform(-0.09, 0.09)
            self.motion.y = random.uniform(-0.06, 0.06)
        self.motion.x += self.wander_x * 0.12
        if self.y < 36:
            self.motion.y = 0.08
        elif self.y > 110:
            self.motion.y = -0.08
        if target is not None and visible(self, target):
            self.shot_ticks += 1
            if self.shot_ticks >= 20:
                self.shoot_at(target, LargeFireball, 0.5)
                self.shot_ticks = -40
        else:
            self.shot_ticks = min(0, self.shot_ticks)


@register_entity
class Blaze(RangedMob):
    entity_id = "blaze"
    translation_key = "entity.Blaze.name"
    fire_immune = True
    experience_reward = 10
    sounds = {"ambient": "mob.blaze.breathe", "hurt": "mob.blaze.hit", "death": "mob.blaze.death"}

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world, z)
        self.width, self.height = 0.6, 1.8
        self.max_health = self.health = 20
        self.attack_damage = 6
        self.burst_step = 0
        self.drops = loot(("blaze_rod", random.randint(0, 1)))

    def spawn_drops(self):
        if getattr(self.last_damage_source, "entity_id", "") == "player":
            super().spawn_drops()

    def update_ai(self):
        if self.motion.y < 0 and not self.on_ground:
            self.motion.y *= 0.6
        target = self.choose_target()
        self.shot_ticks -= 1
        if self.in_water:
            self.apply_damage(1, GENERIC)
        if target is None:
            self.has_visual_fire = False
            self.burst_step = 0
            self.shot_ticks = 0
            return
        if target.y > self.y:
            self.motion.y += (0.3 - self.motion.y) * 0.3
        if self.ai.is_in_attack_reach(target):
            self.try_attack(target)
        elif visible(self, target) and self.shot_ticks <= 0:
            self.burst_step += 1
            if self.burst_step == 1:
                self.shot_ticks = 60
                self.has_visual_fire = True
            elif self.burst_step <= 4:
                self.shoot_at(target, SmallFireball)
                self.shot_ticks = 6
            else:
                self.burst_step = 0
                self.shot_ticks = 100
                self.has_visual_fire = False
        if abs(target.x - self.x) > 16 or not visible(self, target):
            self.ai.move_control.move_to(target.x, 1.0)
            self.ai.move_control.tick()


@register_entity
class MagmaCube(Entity):
    entity_id = "magma_cube"
    translation_key = "entity.LavaSlime.name"
    fire_immune = True

    def __init__(self, x, y, world, z=0, *, size=None):
        super().__init__(x, y, world)
        self.z = z
        self.set_size(random.choice((1, 2, 4)) if size is None else size)
        self.ai = HostileMobAI(self)
        self.jump_delay = random.randint(10, 30)

    def set_size(self, size):
        self.cube_size = size = max(1, min(4, int(size)))
        self.width = self.height = 0.51 * size
        self.max_health = self.health = size * size
        self.attack_damage = size + 2
        self.experience_reward = size
        self.set_attribute_base_value("armor", size * 3)
        self.drops = loot(("magma_cream", max(0, random.randint(0, 3) - 2))) if size > 1 else []

    def update_ai(self):
        if self.no_ai:
            return
        players = [p for p in tuple(self.world.server.players) if self.ai.can_target(p)]
        target = min(players, key=self.ai.distance_squared_to) if players else None
        self.ai.set_target(target)
        self.jump_delay -= 1
        if self.on_ground and self.jump_delay <= 0:
            self.jump_delay = random.randint(10, 30) * (1 if target else 3)
            self.motion.y = 0.42 + self.cube_size * 0.1
            direction = (1 if target.x > self.x else -1) if target else random.choice((-1, 1))
            self.motion.x = direction * (0.12 + self.cube_size * 0.03)
        if target is not None and self.ai.is_in_attack_reach(target):
            self.try_attack(target)

    def die(self):
        if not self._death_handled and self.cube_size > 1:
            for index in range(random.randint(2, 4)):
                self.world.spawn_entity(MagmaCube(self.x + (index % 2) * self.width / 2,
                    self.y + 0.1, self.world, self.z, size=self.cube_size // 2))
        super().die()

    def get_persistent_data(self):
        return {"size": self.cube_size}

    def read_persistent_data(self, data):
        health = self.health
        self.set_size(data.get("size", 1))
        self.health = min(health, self.max_health)


@register_entity
class WitherSkeleton(Entity):
    entity_id = "wither_skeleton"
    translation_key = "entity.Skeleton.name"
    fire_immune = True
    experience_reward = 5
    sounds = {"ambient": "mob.skeleton.say", "hurt": "mob.skeleton.hurt", "death": "mob.skeleton.death"}

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = z
        self.width, self.height = 0.72, 2.4
        self.max_health = self.health = 20
        self.attack_damage = 4
        self.move_speed = 0.1
        self.movement_acceleration = 0.05
        self.interact_range = 1.2
        self.ai = HostileMobAI(self)
        self.drops = loot(("bone", random.randint(0, 2)), ("coal", max(0, random.randint(0, 2) - 1)))
        self.held_item = ItemStack(get_material_by_id("stone_sword"), 1)

    def update_ai(self):
        self.ai.tick()

    def attack(self, target, damage_type=None, amount=None, knockback=None):
        damage = super().attack(target, damage_type, amount, knockback)
        if damage > 0:
            target.add_status_effect(StatusEffectInstance("wither", 200, 0))
        return damage


@register_entity
class Skeleton(RangedMob):
    entity_id = "skeleton"
    translation_key = "entity.Skeleton.name"
    experience_reward = 5
    sounds = WitherSkeleton.sounds

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world, z)
        self.width, self.height = 0.6, 1.95
        self.max_health = self.health = 20
        self.drops = loot(("bone", random.randint(0, 2)), ("arrow", random.randint(0, 2)))
        self.held_item = ItemStack(get_material_by_id("bow"), 1)

    def update_ai(self):
        target = self.choose_target()
        self.shot_ticks -= 1
        if target is not None and visible(self, target) and self.shot_ticks <= 0:
            from src.server.entities.arrow import Arrow
            self.shoot_at(target, Arrow, 1.6, pickup="disallowed")
            self.shot_ticks = 40
        if target is not None and (abs(target.x - self.x) > 12 or not visible(self, target)):
            self.ai.move_control.move_to(target.x, 1.0)
            self.ai.move_control.tick()
