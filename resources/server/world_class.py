import logging
from typing import Any
from typing import cast

import numpy as np

from resources.server.block_class import Block
from resources.server.blocks import AIR
from resources.server.light_manager import flood_fill_light_2d
from resources.server.location import Location, decide_x_or_loc


class Chunk:
    def __init__(self, x, region_array: np.ndarray[Any, np.dtype[Block]]):
        self.x = x
        self.region_array = region_array
        size = self.region_array.shape
        self.sky_light_array = np.full((size[0], size[1]), 0, dtype=np.uint8)
        self.block_light_array = np.full((size[0], size[1]), 0, dtype=np.uint8)
        self.set_sky_light()


    def to_dict(self) -> dict:

        # Blocks to dict
        result_dict = {}
        for x in range(self.region_array.shape[0]):
            for y in range(self.region_array.shape[1]):
                for z in range(self.region_array.shape[2]):
                    block: Block = cast(Block, self.region_array[x, y, z])
                    result_dict[f"{x},{y},{z}"] = block.to_dict()
        light_dict = {}
        # Block light
        for x in range(self.region_array.shape[0]):
            for y in range(self.region_array.shape[1]):
                sky_light = cast(int, self.sky_light_array[x, y])
                block_light = cast(int, self.block_light_array[x, y])
                light_dict[f"{x},{y}"] = max(sky_light, block_light)
        return {
            "__class__": "Chunk",
            "x": self.x,
            "region_array": result_dict,
            "light_array": light_dict,
        }

    def set_sky_light(self):
        # 天空光：从最顶部的非固体方块作为初始光源（亮度 15）
        max_y = self.region_array.shape[1]
        sources = []
        z = 0  # 光照只计算第一层
        for x in range(self.region_array.shape[0]):
            # 寻找最高处非固体方块，或者直接遍历整列
            for y in range(max_y - 1, -1, -1):
                block = cast(Block, self.region_array[x, y, z])
                if not block.solid:
                    sources.append((x, y, 15))
        # 重置天空光数组
        self.sky_light_array.fill(0)
        flood_fill_light_2d(self.sky_light_array, self.region_array, z, sources, max_light=15)
        print(len(sources))

class WorldAttribute:
    def __init__(self, environment = 0, max_build_height = 256):
        self.ENVIRONMENT = environment
        self.MAX_BUILD_HEIGHT = max_build_height

class World:
    def __init__(self,server: 'Server', id_name, generate_method, attribute: WorldAttribute, seed):
        self.server = server
        self.id_name = id_name
        self.generate_method = generate_method
        self.attribute = attribute
        self.seed = seed
        self.regions: dict[int, Chunk] = {}

    def get_block(self, x_loc: int | Location, y: int = None, z: int = None) -> Block:
        x, y, z = decide_x_or_loc(x_loc, y, z)
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        block = cast(Block, chunk.region_array[rela_x, y, z]) # 强迫症写法，为了避免烦人的IDE警报
        return block

    def get_sky_light(self, x: int, y: int) -> int:
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        light = cast(int, chunk.sky_light_array[rela_x, y])
        return light

    def get_block_light(self, x: int, y: int) -> int:
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        light = cast(int, chunk.block_light_array[rela_x, y])
        return light

    def set_block_light(self, x: int, y: int, light: int):
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        chunk.block_light_array[rela_x, y] = light

    def get_sum_light(self, x: int, y: int) -> int:
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        sky_light = cast(int, chunk.block_light_array[rela_x, y])
        block_light = cast(int, chunk.sky_light_array[rela_x, y])
        return max(sky_light, block_light)

    def set_block(self, block: Block, x_loc: int | Location, y: int = None, z: int = None):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        block.location = Location(self, x, y, z)
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
                    d_x = rx * 16 + x
                    block = self.generate_method(x, y, z, self.seed)
                    chunk[x][y][z] = block
                    block.location = Location(self, d_x, y, z)
        self.regions[rx] = Chunk(rx, chunk)

    def break_block(self, x_loc: int | Location, y: int, z: int):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        self.get_block(x, y, z).on_break()
        self.set_block(AIR(), x, y, z)






