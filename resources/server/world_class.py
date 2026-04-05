import logging
from typing import Any
from typing import cast

import numpy as np

from resources.server.block_class import Block
from resources.server.blocks import AIR

class Chunk:
    def __init__(self, x, region_array: np.ndarray[Any, np.dtype[Block]]):
        self.x = x
        self.region_array = region_array

    def to_dict(self) -> dict:

        # Blocks to dict
        result_dict = {}
        for x in range(self.region_array.shape[0]):
            for y in range(self.region_array.shape[1]):
                for z in range(self.region_array.shape[2]):
                    block: Block = cast(Block, self.region_array[x, y, z])
                    result_dict[f"{x},{y},{z}"] = block.to_dict()

        return {
            "__class__": "Chunk",
            "x": self.x,
            "region_array": result_dict,
        }


class WorldAttribute:
    def __init__(self, environment = 0, max_build_height = 256):
        self.ENVIRONMENT = environment
        self.MAX_BUILD_HEIGHT = max_build_height

class World:
    def __init__(self, id_name, generate_method, attribute: WorldAttribute, seed):
        self.id_name = id_name
        self.generate_method = generate_method
        self.attribute = attribute
        self.seed = seed
        self.regions: dict[int, Chunk] = {}

    def get_block(self, x: int, y: int, z: int) -> Block:
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        block = cast(Block, chunk.region_array[rela_x, y, z]) # 强迫症写法，为了避免烦人的IDE警报
        return block

    def set_block(self, x: int, y: int, z: int, block: Block):
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        chunk.region_array[rela_x][y][z] = block

    def generate_chunk(self, rx: int):
        logging.debug(f"Generating {self.id_name} chunk {rx}")
        y_max = self.attribute.MAX_BUILD_HEIGHT
        chunk = np.full((16, y_max, 2), AIR(), dtype=Block)
        for x in range(0, 16):
            for y in range(0, y_max):
                for z in range(0, 2):
                    chunk[x][y][z] = self.generate_method(x, y, z, self.seed)
        self.regions[rx] = Chunk(rx, chunk)





