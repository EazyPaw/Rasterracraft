"""Flat crystal core/frames and authoritative healing beams."""
import math
from collections import OrderedDict

import pygame

from src.client.entity_skeleton import EntitySkeleton
from src.server.utils import client_method
from src.client.dragon_skeleton import EnderDragonSkeleton


_crystal_cache = OrderedDict()
_crystal_bytes = 0
_CRYSTAL_CACHE_BYTES = 6 * 1024 * 1024


def crystal_parts(sheet, size, phase):
    global _crystal_bytes
    key = (sheet, size, phase)
    if key in _crystal_cache:
        _crystal_cache.move_to_end(key)
        return _crystal_cache[key]
    # ModelEnderCrystal uses glass UV (0,0), core UV (32,0), 8px cubes.
    # Only their front faces are used: no fragile pseudo-3D cube skeleton.
    ux, uy = sheet.get_width() / 64, sheet.get_height() / 32
    def face(x, y):
        return sheet.subsurface((round(x * ux), round(y * uy), round(8 * ux), round(8 * uy)))
    frame = pygame.transform.scale(face(8, 8), (size, size))
    inner = pygame.transform.scale(face(40, 8), (max(1, size // 2),) * 2)
    parts = (pygame.transform.rotate(frame, phase * 5),
             pygame.transform.rotate(frame, -phase * 5 + 45),
             pygame.transform.rotate(inner, phase * 5 * 1.5))
    cost = sum(p.get_pitch() * p.get_height() for p in parts)
    while _crystal_cache and (_crystal_bytes + cost > _CRYSTAL_CACHE_BYTES or len(_crystal_cache) >= 96):
        _, old = _crystal_cache.popitem(last=False)
        _crystal_bytes -= sum(p.get_pitch() * p.get_height() for p in old)
    if cost <= _CRYSTAL_CACHE_BYTES:
        _crystal_cache[key] = parts
        _crystal_bytes += cost
    return parts


class EnderCrystalSkeleton(EntitySkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, "entity.endercrystal.endercrystal", entity)

    def draw(self):
        render = self.client.render
        # Rotation/bob follow RenderEnderCrystal, interpolated between packets.
        age = float(self.entity.inner_rotation) + (pygame.time.get_ticks() % 50) / 50
        bob = math.sin(age * .2) / 2 + .5
        bob = (bob * bob + bob) * .2
        wx, wy = self._render_x + 1, self._render_y + .8 + bob
        sx, sy = render.trans_world_location((wx, wy))
        entities = self.client.client_world.iter_entities()
        for dragon in entities:
            if (dragon.entity_id == "ender_dragon" and dragon.health > 0
                    and dragon.healing_crystal_uuid == self.entity.uuid):
                endpoint = render.trans_world_location((dragon.x + dragon.width / 2, dragon.y + dragon.height / 2))
                width = max(2, round(render.block_size * .1))
                pygame.draw.line(render.screen, (92, 24, 120), (sx, sy), endpoint, width)
                pygame.draw.line(render.screen, (244, 190, 255), (sx, sy), endpoint, max(1, width // 3))
        size = max(8, min(256, round(render.block_size * 1.15)))
        for part in crystal_parts(self.texture, size, round(age * 3 / 5) % 72):
            render.blit(part, part.get_rect(center=(round(sx), round(sy))))
