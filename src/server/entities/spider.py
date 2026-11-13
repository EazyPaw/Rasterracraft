"""1.8.9 spider targeting, leaping, wall climbing and drops."""
import math
import random

from src.server.entity import Entity
from src.server.entity_AI import HostileMobAI
from src.server.entity_registry import register_entity
from src.server.entities.nether import visible, loot
from src.server.mob_rules import brightness


class SpiderAI(HostileMobAI):
    def can_target(self, player, extra_range=0.0):
        if not super().can_target(player, extra_range):
            return False
        # Existing aggression and retaliation survive daylight until the
        # attack goal's 1-in-100 chance to give up.
        return (str(getattr(player, "uuid", "")) == self.entity.target_uuid or
                (brightness(self.entity) < 0.5 and visible(self.entity, player)))

    def on_hurt(self, source):
        if super().can_target(source):
            self.set_target(source)

    def is_in_attack_reach(self, target):
        dx = self.entity.x + self.entity.width / 2 - target.x - target.width / 2
        dy = self.entity.y - target.y
        return dx * dx + dy * dy <= 4.0 + target.width


@register_entity
class Spider(Entity):
    entity_id = "spider"
    translation_key = "entity.Spider.name"
    experience_reward = 5
    sounds = {"ambient": "mob.spider.say", "hurt": "mob.spider.say", "death": "mob.spider.death"}

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = int(z)
        self.width, self.height = 1.4, 0.9
        self.max_health = self.health = 16.0
        self.follow_range = 16.0
        self.attack_damage = 2.0
        self.move_speed = 0.1 * (0.3 / 0.23)
        self.climbing = False
        self.ai = SpiderAI(self)

    def update_ai(self):
        if self.no_ai:
            return
        target = self.ai.get_target()
        if target is not None and brightness(self) >= 0.5 and random.randrange(100) == 0:
            self.ai.set_target(None)
        self.ai.tick()
        target = self.ai.get_target()
        if target is not None and self.on_ground and random.randrange(5) == 0:
            dx = target.x + target.width / 2 - self.x - self.width / 2
            dy = target.y - self.y
            distance = dx * dx + dy * dy
            if 4.0 <= distance <= 16.0:
                self.motion.x = self.motion.x * 0.2 + math.copysign(0.4, dx)
                self.motion.y = 0.4

    def is_on_climbable(self):
        return self.horizontal_collision or super().is_on_climbable()

    def move_update(self):
        super().move_update()
        self.climbing = self.horizontal_collision

    def add_status_effect(self, instance):
        if instance.effect_id in {"poison", "minecraft:poison"}:
            return False
        return super().add_status_effect(instance)

    def get_drops(self):
        drops = loot(("string", random.randint(0, 2)))
        if getattr(self.last_damage_source, "entity_id", None) == "player" and random.randrange(3) == 0:
            drops.extend(loot(("spider_eye", 1)))
        return drops

    def get_synced_data(self):
        return {"climbing": self.climbing}
