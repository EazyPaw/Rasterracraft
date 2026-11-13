"""Server-side EntityCreeper / EntityAICreeperSwell behavior (1.8.9)."""
import random

from src.server.entity import Entity
from src.server.entity_AI import HostileMobAI, Goal, GoalFlag
from src.server.entity_registry import register_entity
from src.server.entities.nether import visible, loot
from src.server.location import Location


class SwellGoal(Goal):
    flags = frozenset({GoalFlag.MOVE})

    def can_use(self):
        target = self.ai.get_target()
        return self.entity.swell_state > 0 or (target is not None and
                                               self.ai.distance_squared_to(target) < 9.0)

    def start(self):
        self.ai.move_control.stop()

    def tick(self):
        target = self.ai.get_target()
        self.entity.swell_state = (1 if target is not None and
            self.ai.distance_squared_to(target) <= 49.0 and visible(self.entity, target) else -1)


class CreeperAI(HostileMobAI):
    def on_hurt(self, source):
        if super().can_target(source):
            self.set_target(source)

    def can_target(self, player, extra_range=0.0):
        return (super().can_target(player, extra_range) and
                (str(getattr(player, "uuid", "")) == self.entity.target_uuid or
                 visible(self.entity, player)))

    def register_goals(self):
        super().register_goals()
        self.goal_selector.add(1, SwellGoal(self))

    def try_attack(self, target):
        # Creepers navigate with the melee goal but never deal melee damage.
        return False


@register_entity
class Creeper(Entity):
    entity_id = "creeper"
    translation_key = "entity.Creeper.name"
    experience_reward = 5
    sounds = {"hurt": "mob.creeper.say", "death": "mob.creeper.death"}

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = int(z)
        self.width, self.height = 0.6, 1.7
        self.max_health = self.health = 20.0
        self.follow_range = 16.0
        self.move_speed = 0.1 * (0.25 / 0.23)
        self.swell_state = -1
        self.fuse_ticks = 0
        self.fuse_time = 30
        self.explosion_radius = 3
        self.ignited = False
        self.powered = False
        self.ai = CreeperAI(self)

    def update_ai(self):
        self.ai.tick()
        if self.ignited:
            self.swell_state = 1
        if self.swell_state > 0 and self.fuse_ticks == 0 and not self.silent:
            self.world.server.broadcast_sound("creeper.primed", self.x, self.y, self.z,
                                              world=self.world, volume=1.0)
        self.fuse_ticks = max(0, self.fuse_ticks + self.swell_state)
        if self.fuse_ticks >= self.fuse_time:
            # Remove before the blast: explosions must not trigger death loot.
            self.world.remove_entity(self)
            self.world.spawn_explosion(Location(self.world, self.x + self.width / 2,
                self.y, self.z), power=self.explosion_radius * (2 if self.powered else 1),
                source=self, break_block=bool(getattr(self.world, "mob_griefing", True)))

    def move_update(self):
        if not self.removed:
            super().move_update()

    def ignite(self):
        self.ignited = True

    def cause_fall_damage(self, fall_distance, damage_multiplier=1.0):
        damage = super().cause_fall_damage(fall_distance, damage_multiplier)
        self.fuse_ticks = min(max(0, self.fuse_time - 5),
                              self.fuse_ticks + int(fall_distance * 1.5))
        return damage

    def interact(self, player, held_stack):
        if held_stack is None or held_stack.is_empty() or held_stack.material.name_id != "flint_and_steel":
            return False
        self.ignite()
        if getattr(player.gamemode, "name_id", "survival") != "creative":
            held_stack.hurt_and_break(1, player)
        return True

    def get_drops(self):
        return loot(("gunpowder", random.randint(0, 2)))

    def get_synced_data(self):
        return {"swell_state": self.swell_state, "fuse_ticks": self.fuse_ticks,
                "fuse_time": self.fuse_time, "powered": self.powered}

    def get_persistent_data(self):
        return {**self.get_synced_data(), "ignited": self.ignited,
                "explosion_radius": self.explosion_radius}

    def read_persistent_data(self, data):
        self.fuse_time = max(1, min(32767, int(data.get("fuse_time", 30))))
        self.fuse_ticks = max(0, min(self.fuse_time, int(data.get("fuse_ticks", 0))))
        self.swell_state = 1 if data.get("swell_state", -1) > 0 else -1
        self.powered = bool(data.get("powered", False))
        self.ignited = bool(data.get("ignited", False))
        self.explosion_radius = max(0, min(127, int(data.get("explosion_radius", 3))))
