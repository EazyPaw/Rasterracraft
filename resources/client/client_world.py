from typing import Any

import numpy as np

from resources.server.block_class import Block


class ClientWorld:
    def __init__(self):
        self._grid: dict[int, np.ndarray[Any, np.dtype[Block]]] = {}

    def load_chunk(self, x: int, chunk: np.ndarray[Any, np.dtype[Block]]):
        self._grid[x] = chunk

    def unload_chunk(self, x: int):
        del self._grid[x]