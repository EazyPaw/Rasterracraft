# Commented and arranged by ChatGPT
import random

import pygame

from src.client.entity_skeleton import EntitySkeleton
from src.server.blocks import TNT as TNTBlock
from src.server.entity import Entity
from src.server.entity_registry import register_entity
from src.server.location import Location
from src.server.particles import SMOKE
from src.server.utils import client_method


@register_entity(summonable=False)
class PrimedTNT(Entity):
    entity_id = "primed_tnt"
    translation_key = "entity.PrimedTnt.name"

    def __init__(
        self, x: float, y: float, z: int, world, *, fuse: int = 80, owner=None
    ):
        super().__init__(float(x), float(y), world)
        self.entity_id = "primed_tnt"
        self.z = int(z)
        self.width = 0.98
        self.height = 0.98
        self.fuse = max(1, int(fuse))
        self.initial_fuse = self.fuse
        self.owner = owner
        self.owner_uuid = (
            str(owner.uuid) if getattr(owner, "uuid", None) is not None else None
        )
        self.gravity = 0.04
        self.drag_vertical = 0.98
        self.air_friction = 0.98
        self.damping = self.air_friction
        self.motion.x = random.uniform(-0.02, 0.02)
        self.motion.y = 0.2

    @classmethod
    def create_from_save(cls, data: dict, world):
        subtype = data.get("data", {})
        entity = cls(
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            int(data.get("z", 0)),
            world,
            fuse=max(1, int(subtype.get("fuse", 80))),
        )
        entity.initial_fuse = max(
            entity.fuse, int(subtype.get("initial_fuse", entity.initial_fuse))
        )
        return entity

    def get_persistent_data(self) -> dict:
        owner_uuid = getattr(self.owner, "uuid", None) or self.owner_uuid
        return {
            "fuse": max(1, int(self.fuse)),
            "initial_fuse": max(1, int(self.initial_fuse)),
            "owner_uuid": str(owner_uuid) if owner_uuid is not None else None,
        }

    def read_persistent_data(self, data: dict) -> None:
        self.fuse = max(1, int(data.get("fuse", self.fuse)))
        self.initial_fuse = max(
            self.fuse, int(data.get("initial_fuse", self.initial_fuse))
        )
        owner_uuid = data.get("owner_uuid")
        if owner_uuid:
            self.owner_uuid = str(owner_uuid)
            self.owner = getattr(self.world, "entities", {}).get(self.owner_uuid)

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        return super()._is_block_solid(x, y, self.z)

    def _get_block_at(self, x: float, y: float, z: int = 0):
        return super()._get_block_at(x, y, self.z)

    def can_take_damage(self, damage_type=None) -> bool:
        return False

    def to_entity_data(self) -> dict:
        data = super().to_entity_data()
        data["fuse"] = int(self.fuse)
        data["initial_fuse"] = int(self.initial_fuse)
        return data

    def update(self) -> None:
        self.fuse -= 1
        if self.fuse <= 0:
            center = Location(
                self.world,
                self.x + self.width * 0.5,
                self.y + self.height * 0.5 + 0.0625,
                self.z,
            )
            self.world.remove_entity(self)
            self.world.spawn_explosion(
                center,
                power=4.0,
                break_block=True,
                catch_fire=False,
                source=(
                    self.owner
                    or getattr(self.world, "entities", {}).get(self.owner_uuid)
                    or self
                ),
            )
            return

        if self.fuse % 2 == 0:
            self.world.spawn_particle(
                SMOKE(
                    self.x + self.width * 0.5,
                    self.y + self.height + 0.08,
                    self.z,
                    count=1,
                    motion=(0.0, 0.015),
                    data={"motion_spread": [0.008, 0.006]},
                )
            )
        self.move_update()


class PrimedTNTSkeleton(EntitySkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, "blocks.tnt_side", entity)
        self._visual_center = (0.49, 0.49)
        self._block = TNTBlock()

    def update(self):
        pass

    def get_hitbox_render_position(self) -> tuple[float, float]:
        """TNT 当前不插值；判定框必须跟随其实际绘制坐标。"""
        return self.entity.x, self.entity.y

    def draw(self):
        render = self.client.render
        block_size = render.block_size
        fuse = max(0, int(getattr(self.entity, "fuse", 80)))
        texture = self._block.get_texture(block_size)
        if texture is None:
            return

        pulse = 0.0
        if fuse < 10:
            pulse = (1.0 - fuse / 10.0) ** 4 * 0.30
        side = max(1, round(block_size * (1.0 + pulse)))
        if side != texture.get_width():
            texture = pygame.transform.scale(texture, (side, side))
        else:
            texture = texture.copy()

        if (fuse // 2) % 2 == 0:
            texture.fill((105, 105, 105, 0), special_flags=pygame.BLEND_RGB_ADD)
        tint = render.get_world_light_tint(self.entity.x + 0.5, self.entity.y + 0.5)
        texture = render.get_tinted_surface(texture, tint)
        sx, sy = render.trans_world_location(
            (
                self.entity.x + self.entity.width * 0.5,
                self.entity.y + self.entity.height * 0.5,
            )
        )
        render.blit(
            texture,
            (
                round(sx - texture.get_width() * 0.5),
                round(sy - texture.get_height() * 0.5),
            ),
        )
