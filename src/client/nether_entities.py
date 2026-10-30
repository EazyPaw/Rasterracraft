"""Animated legacy Nether models using the existing Minecraft texture atlases."""
import math
import time

import pygame

from src.client.entity_skeleton import EntitySkeleton, PlayerSkeleton
from src.server.entities.zombie import ZombieSkeleton
from src.server.utils import client_method


class ArmedSkeleton(ZombieSkeleton):
    def _update_held_item_texture(self):
        PlayerSkeleton._update_held_item_texture(self)


class PigmanSkeleton(ArmedSkeleton):
    texture_path = "entity.zombie_pigman"


class NetherSkeleton(ArmedSkeleton):
    texture_path = "entity.skeleton.wither_skeleton"
    VISUAL_HEIGHT_BLOCKS = 2.4


class RegularSkeleton(ArmedSkeleton):
    texture_path = "entity.skeleton.skeleton"


class NetherMobSkeleton(EntitySkeleton):
    # ModelBlaze's top/middle/bottom radii are 9/7/5 model pixels.
    # Distinct speeds, directions and phases keep the rings independent.
    BLAZE_ROD_RINGS = (
        (0.95, 9 / 16, -2 * math.pi, 0.0),
        (0.55, 7 / 16, 0.6 * math.pi, math.pi / 4),
        (0.0, 5 / 16, -math.pi, 0.47123894),
    )
    GHAST_TENTACLE_LENGTHS = (2.0, 2.75, 2.25, 3.5, 2.5)
    TEXTURES = {"ghast": "entity.ghast.ghast", "blaze": "entity.blaze",
                "magma_cube": "entity.slime.magmacube", "fireball": "items.fireball",
                "small_fireball": "items.fireball"}

    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, self.TEXTURES[entity.entity_id], entity)
        self._visual_center = (entity.width / 2, entity.height / 2)
        self._parts = []
        if entity.entity_id == "ghast":
            self._parts.append((self.texture.subsurface((16, 16, 16, 16)).copy(),
                                (0.0, 0.8, 4.0, 3.2)))
            for i, height in enumerate(self.GHAST_TENTACLE_LENGTHS):
                # Attach inside the body and let the 8..14-pixel tentacles
                # hang below it; lengthening must not move their roots.
                pixels = round(height * 4)
                self._parts.append((self.texture.subsurface((2, 2, 2, pixels)).copy(),
                                    (i * 0.75 + 0.2, 1.0 - height, 0.4, height)))
        elif entity.entity_id == "blaze":
            self._parts.append((self.texture.subsurface((8, 8, 8, 8)).copy(),
                                (-0.1, 1.1, 0.8, 0.8)))
            rod = self.texture.subsurface((2, 18, 2, 8)).copy()
            for i in range(12):
                self._parts.append((rod, (0.0, self.BLAZE_ROD_RINGS[i // 4][0], 0.14, 0.5)))
        elif entity.entity_id == "magma_cube":
            for row in range(8):
                uv = (32, 18 if row == 2 else 27, 8, 1) if row in (2, 3) else (8, 8 + row, 8, 1)
                self._parts.append((self.texture.subsurface(uv).copy(),
                                    (0, (7 - row) * entity.height / 8, entity.width, entity.height / 8)))
        else:
            self._parts.append((self.texture, (0, 0, entity.width, entity.height)))
        self._scaled_parts = {}

    def _animated_part_rect(self, index, t):
        x, y, width, height = self._parts[index][1]
        if self.entity.entity_id == "ghast" and index:
            x += math.sin(t * 2 + index) * 0.08
            # The roots stay attached while the free ends sway.
            stretch = math.sin(t * 3 + index) * 0.1
            y -= stretch
            height += stretch
        elif self.entity.entity_id == "blaze" and index:
            ring, rod = divmod(index - 1, 4)
            base_y, radius, speed, phase = self.BLAZE_ROD_RINGS[ring]
            x = self.entity.width / 2 - width / 2 + math.cos(t * speed + phase + rod * math.pi / 2) * radius
            y = base_y + math.cos(t * (10 if ring == 2 else 5) + rod * 0.5 + phase) / 16
        elif self.entity.entity_id == "magma_cube" and not self.entity.on_ground:
            y += (7 - index) * min(0.08, abs(self.entity.motion.y) * 0.12)
        return x, y, width, height

    def draw(self):
        render = self.client.render
        t = time.perf_counter()
        for index, (texture, _rect) in enumerate(self._parts):
            x, y, width, height = self._animated_part_rect(index, t)
            size = (max(1, round(width * render.block_size)),
                    max(1, round(height * render.block_size)))
            key = (index, size)
            if key not in self._scaled_parts:
                if len(self._scaled_parts) > 64:
                    self._scaled_parts.clear()
                self._scaled_parts[key] = pygame.transform.scale(texture, size)
            surface = self._scaled_parts[key]
            tint = render.get_world_light_tint(self._render_x, self._render_y)
            if (self.entity.entity_id in {"blaze", "fireball", "small_fireball"}
                    or self.entity.entity_id == "magma_cube" and index in (2, 3)):
                tint = tuple(max(190, c) for c in tint)
            surface = render.get_tinted_surface(surface, tint)
            if self.entity.hurt_time > 0:
                surface = render.get_tinted_surface(surface, (255, 120, 120))
            sx, sy = render.trans_world_location((self._render_x + x, self._render_y + y + height))
            render.blit(surface, (round(sx), round(sy)))
