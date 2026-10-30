"""The 1.8.9 pearl's 5% side effect, including its two-minute lifetime."""

from src.server.entity import Entity
from src.server.entity_AI import HostileMobAI
from src.server.entity_registry import register_entity
from src.server.particles import PORTAL


@register_entity
class Endermite(Entity):
    entity_id = "endermite"
    translation_key = "entity.Endermite.name"
    experience_reward = 3
    sounds = {"ambient": "mob.silverfish.say", "hurt": "mob.silverfish.hit",
              "death": "mob.silverfish.kill"}

    def __init__(self, x, y, world, z=0):
        super().__init__(float(x), float(y), world)
        self.z = int(z)
        self.width, self.height = 0.4, 0.3
        self.max_health = self.health = 8.0
        self.move_speed = 0.25
        self.attack_damage = 2.0
        self.interact_range = 0.4
        self.lifetime = 0
        self.player_spawned = False
        self.ai = HostileMobAI(self)

    def get_persistent_data(self):
        return {"lifetime": self.lifetime, "player_spawned": self.player_spawned}

    def read_persistent_data(self, data):
        self.lifetime = max(0, int(data.get("lifetime", 0)))
        self.player_spawned = bool(data.get("player_spawned", False))

    def update(self):
        if not self.persistence_required and not getattr(self, "name", None):
            self.lifetime += 1
        if self.lifetime >= 2400:
            self.world.remove_entity(self)
            return
        super().update()
        if not self.removed:
            self.world.spawn_particle(PORTAL(
                self.x + self.width / 2, self.y, self.z, count=2,
                data={"kind": "ambient", "body_size": (self.width, self.height),
                      "y_offset": 0.0},
            ))

    def update_ai(self):
        self.ai.tick()
