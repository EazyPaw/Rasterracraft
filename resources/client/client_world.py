import logging
from typing import Any, cast

import numpy as np

from resources.server.block_class import Block
from resources.server.blocks import get_block_by_id, AIR


class ClientWorld:
    def __init__(self):
        self._region: dict[int, np.ndarray[Any, np.dtype[Block]]] = {}
        self.y_max = 256

    def load_chunk(self, rx: int, chunk: dict[str, dict]):
        chunk_array = np.full((16, self.y_max, 2), AIR(), dtype=Block)
        logging.debug(f"Loading chunk {rx}")
        for key, value in chunk.items():
            x, y, z = key.split(",")
            x, y, z = int(x), int(y), int(z)
            block = get_block_by_id(value["id"])
            chunk_array[x][y][z] = block
        self._region[rx] = chunk_array

    def unload_chunk(self, x: int):
        del self._region[x]

    def get_block(self, x: int, y: int, z: int) -> Block:
        chunk = self._region.get(x // 16)
        rela_x = x % 16
        if chunk is None:
            return AIR()
        block = cast(Block, chunk[rela_x, y, z]) # 强迫症写法，为了避免烦人的IDE警报
        return block