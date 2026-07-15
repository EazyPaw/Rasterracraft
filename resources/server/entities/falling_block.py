import math

from resources.server import blocks
from resources.server.entity import Entity
from resources.server.location import Location


class FallingBlock(Entity):
    def __init__(self, x, y, z, world, block: blocks.Block):
        super().__init__(x, y, world)
        self.entity_id = "falling_block"
        self.height = 1
        self.width = 0.98
        self.block = block
        self.z = z
        self.gravity = 0.04
        self.drag_vertical = 0.98
        self.air_friction = 0.98
        self.damping = self.air_friction

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        return super()._is_block_solid(x, y, self.z)

    def _get_block_at(self, x: float, y: float, z: int = 0):
        return super()._get_block_at(x, y, self.z)

    def move_update(self):
        if self.y < -4:
            self.world.remove_entity(self)
            return
        super().move_update()
        if self.on_ground:
            x = math.floor(self.x)
            y = math.floor(self.y)
            loc = Location(self.world, x, y, self.z)
            target = self.world.get_block(loc)
            if target.replaceable:
                self.world.set_block(self.block, loc)
            elif not target.solid:
                self.world.break_block(loc)
                self.world.set_block(self.block, loc)
            self.world.remove_entity(self)
