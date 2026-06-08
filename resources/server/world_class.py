import logging
from typing import Any
from typing import cast

import numpy as np

from resources.server.block_class import Block
from resources.server.blocks import AIR
from resources.server.generator import Generator
from resources.server.location import Location, decide_x_or_loc


class Chunk:
    def __init__(self, x, region_array: np.ndarray[Any, np.dtype[Block]]):
        self.x = x
        self.region_array = region_array
        size = self.region_array.shape
        self.sky_light_array = np.zeros((size[0], size[1]), dtype=np.uint8)
        self.block_light_array = np.zeros((size[0], size[1]), dtype=np.uint8)
        self.recalculate_all_light()   # 初始化时直接计算全部光照

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

    def get_full_light_dict(self) -> dict:
        """返回整个区块的光照字典（x,y -> max(sky, block)）"""
        light_dict = {}
        for x in range(self.region_array.shape[0]):
            for y in range(self.region_array.shape[1]):
                sky = int(self.sky_light_array[x, y])
                block = int(self.block_light_array[x, y])
                light_dict[f"{x},{y}"] = max(sky, block)
        return light_dict

    def get_light_update_dict(self, start_x: int, end_x: int,
                              start_y: int, end_y: int) -> dict:
        """获取局部区域的光照字典（保留，用于可能的高效局部更新，但已不使用）"""
        # 当前实现直接重算整个区块，故本方法暂时保留但不再被调用
        light_dict = {}
        for x in range(max(0, start_x), min(self.region_array.shape[0], end_x + 1)):
            for y in range(max(0, start_y), min(self.region_array.shape[1], end_y + 1)):
                sky = int(self.sky_light_array[x, y])
                block = int(self.block_light_array[x, y])
                light_dict[f"{x},{y}"] = max(sky, block)
        return light_dict

    def recalculate_all_light(self):
        """重新计算整个区块的天空光和方块光"""
        SX, SY = self.region_array.shape[0], self.region_array.shape[1]

        # 清零
        self.sky_light_array.fill(0)
        self.block_light_array.fill(0)

        # === 天空光 ===
        sky_sources = []
        for x in range(SX):
            # 从上往下找第一个非固体方块
            for y in range(SY - 1, -1, -1):
                blk = cast(Block, self.region_array[x, y, 0])
                if not blk.solid:
                    sky_sources.append((x, y, 15))
                else:
                    break
        if sky_sources:
            from resources.server.light_manager import flood_fill_light_2d
            flood_fill_light_2d(self.sky_light_array, self.region_array,
                                0, sky_sources)

        # === 方块光 ===
        block_sources = []
        for x in range(SX):
            for y in range(SY):
                blk0 = cast(Block, self.region_array[x, y, 0])
                blk1 = cast(Block, self.region_array[x, y, 1])
                light = blk0.light_source + blk1.light_source
                if light > 0:
                    block_sources.append((x, y, min(15, light)))
        if block_sources:
            from resources.server.light_manager import flood_fill_light_2d
            flood_fill_light_2d(self.block_light_array, self.region_array,
                                0, block_sources)



class WorldAttribute:
    def __init__(self, environment = 0, max_build_height = 256):
        self.ENVIRONMENT = environment
        self.MAX_BUILD_HEIGHT = max_build_height

class World:
    def __init__(self,server: 'Server', id_name, generator, attribute: WorldAttribute, seed):
        self.server = server
        self.id_name = id_name
        self.generator: Generator = generator(seed)
        self.attribute = attribute
        self.seed = seed
        self.regions: dict[int, Chunk] = {}

    def get_block(self, x_loc: int | Location, y: int = None, z: int = None) -> Block:
        """
        获取在某位置的方块
        支持传入 Location 或者 xyz 坐标
        """
        x, y, z = decide_x_or_loc(x_loc, y, z)
        chunk = self.regions.get(x // 16)
        if 0 < y < self.attribute.MAX_BUILD_HEIGHT:
            rela_x = x % 16
            block = cast(Block, chunk.region_array[rela_x, y, z]) # 强迫症写法，为了避免烦人的IDE警报
            return block
        return AIR()

    def get_sky_light(self, x: int, y: int) -> int:
        """
        获取在某位置的天空亮度
        接受 xy 二维坐标
        """
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        light = cast(int, chunk.sky_light_array[rela_x, y])
        return light

    def get_block_light(self, x: int, y: int) -> int:
        """
        获取在某位置的方块亮度
        接受 xy 二维坐标
        """
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
        sky_light = cast(int, chunk.sky_light_array[rela_x, y])
        block_light = cast(int, chunk.block_light_array[rela_x, y])
        return max(sky_light, block_light)

    def set_block(self, block: Block, x_loc: int | Location, y: int = None, z: int = None
                  , send_packet: bool = True, block_update: bool = True):
        """
        设置某位置的方块
        :param block_update: 是否触发方块更新，默认为 True
        :param block: 指定的方块对象
        :param x_loc: 可传入 x 或 Location
        :param y: 传入Location 无需填写
        :param z: 传入Location 无需填写
        :param send_packet: 是否发送数据包，默认为 True
        :return:
        """
        x, y, z = decide_x_or_loc(x_loc, y, z)
        block.location = Location(self, x, y, z)
        chunk = self.regions.get(x // 16)
        rela_x = x % 16
        chunk.region_array[rela_x][y][z] = block
        # 重算整个区块光照
        chunk.recalculate_all_light()
        if send_packet:
            for player in self.server.players:
                if player.is_loading_position(x, y, z):
                    self.server.send_client_socket(player, chunk, "Chunk")
        if block_update:
            self.get_block(x, y + 1, z).on_update()
            self.get_block(x, y - 1, z).on_update()
            self.get_block(x + 1, y, z).on_update()
            self.get_block(x - 1, y, z).on_update()
            if z == 0:
                self.get_block(x, y, 1).on_update()
            elif z == 1:
                self.get_block(x, y, 0).on_update()

    def generate_chunk(self, rx: int):
        logging.debug(f"Generating {self.id_name} chunk {rx}")
        y_max = self.attribute.MAX_BUILD_HEIGHT
        chunk = np.full((16, y_max, 2), AIR(), dtype=Block)
        for x in range(0, 16):
            sx = x + rx * 16
            for y in range(0, y_max):
                for z in range(0, 2):
                    d_x = rx * 16 + x
                    block = self.generator.get_original_block(sx, y, z)
                    chunk[x][y][z] = block
                    block.location = Location(self, d_x, y, z)
        self.regions[rx] = Chunk(rx, chunk)

    def break_block(self, x_loc: int | Location, y: int = None, z: int = None):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        self.get_block(x, y, z).on_break()
        for player in self.server.players:
            if player.is_loading_position(x, y, z):
                self.server.send_client_socket(player, Location(self, x, y, z), "BreakBlock")
        self.set_block(AIR(), x, y, z, False)

    def is_chunk_loaded(self, x):
        return x in self.regions






