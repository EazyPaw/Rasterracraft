import logging
import threading
from typing import Any
from typing import cast

import numpy as np
import resources.server.biome as biome

from resources.server.block_class import Block
from resources.server.blocks import AIR
from resources.server.generator import Generator
from resources.server.location import Location, decide_x_or_loc


class Chunk:
    def __init__(self, x, region_array: np.ndarray[Any, np.dtype[Block]]
                 , biome_array: np.ndarray[Any, np.dtype[str]]) -> None:
        self.x = x
        self.region_array = region_array
        self.biome_array = biome_array
        size = self.region_array.shape
        self.sky_light_array = np.zeros((size[0], size[1]), dtype=np.uint8)
        self.block_light_array = np.zeros((size[0], size[1]), dtype=np.uint8)
        self._recalculate_internal()   # 初始化时先进行区块内部光照计算

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
        biome_dict = {}
        for x in range(self.biome_array.shape[0]):
            for y in range(self.biome_array.shape[1]):
                biome_id = str(self.biome_array[x, y])
                biome_dict[f"{x},{y}"] = biome_id
        return {
            "__class__": "Chunk",
            "x": self.x,
            "region_array": result_dict,
            "light_array": light_dict,
            "biome_array": biome_dict
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

    def get_full_biome_dict(self) -> dict:
        """返回整个区块的生物群系字典（x,y -> biome_id）"""
        biome_dict = {}
        for x in range(self.biome_array.shape[0]):
            for y in range(self.biome_array.shape[1]):
                biome_dict[f"{x},{y}"] = str(self.biome_array[x, y])
        return biome_dict

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

    def _recalculate_internal(self):
        """仅基于本区块数据重新计算光照（不跨区块传播）"""
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

    def recalculate_all_light(self, world=None):
        """
        重新计算整个区块的天空光和方块光，支持跨区块光照传播。

        当提供 world 参数时，会构建扩展缓冲区，包含相邻区块的边缘列，
        使光照能够自然跨越区块边界传播。同时会更新相邻区块边缘列的光照值。

        :param world: World 实例，用于访问相邻区块
        :return: set[int] — 光照被修改的区块索引集合
        """
        SX, SY = self.region_array.shape[0], self.region_array.shape[1]

        # 如果没有世界引用，退化为内部计算
        if world is None:
            self._recalculate_internal()
            return {self.x}

        from resources.server.light_manager import flood_fill_light_2d

        # 清零
        self.sky_light_array.fill(0)
        self.block_light_array.fill(0)

        # 获取邻居区块
        left_chunk = world.regions.get(self.x - 1)
        right_chunk = world.regions.get(self.x + 1)

        # 追踪哪些区块的光照被更新了
        updated_chunks = {self.x}

        ext_left = 1 if left_chunk is not None else 0
        ext_right = 1 if right_chunk is not None else 0

        # 没有邻居时退化为内部计算
        if ext_left == 0 and ext_right == 0:
            self._recalculate_internal()
            return updated_chunks

        ext_sx = SX + ext_left + ext_right

        # ---- 构建扩展的方块数组（仅供读取固体/光源属性） ----
        ext_region = np.full((ext_sx, SY, 2), AIR(), dtype=Block)
        ext_region[ext_left:ext_left + SX, :, :] = self.region_array
        if left_chunk is not None:
            ext_region[0, :, :] = left_chunk.region_array[SX - 1, :, :]
        if right_chunk is not None:
            ext_region[ext_sx - 1, :, :] = right_chunk.region_array[0, :, :]

        # ---- 创建扩展的光照数组 ----
        ext_sky = np.zeros((ext_sx, SY), dtype=np.uint8)
        ext_block = np.zeros((ext_sx, SY), dtype=np.uint8)

        # ==================== 天空光 ====================
        sky_sources: list = []
        for x in range(ext_sx):
            for y in range(SY - 1, -1, -1):
                blk = cast(Block, ext_region[x, y, 0])
                if not blk.solid:
                    sky_sources.append((x, y, 15))
                else:
                    break

        # 从邻居区块引入已计算的天空光作为额外光源
        if left_chunk is not None:
            for y in range(SY):
                lvl = int(left_chunk.sky_light_array[SX - 1, y])
                if lvl > 0:
                    sky_sources.append((0, y, lvl))
        if right_chunk is not None:
            for y in range(SY):
                lvl = int(right_chunk.sky_light_array[0, y])
                if lvl > 0:
                    sky_sources.append((ext_sx - 1, y, lvl))

        if sky_sources:
            flood_fill_light_2d(ext_sky, ext_region, 0, sky_sources)

        # ==================== 方块光 ====================
        block_sources: list = []
        for x in range(ext_sx):
            for y in range(SY):
                blk0 = cast(Block, ext_region[x, y, 0])
                blk1 = cast(Block, ext_region[x, y, 1])
                light = blk0.light_source + blk1.light_source
                if light > 0:
                    block_sources.append((x, y, min(15, light)))

        # 从邻居区块引入已计算的方块光作为额外光源
        if left_chunk is not None:
            for y in range(SY):
                lvl = int(left_chunk.block_light_array[SX - 1, y])
                if lvl > 0:
                    block_sources.append((0, y, lvl))
        if right_chunk is not None:
            for y in range(SY):
                lvl = int(right_chunk.block_light_array[0, y])
                if lvl > 0:
                    block_sources.append((ext_sx - 1, y, lvl))

        if block_sources:
            flood_fill_light_2d(ext_block, ext_region, 0, block_sources)

        # ==================== 写回结果 ====================
        # 本区块
        self.sky_light_array = ext_sky[ext_left:ext_left + SX, :]
        self.block_light_array = ext_block[ext_left:ext_left + SX, :]

        # 更新邻居区块边缘列，并追踪是否有变化
        if left_chunk is not None:
            changed = False
            for y in range(SY):
                if ext_sky[0, y] > left_chunk.sky_light_array[SX - 1, y]:
                    left_chunk.sky_light_array[SX - 1, y] = ext_sky[0, y]
                    changed = True
                if ext_block[0, y] > left_chunk.block_light_array[SX - 1, y]:
                    left_chunk.block_light_array[SX - 1, y] = ext_block[0, y]
                    changed = True
            if changed:
                updated_chunks.add(self.x - 1)

        if right_chunk is not None:
            changed = False
            for y in range(SY):
                if ext_sky[ext_sx - 1, y] > right_chunk.sky_light_array[0, y]:
                    right_chunk.sky_light_array[0, y] = ext_sky[ext_sx - 1, y]
                    changed = True
                if ext_block[ext_sx - 1, y] > right_chunk.block_light_array[0, y]:
                    right_chunk.block_light_array[0, y] = ext_block[ext_sx - 1, y]
                    changed = True
            if changed:
                updated_chunks.add(self.x + 1)

        return updated_chunks



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
        self._regions_lock = threading.Lock()  # 保护 regions 字典的并发写入
        self.world_time = 0

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

    def get_biome(self, x: int, y: int) -> str:
        if y < 0 or y >= self.attribute.MAX_BUILD_HEIGHT:
            return biome.Void.biome_id
        chunk = self.regions.get(x // 16)
        if chunk is None:
            return biome.Void.biome_id
        rela_x = x % 16
        return str(chunk.biome_array[rela_x, y])

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
        # 重算整个区块光照（含跨区块传播）
        chunk.recalculate_all_light(world=self)
        if send_packet:
            for player in self.server.players:
                if player.is_loading_position(x, y, z):
                    self.server.send_client_socket(player, chunk, "Chunk")
                    # 同时为相邻区块发送光照更新
                    for neighbor_rx in (x // 16 - 1, x // 16 + 1):
                        if neighbor_rx != chunk.x and neighbor_rx in self.regions:
                            neighbor = self.regions[neighbor_rx]
                            light_update = {
                                'rx': neighbor_rx,
                                'light_array': neighbor.get_full_light_dict()
                            }
                            player.world.server.send_client_socket(player, light_update, "LightUpdate")
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
        biome_array = np.full((16, y_max), biome.Void.biome_id, dtype="<U32")
        # 第一阶段（可并行）：噪声计算生成方块和生物群系数据
        for x in range(0, 16):
            sx = x + rx * 16
            for y in range(0, y_max):
                biome_id = self.generator.get_original_biome(sx, y)
                biome_array[x, y] = biome_id
                for z in range(0, 2):
                    d_x = rx * 16 + x
                    block = self.generator.get_original_block(sx, y, z)
                    chunk[x][y][z] = block
                    block.location = Location(self, d_x, y, z)
        new_chunk = Chunk(rx, chunk, biome_array)
        # 第二阶段（临界区）：写入 regions 字典并做跨区块光照计算
        # 光照计算需要读取相邻区块，因此需要串行化以保证一致性
        with self._regions_lock:
            self.regions[rx] = new_chunk
            # 使用世界上下文重新计算光照以支持跨区块传播
            new_chunk.recalculate_all_light(world=self)
            # 新区块生成后，相邻的已加载区块也需要重新计算光照
            # （因为新区块可能在边界引入了新的光源或改变了天空光遮挡）
            for neighbor_rx in (rx - 1, rx + 1):
                neighbor = self.regions.get(neighbor_rx)
                if neighbor is not None:
                    neighbor.recalculate_all_light(world=self)

    def break_block(self, x_loc: int | Location, y: int = None, z: int = None):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        self.get_block(x, y, z).on_break()
        for player in self.server.players:
            if player.is_loading_position(x, y, z):
                self.server.send_client_socket(player, Location(self, x, y, z), "BreakBlock")
        self.set_block(AIR(), x, y, z, False)

    def is_chunk_loaded(self, x):
        return x in self.regions






