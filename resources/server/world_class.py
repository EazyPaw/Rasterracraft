from enum import Enum
from typing import Any
from typing import cast

import numpy as np

from resources.server.block_class import Block
from resources.server.blocks import AIR


class WorldAttribute(Enum):
    ENVIRONMENT = 0
    MAX_BUILD_HEIGHT = 256

class World:
    def __init__(self, id_name, generate_method, attribute: WorldAttribute, seed):
        self.id_name = id_name
        self.generate_method = generate_method
        self.attribute = attribute
        self.seed = seed
        self.grid: dict[int, np.ndarray[Any, np.dtype[Block]]] = {}

    def get_block(self, x: int, y: int, z: int) -> Block:
        chunk = self.grid.get(x // 16)
        rela_x = x % 16
        block = cast(Block, chunk[rela_x, y, z]) # 强迫症写法，为了避免烦人的IDE警报
        return block

    def set_block(self, x: int, y: int, z: int, block: Block):
        chunk = self.grid.get(x // 16)
        rela_x = x % 16
        chunk[rela_x][y][z] = block

    def generate_chunk(self, rx: int):
        y_max = self.attribute.MAX_BUILD_HEIGHT.value
        chunk = np.full((16, y_max, 2), AIR(), dtype=Block)
        for x in range(0, 16):
            for y in range(0, y_max):
                for z in range(0, 2):
                    chunk[x][y][z] = self.generate_method(x, y, z, self.seed)
        self.grid[rx] = chunk



