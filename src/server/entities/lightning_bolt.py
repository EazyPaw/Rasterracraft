"""Server-authoritative Minecraft Java 1.8.9 EntityLightningBolt."""
import math
import random

from src.server.entity import Entity
from src.server.entity_registry import register_entity
from src.server.blocks import AIR, FIRE


@register_entity(aliases=("LightningBolt", "lightning"), persistent=False)
class LightningBolt(Entity):
    entity_id = "lightning_bolt"
    attackable = False
    receives_damage = False
    blocks_block_placement = False
    fire_immune = True

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = int(z)
        self.width = self.height = 0.0
        self.lightning_state = 2
        self.bolt_vertex = random.getrandbits(32)
        self.bolt_living_time = random.randrange(1, 4)
        self._started = False

    def tick_entity_portal(self):
        return False

    def _ignite(self, x, y, z):
        world = self.world
        if not getattr(world, "do_fire_tick", True):
            return
        # EntityLightningBolt checks a ten-block loaded area before ignition.
        if any(rx not in world.regions for rx in range(
                (math.floor(self.x) - 10) // 16, (math.floor(self.x) + 10) // 16 + 1)):
            return
        if (x // 16 not in world.regions or z not in (0, 1)
                or not 0 < y < world.attribute.MAX_BUILD_HEIGHT):
            return
        if isinstance(world.get_block(x, y, z), AIR) and world.get_block(x, y - 1, z).solid:
            world.set_block(FIRE(), x, y, z)

    def update(self):
        x, y, z = math.floor(self.x), math.floor(self.y), self.z
        if not self._started:
            self._started = True
            difficulty = getattr(self.world, "difficulty", getattr(self.world.server, "difficulty", "normal"))
            difficulty = getattr(difficulty, "name_id", getattr(difficulty, "value", difficulty))
            if difficulty in (2, 3, "normal", "hard", "NORMAL", "HARD"):
                self._ignite(x, y, z)
                for _ in range(4):
                    self._ignite(x + random.randrange(-1, 2), y + random.randrange(-1, 2),
                                 z + random.randrange(-1, 2))
            self.world.server.broadcast_sound("ambient.weather.thunder", self.x, self.y,
                                              z, world=self.world, volume=10000.0)
            self.world.server.broadcast_sound("random.explode", self.x, self.y,
                                              z, world=self.world, volume=2.0)
        self.lightning_state -= 1
        if self.lightning_state < 0:
            if self.bolt_living_time == 0:
                self.world.remove_entity(self)
                return
            if self.lightning_state < -random.randrange(10):
                self.bolt_living_time -= 1
                self.lightning_state = 1
                self.bolt_vertex = random.getrandbits(32)
                self._ignite(x, y, z)
        if self.lightning_state >= 0:
            # Snapshot and deduplicate: players may also be in the entity map.
            targets = {str(e.uuid): e for e in (*tuple(self.world.entities.values()),
                       *tuple(self.world.server.players))}
            for entity in targets.values():
                if (entity is self or entity.world is not self.world or entity.removed
                        or entity.entity_id == self.entity_id):
                    continue
                if (entity.x + entity.width > self.x - 3 and entity.x < self.x + 3
                        and entity.y + entity.height > self.y - 3 and entity.y < self.y + 9
                        and abs(getattr(entity, "z", 0) - z) < 3):
                    entity.on_struck_by_lightning(self)

    def get_synced_data(self):
        return {"lightning_state": self.lightning_state, "bolt_vertex": self.bolt_vertex}
