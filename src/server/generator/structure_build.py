"""Void generator used by the in-game structure template editor."""

from src.server.biome import Void
from src.server.blocks import AIR
from src.server.generator.base import Generator


class StructureBuild(Generator):
    """Generate an entirely empty world with a stable editing spawn height."""

    def get_original_block(self, x, y, z):
        return AIR()

    def get_original_biome(self, x, y):
        return Void.biome_id

    @staticmethod
    def get_spawn_height(_x=0) -> float:
        return 100.0
