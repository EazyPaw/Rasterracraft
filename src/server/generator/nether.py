"""Java 1.8 Nether features adapted to the game's two depth layers.

Coordinate noise and structure plans are pure functions: chunk order and worker
count cannot change the terrain. Natural terrain stops at 128; building is 256.
"""
from functools import lru_cache

from noise import pnoise2

from src.server.generator.base import Generator
from src.server.generator.fortress import NetherFortressGenerator
from src.server.blocks import (
    AIR, BEDROCK, NETHERRACK, LAVA, SOUL_SAND, GRAVEL, GLOWSTONE,
    NETHER_QUARTZ_ORE, FIRE, BROWN_MUSHROOM, RED_MUSHROOM,
)


class Nether(Generator):
    terrain_height = 128
    lava_level = 32

    def _noise(self, x, y, scale, salt=0, octaves=1):
        offset = (self.seed + salt * 7919) % 100003
        return pnoise2((x + offset) / scale, (y - offset) / scale,
                       octaves=octaves, base=(self.seed + salt) % 256)

    def _hash(self, x, y=0, salt=0):
        value = (int(x) * 341873128712 + int(y) * 132897987541
                 + self.seed + salt * 374761393) & ((1 << 64) - 1)
        value = ((value ^ (value >> 30)) * 0xbf58476d1ce4e5b9) & ((1 << 64) - 1)
        return value ^ (value >> 27)

    @lru_cache(maxsize=131072)
    def _solid(self, x, y):
        if y < 5 or y >= 122:
            return True
        # Multiple shelves around large caverns, with tunnels between them.
        floor = 26 + self._noise(x, 0, 105, 1, 3) * 32
        ceiling = 109 + self._noise(x, 0, 90, 2, 2) * 19
        if y < floor or y > ceiling:
            return True
        density = self._noise(x, y * 1.6, 48, 3, 3)
        return density > 0.12 + 0.08 * self._noise(x, y, 120, 4)

    @lru_cache(maxsize=65536)
    def _layer_solid(self, x, y, z):
        # Expand only the rear rock silhouette, not structures/decorations.
        # A one-block rim around floors, ceilings and walls reveals depth.
        return self._solid(x, y) or (z == 1 and any(
            self._solid(x + dx, y + dy)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1))
        ))

    @lru_cache(maxsize=65536)
    def _terrain_id(self, x, y, z=0):
        if y < 0 or y >= 128:
            return "air"
        if y <= self._hash(x, 0, 5) % 5 or y >= 127 - self._hash(x, 127, 5) % 5:
            return "bedrock"
        if self._layer_solid(x, y, z):
            if not self._layer_solid(x, y + 1, z) and 29 <= y <= 65:
                surface = self._noise(x, 0, 24, 6, 2)
                if surface > 0.09:
                    return "soul_sand"
                if surface < -0.12:
                    return "gravel"
            if 10 <= y <= 117 and self._noise(x, y, 5, 7) > 0.34:
                return "nether_quartz_ore"
            return "netherrack"
        if y < self.lava_level:
            return "lava"
        if self._layer_solid(x, y + 1, z) and self._noise(x, y, 9, 8) > 0.16:
            return "glowstone"
        if self._layer_solid(x, y - 1, z):
            value = self._hash(x, y, 9) % 95
            if value == 0:
                return "fire"
            if value == 1:
                return "brown_mushroom"
            if value == 2:
                return "red_mushroom"
        # Thin lava falls originate in the ceiling; no water or modern ores.
        if self._hash(x, 0, 10) % 127 == 0:
            for source_y in range(y + 1, min(123, y + 55)):
                if self._layer_solid(x, source_y, z):
                    return "lava"
        return "air"

    def get_original_block(self, x, y, z):
        block_type = TERRAIN_BLOCKS[self._terrain_id(int(x), int(y), z)]
        if block_type is LAVA and y >= self.lava_level:
            return LAVA(falling=not self._layer_solid(int(x), int(y) + 1, z))
        return block_type()

    def get_original_biome(self, x, y):
        return "hell"


TERRAIN_BLOCKS = {cls.block_id: cls for cls in (
    AIR, BEDROCK, NETHERRACK, LAVA, SOUL_SAND, GRAVEL, GLOWSTONE,
    NETHER_QUARTZ_ORE, FIRE, BROWN_MUSHROOM, RED_MUSHROOM,
)}
