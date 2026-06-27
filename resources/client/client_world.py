import logging
import math
from typing import Any, cast

import numpy as np

from resources.server.block_class import Block
from resources.server.blocks import get_block_by_id, AIR
from resources.server.location import Location, decide_x_or_loc


class ClientWorld:
    def __init__(self, client: 'Client'):
        self.id_name = "null"
        self._regions: dict[int, np.ndarray[Any, np.dtype[Block]]] = {}
        self.light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]] = {}
        self.y_max = 256
        self.client = client

    def load_chunk(self, rx: int, chunk: dict[str, dict]):
        chunk_array = np.full((16, self.y_max, 2), AIR(), dtype=Block)
        logging.debug(f"Loading chunk {rx}")
        for key, value in chunk.items():
            x, y, z = map(int, key.split(","))
            world_x = rx * 16 + x  # 计算世界绝对坐标
            block = get_block_by_id(value["id"])
            block.write_nbt(value['nbt'])
            block.location = Location(self, world_x, y, z)  # 使用绝对坐标
            chunk_array[x][y][z] = block
        self._regions[rx] = chunk_array

    def load_lights(self, rx: int, light_map: dict[str, int]):
        light_array = np.full((16, self.y_max), 0, dtype=np.uint8)
        for key, value in light_map.items():
            x, y = key.split(",")
            x, y = int(x), int(y)
            light_array[x][y] = value
        self.light_map[rx] = light_array

    def update_lights(self, rx: int, light_map: dict[str, int]):
        """
        增量更新光照数据（只更新变化的部分）
        """
        # 如果该区块的光照数组不存在，先创建
        if rx not in self.light_map:
            self.light_map[rx] = np.full((16, self.y_max), 0, dtype=np.uint8)
        
        light_array = self.light_map[rx]
        for key, value in light_map.items():
            x, y = key.split(",")
            x, y = int(x), int(y)
            light_array[x][y] = value

    def unload_chunk(self, x: int):
        del self._regions[x]

    def get_block(self, x_loc: int | Location, y: int | None = None, z: int | None = None) -> Block:
        x, y, z = decide_x_or_loc(x_loc, y, z)
        x, y, z = int(x), int(y), int(z)
        if y < 0 or y >= self.y_max:
            return AIR()
        chunk = self._regions.get(x // 16)
        rela_x = x % 16
        if chunk is None:
            return AIR()
        block = cast(Block, chunk[rela_x, y, z]) # 强迫症写法，为了避免烦人的IDE警报
        return block

    def set_block(self, block: Block, x_loc: int | Location, y: int | None = None, z: int | None = None):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        block.location = Location(self, x, y, z)
        chunk = self._regions.get(x // 16)
        rela_x = x % 16
        if chunk is None:return
        chunk[rela_x, y, z] = block

    def break_block(self,x_loc: int | Location, y: int | None = None, z: int | None = None):
        """
        破坏客户端世界的方块
        :param x_loc: 可传入 x 或 Location
        :param y: 传入 Location 则不填写
        :param z: 传入 Location 则不填写
        :return:
        """
        x, y, z = decide_x_or_loc(x_loc, y, z)
        block = self.get_block(x, y, z)
        if isinstance(block, AIR): return
        block.on_break()
        self.play_sound(block.break_sound, block.location)
        self.set_block(AIR(), x, y, z)

    def play_sound(self, sound_id: str, x_loc: int | Location, y: int | None = None, z: int | None = None):
        """
        在指定坐标播放音效，根据玩家位置自动调整立体声左右平衡及距离衰减。
        """
        # 解析坐标
        x, y, z = decide_x_or_loc(x_loc, y, z)

        # 获取玩家位置（假设 client 有 player 对象，且 player 有 x, y, z 属性）
        player = getattr(self.client, 'player', None)
        if player is None:
            # 无玩家信息时降级为普通播放
            self.client.resources_manager.play_sound(sound_id)
            return

        px, py, pz = player.x, player.y, player.z

        # 计算相对位置
        dx = x - px
        dy = y - py
        dz = z - pz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        max_dist = 16.0          # 最大可听距离（可根据需要调整）
        max_pan_range = 10.0     # 立体声完全偏到一侧的水平距离

        if dist > max_dist:
            return               # 太远，不播放

        # 距离衰减因子（线性衰减）
        vol_factor = max(0.0, 1.0 - dist / max_dist)

        # 立体声左右平衡计算（基于水平偏移 dx）
        # pan 范围 [-1, 1]，-1 完全左声道，1 完全右声道
        pan = max(-1.0, min(1.0, dx / max_pan_range))
        left_vol = vol_factor * (1.0 - pan) / 2.0
        right_vol = vol_factor * (1.0 + pan) / 2.0

        # 调用资源管理器播放立体声音效
        self.client.resources_manager.play_sound(
            sound_id,
            stereo_balance=(left_vol, right_vol)
        )