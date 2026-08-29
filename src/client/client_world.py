# Commented and arranged by ChatGPT
import logging
import math
import threading
import time
import zlib
from typing import Any, Optional, cast

import msgpack
import numpy as np

from src.client.client_entity import ClientEntity
from src.server.block_class import Block
from src.server.blocks import get_block_by_id, AIR
from src.server.location import Location, decide_x_or_loc
from src.server.biome import get_precipitation_type


class ClientWorld:
    SOUND_MAX_DISTANCE = 16.0
    SOUND_FULL_VOLUME_DISTANCE = 1.5
    SOUND_PAN_STRENGTH = 0.85

    def __init__(self, client):
        self.id_name = "null"
        self._regions: dict[int, np.ndarray[Any, np.dtype[Block]]] = {}
        self.light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]] = {}
        self.sky_light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]] = {}
        self.block_light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]] = {}
        self._light_snapshots: dict[int, tuple[Any, Any, Any]] = {}
        self.biome_map: dict[int, np.ndarray[Any, np.dtype[np.str_]]] = {}
        self.y_max = 256
        self.world_time = 0
        self.weather = "clear"
        self.weather_remaining_ticks = 0
        self.client = client
        self._render_revision = 0
        self._render_chunk_versions: dict[int, int] = {}
        self._chunk_state_lock = threading.RLock()
        self._loading_chunks: set[int] = set()
        self._chunk_load_versions: dict[int, int] = {}
        self._light_update_epochs: dict[int, int] = {}
        self._chunk_load_light_epochs: dict[int, int] = {}
        self._chunk_load_counter = 0
        self._pending_chunk_block_updates: dict[
            int, dict[tuple[int, int, int], Block]
        ] = {}
        self.entities: dict[str, ClientEntity] = {}
        self._entities_lock = threading.RLock()
        self._break_progress: dict[str, dict[str, Any]] = {}
        self._last_fluid_sound_tick = -10_000
        self._precipitation_height_cache: dict[
            tuple[int, int], tuple[int, float, bool]
        ] = {}

    def _mark_render_chunk_dirty(self, rx: int) -> None:
        self._render_revision += 1
        self._render_chunk_versions[rx] = self._render_revision

    def begin_chunk_load(self, rx: int) -> int:
        with self._chunk_state_lock:
            self._chunk_load_counter += 1
            load_version = self._chunk_load_counter
            self._chunk_load_versions[rx] = load_version
            self._chunk_load_light_epochs[rx] = self._light_update_epochs.get(rx, 0)
            self._loading_chunks.add(rx)
            return load_version

    def is_chunk_loaded(self, rx: int) -> bool:
        with self._chunk_state_lock:
            return rx in self._regions and rx not in self._loading_chunks

    def load_chunk_packet(self, packet: dict, load_version: int) -> None:
        rx = int(packet["x"])
        try:
            if int(packet.get("format", 1)) == 2:
                self._load_compact_chunk(rx, packet["payload"], load_version)
            else:
                self.load_chunk(rx, packet["region_array"], load_version)
                if "light_array" in packet:
                    self.load_lights(
                        rx,
                        packet["light_array"],
                        packet.get("sky_light_array"),
                        packet.get("block_light_array"),
                        load_version,
                    )
                if "biome_array" in packet:
                    self.load_biomes(rx, packet["biome_array"], load_version)
            callback = getattr(self.client, "on_chunk_loaded", None)
            if self.is_chunk_loaded(rx) and callable(callback):
                callback(rx)
        except Exception:
            logging.exception("Failed to decode chunk %s", rx)

    def _load_compact_chunk(
        self, rx: int, compressed: bytes, load_version: int
    ) -> None:
        data = msgpack.unpackb(zlib.decompress(compressed), raw=False)
        height = int(data["height"])
        depth = int(data["depth"])
        if height != self.y_max or depth != 2:
            raise ValueError(f"Unsupported chunk dimensions 16x{height}x{depth}")

        block_width = int(data.get("block_index_width", 1))
        block_dtype = np.uint8 if block_width == 1 else np.dtype("<u2")
        indices = np.frombuffer(data["block_indices"], dtype=block_dtype)
        expected_blocks = 16 * height * depth
        if indices.size != expected_blocks:
            raise ValueError(f"Invalid block index count: {indices.size}")

        palette = data["block_palette"]
        if indices.size and int(indices.max()) >= len(palette):
            raise ValueError("Chunk block palette index is out of range")
        chunk_array = np.full((16, height, depth), AIR(), dtype=Block)
        stride = height * depth
        for flat_index, palette_index in enumerate(indices):
            if flat_index and flat_index % 1024 == 0:
                time.sleep(0)
            block_data = palette[int(palette_index)]
            if block_data.get("id") == "air" and not block_data.get("nbt"):
                continue
            x, remainder = divmod(flat_index, stride)
            y, z = divmod(remainder, depth)
            block = get_block_by_id(block_data["id"])
            block.write_nbt(block_data.get("nbt", {}))
            block.location = Location(self, rx * 16 + x, y, z)
            chunk_array[x, y, z] = block

        sky = (
            np.frombuffer(data["sky_light"], dtype=np.uint8).reshape(16, height).copy()
        )
        block_light = (
            np.frombuffer(data["block_light"], dtype=np.uint8)
            .reshape(16, height)
            .copy()
        )
        light = np.maximum(sky, block_light)

        biome_width = int(data.get("biome_index_width", 1))
        biome_dtype = np.uint8 if biome_width == 1 else np.dtype("<u2")
        biome_indices = np.frombuffer(data["biome_indices"], dtype=biome_dtype)
        if biome_indices.size != 16 * height:
            raise ValueError(f"Invalid biome index count: {biome_indices.size}")
        biome_palette = np.asarray(data["biome_palette"], dtype="<U32")
        if biome_indices.size and int(biome_indices.max()) >= len(biome_palette):
            raise ValueError("Chunk biome palette index is out of range")
        biomes = biome_palette[biome_indices].reshape(16, height)

        with self._chunk_state_lock:
            if self._chunk_load_versions.get(rx) != load_version:
                return
            for (world_x, y, z), block in self._pending_chunk_block_updates.pop(
                rx, {}
            ).items():
                block.location = Location(self, world_x, y, z)
                chunk_array[world_x % 16, y, z] = block
            self._regions[rx] = chunk_array
            light_changed_during_load = self._light_update_epochs.get(
                rx, 0
            ) != self._chunk_load_light_epochs.get(rx, 0)
            if light_changed_during_load and all(
                rx in mapping
                for mapping in (
                    self.light_map,
                    self.sky_light_map,
                    self.block_light_map,
                )
            ):
                light = self.light_map[rx]
                sky = self.sky_light_map[rx]
                block_light = self.block_light_map[rx]
            else:
                self.light_map[rx] = light
                self.sky_light_map[rx] = sky
                self.block_light_map[rx] = block_light
            self._light_snapshots[rx] = (light, sky, block_light)
            self.biome_map[rx] = biomes
            self._loading_chunks.discard(rx)
            self._mark_render_chunk_dirty(rx)

    def load_chunk(
        self, rx: int, chunk: dict[str, dict], load_version: int | None = None
    ):
        if load_version is None:
            load_version = self.begin_chunk_load(rx)
        chunk_array = np.full((16, self.y_max, 2), AIR(), dtype=Block)
        logging.debug(f"Loading chunk {rx}")
        for key, value in chunk.items():
            x, y, z = map(int, key.split(","))
            world_x = rx * 16 + x  # 计算世界绝对坐标
            block = get_block_by_id(value["id"])
            block.write_nbt(value.get("nbt", {}))
            block.location = Location(self, world_x, y, z)  # 使用绝对坐标
            chunk_array[x][y][z] = block
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

    def load_lights(
        self,
        rx: int,
        light_map: dict[str, int],
        sky_light_map: dict[str, int] | None = None,
        block_light_map: dict[str, int] | None = None,
        load_version: int | None = None,
    ):
        light_array = np.full((16, self.y_max), 0, dtype=np.uint8)
        for key, value in light_map.items():
            x, y = key.split(",")
            x, y = int(x), int(y)
            light_array[x][y] = value
        sky_array = (
            self._dict_to_light_array(sky_light_map)
            if sky_light_map is not None
            else None
        )
        block_array = (
            self._dict_to_light_array(block_light_map)
            if block_light_map is not None
            else None
        )
        with self._chunk_state_lock:
            if (
                load_version is not None
                and self._chunk_load_versions.get(rx) != load_version
            ):
                return
            if load_version is not None and self._light_update_epochs.get(
                rx, 0
            ) != self._chunk_load_light_epochs.get(rx, 0):
                return
            self.light_map[rx] = light_array
            if sky_array is not None:
                self.sky_light_map[rx] = sky_array
            if block_array is not None:
                self.block_light_map[rx] = block_array
            self._light_snapshots[rx] = (
                self.light_map.get(rx),
                self.sky_light_map.get(rx),
                self.block_light_map.get(rx),
            )
            self._mark_render_chunk_dirty(rx)

    def update_lights(
        self,
        rx: int,
        light_map: dict[str, int],
        sky_light_map: dict[str, int] | None = None,
        block_light_map: dict[str, int] | None = None,
    ):
        """
        增量更新光照数据（只更新变化的部分）
        """
        with self._chunk_state_lock:
            previous_light = self.light_map.get(rx)
            light_array = (
                previous_light.copy()
                if previous_light is not None
                else np.zeros((16, self.y_max), dtype=np.uint8)
            )
            for key, value in light_map.items():
                x, y = key.split(",")
                light_array[int(x), int(y)] = value
            sky_array = (
                self._dict_to_light_array(sky_light_map)
                if sky_light_map is not None
                else self.sky_light_map.get(rx)
            )
            block_array = (
                self._dict_to_light_array(block_light_map)
                if block_light_map is not None
                else self.block_light_map.get(rx)
            )
            if sky_array is not None and block_array is not None:
                light_array = np.maximum(sky_array, block_array)

            self._light_update_epochs[rx] = self._light_update_epochs.get(rx, 0) + 1
            self.light_map[rx] = light_array
            if sky_array is not None:
                self.sky_light_map[rx] = sky_array
            if block_array is not None:
                self.block_light_map[rx] = block_array
            self._light_snapshots[rx] = (light_array, sky_array, block_array)
            self._mark_render_chunk_dirty(rx)

    def update_lights_compact(
        self, rx: int, height: int, sky_light: bytes, block_light: bytes
    ) -> None:
        try:
            height = int(height)
            expected = 16 * height
            if (
                height != self.y_max
                or len(sky_light) != expected
                or len(block_light) != expected
            ):
                logging.warning(
                    "Ignoring malformed compact light update for chunk %s", rx
                )
                return
            sky_array = (
                np.frombuffer(sky_light, dtype=np.uint8).reshape((16, height)).copy()
            )
            block_array = (
                np.frombuffer(block_light, dtype=np.uint8).reshape((16, height)).copy()
            )
        except (TypeError, ValueError):
            logging.warning("Ignoring malformed compact light update for chunk %s", rx)
            return

        light_array = np.maximum(sky_array, block_array)
        with self._chunk_state_lock:
            self._light_update_epochs[rx] = self._light_update_epochs.get(rx, 0) + 1
            self.light_map[rx] = light_array
            self.sky_light_map[rx] = sky_array
            self.block_light_map[rx] = block_array
            self._light_snapshots[rx] = (light_array, sky_array, block_array)
            self._mark_render_chunk_dirty(rx)

    def get_light_snapshot(self, rx: int):
        snapshot = self._light_snapshots.get(rx)
        if snapshot is not None:
            return snapshot
        return (
            self.light_map.get(rx),
            self.sky_light_map.get(rx),
            self.block_light_map.get(rx),
        )

    def _dict_to_light_array(self, light_map: dict[str, int]):
        light_array = np.full((16, self.y_max), 0, dtype=np.uint8)
        for key, value in light_map.items():
            x, y = key.split(",")
            light_array[int(x)][int(y)] = value
        return light_array

    def load_biomes(
        self, rx: int, biome_dict: dict[str, str], load_version: int | None = None
    ):
        """从服务器数据包加载整个区块的生物群系数据"""
        biome_array = np.full((16, self.y_max), "void", dtype="<U32")
        for key, biome_id in biome_dict.items():
            x_str, y_str = key.split(",")
            x, y = int(x_str), int(y_str)
            biome_array[x][y] = biome_id
        with self._chunk_state_lock:
            if (
                load_version is not None
                and self._chunk_load_versions.get(rx) != load_version
            ):
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

    def get_precipitation_type(self, x: int, y: int) -> str:
        biome_id = self.get_biome(x, max(0, min(self.y_max - 1, int(y))))
        if biome_id is None or biome_id == "void":
            return "none"
        return get_precipitation_type(biome_id, y)

    def get_precipitation_surface(
        self, x: int, z: int = 0
    ) -> tuple[float, bool] | None:
        rx = int(x) // 16
        chunk = self._regions.get(rx)
        if chunk is None:
            return None
        chunk_version = self._render_chunk_versions.get(rx, 0)
        z = 1 if int(z) else 0
        cache_key = (int(x), z)
        cached = self._precipitation_height_cache.get(cache_key)
        if cached is not None and cached[0] == chunk_version:
            return cached[1], cached[2]

        local_x = int(x) % 16
        height = 0.0
        is_water = False
        for y in range(self.y_max - 1, -1, -1):
            block = chunk[local_x, y, z]
            if block.solid:
                height = float(y + 1)
                break
            if getattr(block, "is_fluid", False):
                try:
                    fluid_ratio = float(block.fluid_height_ratio())
                except (AttributeError, TypeError, ValueError):
                    fluid_ratio = 1.0
                height = float(y) + max(0.0, min(1.0, fluid_ratio))
                is_water = getattr(block, "block_id", None) == "water"
                break
        self._precipitation_height_cache[cache_key] = (chunk_version, height, is_water)
        return height, is_water

    def get_precipitation_height(self, x: int, z: int = 0) -> float | None:
        surface = self.get_precipitation_surface(x, z)
        return None if surface is None else surface[0]

    def unload_chunk(self, x: int):
        """卸载区块，同时清理方塊、光照和生物群系数据"""
        loaded_regions = getattr(self.client, "loaded_chunk_regions", None)
        if loaded_regions is not None:
            loaded_regions.discard(int(x))
        with self._chunk_state_lock:
            self._regions.pop(x, None)
            self.light_map.pop(x, None)
            self.sky_light_map.pop(x, None)
            self.block_light_map.pop(x, None)
            self._light_snapshots.pop(x, None)
            self.biome_map.pop(x, None)
            self._loading_chunks.discard(x)
            self._chunk_load_versions.pop(x, None)
            self._light_update_epochs.pop(x, None)
            self._chunk_load_light_epochs.pop(x, None)
            self._pending_chunk_block_updates.pop(x, None)
            for world_x in range(x * 16, x * 16 + 16):
                self._precipitation_height_cache.pop((world_x, 0), None)
                self._precipitation_height_cache.pop((world_x, 1), None)
        with self._entities_lock:
            for uuid, entity in list(self.entities.items()):
                if int(entity.x // 16) == x:
                    self.entities.pop(uuid, None)
            for miner_uuid, state in list(self._break_progress.items()):
                if int(state["x"]) // 16 == x:
                    self._break_progress.pop(miner_uuid, None)
        self._mark_render_chunk_dirty(x)

    def update_entity(self, packet: dict):
        entity_uuid = str(packet.get("uuid", ""))
        if not entity_uuid:
            return
        if entity_uuid == getattr(self.client, "server_player_uuid", None):
            self.remove_entity(entity_uuid)
            return
        with self._entities_lock:
            entity = self.entities.get(entity_uuid)
            if entity is None:
                entity = ClientEntity(self.client, packet)
                self.entities[entity_uuid] = entity
            else:
                entity.apply_packet(packet)
            if (
                entity.entity_id == "player"
                and entity.breaking
                and entity.break_target is not None
            ):
                x, y, z = entity.break_target
                self._break_progress[entity_uuid] = {
                    "miner_uuid": entity_uuid,
                    "x": int(x),
                    "y": int(y),
                    "z": int(z),
                    "progress": max(0.0, min(1.0, float(entity.break_progress))),
                }
            elif entity.entity_id == "player":
                self._break_progress.pop(entity_uuid, None)

    def remove_entity(self, entity_uuid: str):
        with self._entities_lock:
            self.entities.pop(str(entity_uuid), None)
            self._break_progress.pop(str(entity_uuid), None)

    def iter_entities(self):
        with self._entities_lock:
            return list(self.entities.values())

    def update_break_progress(self, packet: dict) -> None:
        miner_uuid = str(packet.get("miner_uuid", ""))
        if not miner_uuid:
            return
        active = packet.get("active") is True
        with self._entities_lock:
            entity = self.entities.get(miner_uuid)
            if not active:
                self._break_progress.pop(miner_uuid, None)
                if entity is not None:
                    entity.breaking = False
                    entity.break_progress = 0.0
                    entity.break_target = None
                return
            try:
                x = int(packet.get("x"))
                y = int(packet.get("y"))
                z = int(packet.get("z"))
                progress = max(0.0, min(1.0, float(packet.get("progress", 0.0))))
            except (TypeError, ValueError, OverflowError):
                return
            state = {
                "miner_uuid": miner_uuid,
                "x": x,
                "y": y,
                "z": z,
                "progress": progress,
            }
            self._break_progress[miner_uuid] = state
            if entity is not None:
                entity.breaking = True
                entity.break_progress = progress
                entity.break_target = (x, y, z)

    def iter_break_progress(self) -> list[dict[str, Any]]:
        with self._entities_lock:
            return [dict(state) for state in self._break_progress.values()]

    def clear_break_progress_at(self, x: int, y: int, z: int) -> None:
        target = int(x), int(y), int(z)
        with self._entities_lock:
            for miner_uuid, state in list(self._break_progress.items()):
                if (state["x"], state["y"], state["z"]) == target:
                    self._break_progress.pop(miner_uuid, None)
                    entity = self.entities.get(miner_uuid)
                    if entity is not None:
                        entity.breaking = False
                        entity.break_progress = 0.0
                        entity.break_target = None

    def get_block(
        self, x_loc: int | Location, y: int | None = None, z: int | None = None
    ) -> Block:
        x, y, z = decide_x_or_loc(x_loc, y, z)
        x, y, z = int(x), int(y), int(z)
        if y < 0 or y >= self.y_max:
            return AIR()
        chunk = self._regions.get(x // 16)
        rela_x = x % 16
        if chunk is None:
            return AIR()
        block = cast(Block, chunk[rela_x, y, z])  # 强迫症写法，为了避免烦人的IDE警报
        return block

    def set_block(
        self,
        block: Block,
        x_loc: int | Location,
        y: int | None = None,
        z: int | None = None,
    ):
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

    def break_block(
        self, x_loc: int | Location, y: int | None = None, z: int | None = None
    ):
        """
        破坏客户端世界的方块
        :param x_loc: 可传入 x 或 Location
        :param y: 传入 Location 则不填写
        :param z: 传入 Location 则不填写
        :return:
        """
        x, y, z = decide_x_or_loc(x_loc, y, z)
        block = self.get_block(x, y, z)
        if isinstance(block, AIR):
            return
        block.on_break()
        self.play_sound(block.break_sound, block.location)
        self.set_block(AIR(), x, y, z)

    def play_sound(
        self,
        sound_id: str,
        x_loc: int | Location,
        y: int | None = None,
        z: int | None = None,
        *,
        volume: float = 1.0,
    ):
        """
        在指定坐标播放音效，根据玩家位置自动调整立体声左右平衡及距离衰减。
        """
        # 解析坐标
        x, y, z = decide_x_or_loc(x_loc, y, z)

        # 客户端实际使用 client_player；兼容旧的 client.player 引用。
        player = getattr(self.client, "client_player", None) or getattr(
            self.client, "player", None
        )
        if player is None:
            # 无玩家信息时降级为普通播放
            self.client.resources_manager.play_sound(sound_id, volume=volume)
            return

        px, py, pz = player.x, player.y, getattr(player, "z", 0.0)

        dx = x - px
        dy = y - py
        dz = z - pz
        attenuation, left_gain, right_gain = self.calculate_spatial_audio(
            dx, dy, dz
        )
        if attenuation <= 0.0:
            return

        self.client.resources_manager.play_sound(
            sound_id,
            volume=volume * attenuation,
            stereo_balance=(left_gain, right_gain),
        )

    @classmethod
    def calculate_spatial_audio(
        cls, dx: float, dy: float, dz: float
    ) -> tuple[float, float, float]:
        """返回距离衰减以及左右声道增益。"""
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance >= cls.SOUND_MAX_DISTANCE:
            return 0.0, 0.0, 0.0

        if distance <= cls.SOUND_FULL_VOLUME_DISTANCE:
            attenuation = 1.0
        else:
            audible_range = (
                cls.SOUND_MAX_DISTANCE - cls.SOUND_FULL_VOLUME_DISTANCE
            )
            remaining = (cls.SOUND_MAX_DISTANCE - distance) / audible_range
            # 平方曲线让屏幕边缘之外的声音明显变弱，同时保留近处细节。
            attenuation = max(0.0, min(1.0, remaining)) ** 2

        planar_distance = math.hypot(dx, dy)
        if planar_distance <= 1e-6:
            pan = 0.0
        else:
            # 声像取决于方向角而非横向相差格数，因此近处左右声源也能分辨。
            pan = max(-1.0, min(1.0, dx / planar_distance))
            pan *= cls.SOUND_PAN_STRENGTH

        left_gain = 1.0 - max(0.0, pan)
        right_gain = 1.0 + min(0.0, pan)
        return attenuation, left_gain, right_gain

    def tick_fluid_sounds(self) -> None:
        player = getattr(self.client, "client_player", None) or getattr(
            self.client, "player", None
        )
        if player is None:
            return
        tick = int(getattr(self.client, "client_ticks", 0))

        if tick - self._last_fluid_sound_tick < 30:
            return

        from src.server.block_class import FluidBlock

        px, py = float(player.x), float(player.y)
        pz = int(getattr(player, "z", 0))
        best = None
        for x in range(int(px) - 8, int(px) + 9):
            for y in range(max(0, int(py) - 6), min(self.y_max, int(py) + 8)):
                for z in (0, 1):
                    block = self.get_block(x, y, z)
                    if not isinstance(block, FluidBlock):
                        continue
                    sound_id = (
                        getattr(block, "source_sound", None)
                        if block.is_source
                        else getattr(block, "flowing_sound", None)
                    )
                    if not sound_id:
                        continue
                    distance = (x + 0.5 - px) ** 2 + (y + 0.5 - py) ** 2 + (z - pz) ** 2
                    if best is None or distance < best[0]:
                        best = (distance, sound_id, x + 0.5, y + 0.5, z)

        if best is None:
            return
        try:
            _, sound_id, x, y, z = best
        except (TypeError, ValueError):
            if best is None:
                return
            # 其他异常处理
            logging.warning(f"Unexpected best value: {best!r}")
            return
        self.play_sound(sound_id, x, y, z, volume=0.65)
        self._last_fluid_sound_tick = tick
