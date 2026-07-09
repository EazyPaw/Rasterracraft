import logging
import math
import threading
from typing import Any, Optional, cast
import time

import numpy as np

from resources.client.client_entity import ClientEntity
from resources.server.block_class import Block
from resources.server.blocks import get_block_by_id, AIR
from resources.server.location import Location, decide_x_or_loc


class ClientWorld:
    def __init__(self, client: 'Client'):
        self.id_name = "null"
        self._regions: dict[int, np.ndarray[Any, np.dtype[Block]]] = {}
        self.light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]] = {}
        self.sky_light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]] = {}
        self.block_light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]] = {}
        self.biome_map: dict[int, np.ndarray[Any, np.dtype[np.str_]]] = {}
        self.y_max = 256
        self.world_time = 0
        self.client = client
        self._render_revision = 0
        self._render_chunk_versions: dict[int, int] = {}
        self._chunk_state_lock = threading.RLock()
        self._loading_chunks: set[int] = set()
        self._chunk_load_versions: dict[int, int] = {}
        self._chunk_load_counter = 0
        self._pending_chunk_block_updates: dict[int, dict[tuple[int, int, int], Block]] = {}
        self.entities: dict[str, ClientEntity] = {}
        self._entities_lock = threading.RLock()

    def _mark_render_chunk_dirty(self, rx: int) -> None:
        self._render_revision += 1
        self._render_chunk_versions[rx] = self._render_revision

    def begin_chunk_load(self, rx: int) -> int:
        with self._chunk_state_lock:
            self._chunk_load_counter += 1
            load_version = self._chunk_load_counter
            self._chunk_load_versions[rx] = load_version
            self._loading_chunks.add(rx)
            return load_version

    def load_chunk(self, rx: int, chunk: dict[str, dict], load_version: int | None = None):
        if load_version is None:
            load_version = self.begin_chunk_load(rx)
        chunk_array = np.full((16, self.y_max, 2), AIR(), dtype=Block)
        logging.debug(f"Loading chunk {rx}")
        for key, value in chunk.items():
            x, y, z = map(int, key.split(","))
            world_x = rx * 16 + x  # 计算世界绝对坐标
            block = get_block_by_id(value["id"])
            block.write_nbt(value.get('nbt', {}))
            block.location = Location(self, world_x, y, z)  # 使用绝对坐标
            chunk_array[x][y][z] = block
            time.sleep(0)  # 释放GIL，让出CPU，不然会导致渲染卡顿
        with self._chunk_state_lock:
            if self._chunk_load_versions.get(rx) != load_version:
                return
            pending_updates = self._pending_chunk_block_updates.pop(rx, {})
            for (world_x, y, z), block in pending_updates.items():
                block.location = Location(self, world_x, y, z)
                chunk_array[world_x % 16, y, z] = block
            self._regions[rx] = chunk_array
            self._loading_chunks.discard(rx)
            self._mark_render_chunk_dirty(rx)

    def load_lights(self, rx: int, light_map: dict[str, int],
                    sky_light_map: dict[str, int] | None = None,
                    block_light_map: dict[str, int] | None = None,
                    load_version: int | None = None):
        light_array = np.full((16, self.y_max), 0, dtype=np.uint8)
        for key, value in light_map.items():
            x, y = key.split(",")
            x, y = int(x), int(y)
            light_array[x][y] = value
            time.sleep(0) # 同理
        sky_array = self._dict_to_light_array(sky_light_map) if sky_light_map is not None else None
        block_array = self._dict_to_light_array(block_light_map) if block_light_map is not None else None
        with self._chunk_state_lock:
            if load_version is not None and self._chunk_load_versions.get(rx) != load_version:
                return
            self.light_map[rx] = light_array
            if sky_array is not None:
                self.sky_light_map[rx] = sky_array
            if block_array is not None:
                self.block_light_map[rx] = block_array
            self._mark_render_chunk_dirty(rx)

    def update_lights(self, rx: int, light_map: dict[str, int],
                      sky_light_map: dict[str, int] | None = None,
                      block_light_map: dict[str, int] | None = None):
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
        if sky_light_map is not None:
            self.sky_light_map[rx] = self._dict_to_light_array(sky_light_map)
        if block_light_map is not None:
            self.block_light_map[rx] = self._dict_to_light_array(block_light_map)
        self._mark_render_chunk_dirty(rx)

    def _dict_to_light_array(self, light_map: dict[str, int]):
        light_array = np.full((16, self.y_max), 0, dtype=np.uint8)
        for key, value in light_map.items():
            x, y = key.split(",")
            light_array[int(x)][int(y)] = value
        return light_array

    def load_biomes(self, rx: int, biome_dict: dict[str, str], load_version: int | None = None):
        """从服务器数据包加载整个区块的生物群系数据"""
        biome_array = np.full((16, self.y_max), "void", dtype="<U32")
        for key, biome_id in biome_dict.items():
            x_str, y_str = key.split(",")
            x, y = int(x_str), int(y_str)
            biome_array[x][y] = biome_id
        with self._chunk_state_lock:
            if load_version is not None and self._chunk_load_versions.get(rx) != load_version:
                return
            self.biome_map[rx] = biome_array
            self._mark_render_chunk_dirty(rx)

    def update_biomes(self, rx: int, biome_dict: dict[str, str]):
        """增量更新生物群系数据（只更新变化的部分）"""
        if rx not in self.biome_map:
            self.biome_map[rx] = np.full((16, self.y_max), "void", dtype="<U32")

        biome_array = self.biome_map[rx]
        for key, biome_id in biome_dict.items():
            x_str, y_str = key.split(",")
            x, y = int(x_str), int(y_str)
            biome_array[x][y] = biome_id
        self._mark_render_chunk_dirty(rx)

    def get_biome(self, x: int, y: int) -> Optional[str]:
        """
        获取世界坐标 (x, y) 处的生物群系 ID。
        返回 None 表示该位置尚未加载。
        """
        if y < 0 or y >= self.y_max:
            return None
        chunk = self.biome_map.get(x // 16)
        if chunk is None:
            return None
        local_x = x % 16
        return str(chunk[local_x, y])

    def unload_chunk(self, x: int):
        """卸载区块，同时清理方塊、光照和生物群系数据"""
        with self._chunk_state_lock:
            self._regions.pop(x, None)
            self.light_map.pop(x, None)
            self.sky_light_map.pop(x, None)
            self.block_light_map.pop(x, None)
            self.biome_map.pop(x, None)
            self._loading_chunks.discard(x)
            self._chunk_load_versions.pop(x, None)
            self._pending_chunk_block_updates.pop(x, None)
        with self._entities_lock:
            for uuid, entity in list(self.entities.items()):
                if int(entity.x // 16) == x:
                    self.entities.pop(uuid, None)
        self._mark_render_chunk_dirty(x)

    def update_entity(self, packet: dict):
        entity_uuid = str(packet.get('uuid', ''))
        if not entity_uuid:
            return
        if entity_uuid == getattr(self.client, "server_player_uuid", None):
            self.remove_entity(entity_uuid)
            return
        with self._entities_lock:
            entity = self.entities.get(entity_uuid)
            if entity is None:
                self.entities[entity_uuid] = ClientEntity(self.client, packet)
            else:
                entity.apply_packet(packet)

    def remove_entity(self, entity_uuid: str):
        with self._entities_lock:
            self.entities.pop(str(entity_uuid), None)

    def iter_entities(self):
        with self._entities_lock:
            return list(self.entities.values())

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
        rx = x // 16
        with self._chunk_state_lock:
            if rx in self._loading_chunks:
                self._pending_chunk_block_updates.setdefault(rx, {})[(x, y, z)] = block
        chunk = self._regions.get(rx)
        rela_x = x % 16
        if chunk is None:
            return
        chunk[rela_x, y, z] = block
        self._mark_render_chunk_dirty(rx)

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
