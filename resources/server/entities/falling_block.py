import math

from resources.client.entity_skeleton import EntitySkeleton
from resources.server import blocks
from resources.server.entity import Entity
from resources.server.entity_registry import register_entity
from resources.server.location import Location
from resources.server.utils import client_method


@register_entity(summonable=False)
class FallingBlock(Entity):
    entity_id = "falling_block"
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

    @classmethod
    def create_from_save(cls, data: dict, world):
        block_data = data.get("data", {}).get("block", {})
        block = blocks.get_block_by_id(block_data.get("id", "sand"))
        nbt = block_data.get("nbt", {})
        if isinstance(nbt, dict) and nbt:
            block.write_nbt(nbt)
        return cls(
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            int(data.get("z", 0)),
            world,
            block,
        )

    def get_persistent_data(self) -> dict:
        return {
            "block": {
                "id": str(self.block.block_id),
                "nbt": dict(self.block.parse_nbt() or {}),
            }
        }

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
            elif not getattr(target, "has_collision_box", lambda: False)():
                self.world.break_block(loc)
                self.world.set_block(self.block, loc)
            self.world.remove_entity(self)


class FallingBlockSkeleton(EntitySkeleton):

    @client_method
    def __init__(self, entity, client = None):
        super().__init__(client, "blocks.sand", entity)
        self._visual_center = (0.5, 0.5)

    def draw(self):
        block = getattr(self.entity, "block", None)
        if block is None:
            return
        render = self.client.render
        bs = render.block_size
        render_x = self._render_x
        render_y = self._render_y
        if getattr(block, "location", None) is not None:
            block.location.x = math.floor(render_x)
            block.location.y = math.floor(render_y)
            block.location.z = getattr(self.entity, "z", block.location.z)
        tex = block.get_texture(bs)
        if tex is None:
            return
        tint = render.get_world_light_tint(render_x + 0.5, render_y + 0.5)
        tex = render.get_tinted_surface(tex, tint)
        sx = (render_x - render.camera.x - 0.5) * bs + render.SCREEN_WIDTH // 2
        sy = render.SCREEN_HEIGHT - (
            ((render_y + 1) - render.camera.y + 0.5) * bs + render.SCREEN_HEIGHT // 2
        )
        render.blit(tex, (round(sx), round(sy)))
