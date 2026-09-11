"""雪球、鸡蛋等投掷物共用的命中粒子和物品贴图渲染。"""

import pygame

from src.client.entity_skeleton import EntitySkeleton
from src.server.entities.projectile import Projectile, ProjectileHitResult
from src.server.particles import ITEM
from src.server.utils import client_method


class ThrownItem(Projectile):
    default_inaccuracy = 0.0075
    impact_knockback = 0.4

    def __init__(self, x, y, world, z: int = 0, *, owner=None):
        super().__init__(x, y, world, z, owner=owner)
        self.width = 0.5
        self.height = 0.5

    def on_hit(self, result: ProjectileHitResult) -> None:
        spawner = getattr(self.world, "spawn_particle", None)
        if callable(spawner):
            spawner(
                ITEM(
                    result.x + self.width * 0.5,
                    result.y + self.height * 0.5,
                    self.z,
                    count=8,
                    motion=(0.0, 0.015),
                    data={
                        "item_id": self.entity_id,
                        "position_spread": (0.08, 0.08),
                        "motion_spread": (0.06, 0.06),
                    },
                )
            )
        super().on_hit(result)


class ThrownItemSkeleton(EntitySkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, f"items.{entity.entity_id}", entity)
        self._visual_center = (entity.width * 0.5, entity.height * 0.5)
        self._scaled_texture = None
        self._scaled_size = None

    def draw(self):
        render = self.client.render
        size = (
            max(2, round(render.block_size * self.entity.width)),
            max(2, round(render.block_size * self.entity.height)),
        )
        if self._scaled_texture is None or self._scaled_size != size:
            self._scaled_texture = pygame.transform.scale(self.texture, size)
            self._scaled_size = size

        center_x = self._render_x + self.entity.width * 0.5
        center_y = self._render_y + self.entity.height * 0.5
        tint = render.get_world_light_tint(center_x, center_y)
        texture = render.get_tinted_surface(self._scaled_texture, tint)
        screen_x, screen_y = render.trans_world_location((center_x, center_y))
        render.blit(
            texture,
            (
                round(screen_x - texture.get_width() * 0.5),
                round(screen_y - texture.get_height() * 0.5),
            ),
        )
