"""The single 1.8 End island and shared-template arena structures."""
import json
import math
from functools import cached_property, lru_cache
from pathlib import Path

from noise import pnoise1

from src.server.generator.base import Generator
from src.server.blocks import AIR, END_STONE, END_PORTAL, get_block_by_id
from src.server.location import Location
from src.server.structure import iter_structure_blocks, load_structure_data


LAYOUT_PATH = Path(__file__).resolve().parents[3] / "worldgen/end.json"


class End(Generator):
    """Finite main island, endless surrounding void; no modern outer islands."""
    @lru_cache(maxsize=1024)
    def column(self, x):
        radius = 96 + pnoise1((x + self.seed % 4096) / 27, base=self.seed % 256) * 3
        if abs(x) >= radius:
            return None
        edge = max(0, 1 - (abs(x) / radius) ** 2)
        # Only the fountain apron is level. Broad seeded hills and small
        # undulations continue across chunk boundaries toward the tapered rim.
        blend = max(0.0, min(1.0, (abs(x) - 4) / 10))
        blend = blend * blend * (3 - 2 * blend)
        hills = (pnoise1((x + self.seed % 8192) / 32, base=self.seed % 256) * 10
                 + pnoise1((x - self.seed % 4096) / 11, base=(self.seed + 17) % 256) * 2)
        top = round(64 + blend * (48 + 16 * math.sqrt(edge) - 64 + hills * edge))
        bottom = int(top - 8 - 28 * math.sqrt(edge)
                     + pnoise1((x + self.seed % 8192) / 11, base=self.seed % 256) * 4)
        return bottom, top

    def get_original_block(self, x, y, z):
        column = self.column(int(x))
        return END_STONE() if column and column[0] <= y <= column[1] else AIR()

    def get_original_biome(self, x, y):
        return "sky"

    def get_spawn_height(self, x=100):
        return 51.0


class EndStructures:
    """Use the same template loader, NBT and chunk slicing as other structures."""
    @cached_property
    def layout(self):
        data = json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
        if data.get("format_version") != 1:
            raise ValueError("Unsupported End arena layout")
        return data

    @cached_property
    def templates(self):
        return {p["template"]: load_structure_data(p["template"])[1] for p in self.layout["pieces"]}

    def apply_chunk(self, world, rx, blocks):
        for piece in self.layout["pieces"]:
            data = self.templates[piece["template"]]
            for x, y, z, entry in iter_structure_blocks(data, tuple(piece["origin"]), x_bounds=(rx * 16, rx * 16 + 15)):
                if not 0 <= y < blocks.shape[1]:
                    continue
                block = get_block_by_id(entry["id"])
                if entry.get("nbt"):
                    block.write_nbt(entry["nbt"])
                block.location = Location(world, x, y, z)
                blocks[x % 16, y, z] = block
        if world.end_fight.dragon_killed:
            for x, y, z in self.layout["exit_cells"]:
                if x // 16 == rx:
                    block = END_PORTAL({"exit_portal": True})
                    block.location = Location(world, x, y, z)
                    blocks[x % 16, y, z] = block
