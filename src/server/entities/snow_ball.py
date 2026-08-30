# Commented and arranged by ChatGPT

import pygame

from src.client.entity_skeleton import EntitySkeleton
from src.server.damange_type import THROWN
from src.server.entities.projectile import Projectile, ProjectileHitResult
from src.server.entity_registry import register_entity
from src.server.particles import ITEM
from src.server.utils import client_method


@register_entity(persistent=False)
class SnowBall(Projectile):
    entity_id = "snowball"
    translation_key = "entity.Snowball.name"
    _texture_path = "items.snowball"

    default_speed = 1.5
    default_inaccuracy = 0.0075
    air_drag = 0.99
    water_drag = 0.80
    impact_damage = 0.0
    impact_knockback = 0.0
    damage_type = THROWN

    def __init__(self, x, y, world, z: int = 0, *, owner=None):
        super().__init__(x, y, world, z, owner=owner)
        self.width = 0.25
        self.height = 0.25
        self.gravity = 0.03

    def on_hit(self, result: ProjectileHitResult) -> None:
        center_x = result.x + self.width * 0.5
        center_y = result.y + self.height * 0.5
        spawner = getattr(self.world, "spawn_particle", None)
        if callable(spawner):
            spawner(
                ITEM(
                    center_x,
                    center_y,
                    self.z,
                    count=8,
                    motion=(0.0, 0.015),
                    data={
                        "item_id": "snowball",
                        "position_spread": (0.08, 0.08),
                        "motion_spread": (0.06, 0.06),
                    },
                )
            )
        super().on_hit(result)


class SnowBallSkeleton(EntitySkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, SnowBall._texture_path, entity)
        self._visual_center = (0.125, 0.125)
        self._scaled_texture = None
        self._scaled_size = None

    def draw(self):
        render = self.client.render
        size = max(2, round(render.block_size * 0.25))
        if self._scaled_texture is None or self._scaled_size != size:
            self._scaled_texture = pygame.transform.scale(self.texture, (size, size))
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

Snowball = SnowBall
