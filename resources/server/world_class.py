import logging
import math
import random
import threading
import traceback
import zlib
from typing import Any
from typing import cast
from enum import Enum

import numpy as np
import msgpack
import resources.server.biome as biome

from resources.server import save_manager
from resources.server.block_class import Block
from resources.server.blocks import AIR, FIRE, SNOW
from resources.server.damange_type import EXPLOSION, PLAYER_EXPLOSION
from resources.server.entity import Entity
from resources.server.generator import Generator
from resources.server.location import Location, Vector, decide_x_or_loc
from resources.server.particles import BlockBreakParticleEffect, Particle, get_particle_by_id


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
        """Serialize a chunk as a compressed palette packet.

        The old wire format repeated a coordinate string and a nested dict for
        every cell.  Palette indices preserve the exact block/NBT data while
        reducing both transfer size and client-side parsing work by an order of
        magnitude.  The client keeps a legacy decoder for older servers/tests.
        """
        block_palette: list[dict] = []
        block_lookup: dict[tuple, int] = {}
        block_indices: list[int] = []

        def freeze(value):
            if isinstance(value, dict):
                return tuple((key, freeze(item)) for key, item in sorted(value.items()))
            if isinstance(value, list):
                return tuple(freeze(item) for item in value)
            return value

        for value in self.region_array.flat:
            block = cast(Block, value)
            nbt = block.parse_nbt()
            key = (block.block_id, freeze(nbt))
            index = block_lookup.get(key)
            if index is None:
                index = len(block_palette)
                block_lookup[key] = index
                block_data = {"id": block.block_id}
                if nbt:
                    block_data["nbt"] = nbt
                block_palette.append(block_data)
            block_indices.append(index)

        biome_palette: list[str] = []
        biome_lookup: dict[str, int] = {}
        biome_indices: list[int] = []
        for value in self.biome_array.flat:
            biome = str(value)
            index = biome_lookup.get(biome)
            if index is None:
                index = len(biome_palette)
                biome_lookup[biome] = index
                biome_palette.append(biome)
            biome_indices.append(index)

        def pack_indices(indices: list[int]) -> tuple[int, bytes]:
            width = 1 if max(indices, default=0) < 256 else 2
            dtype = np.uint8 if width == 1 else "<u2"
            return width, np.asarray(indices, dtype=dtype).tobytes()

        block_width, packed_blocks = pack_indices(block_indices)
        biome_width, packed_biomes = pack_indices(biome_indices)
        payload = {
            "height": int(self.region_array.shape[1]),
            "depth": int(self.region_array.shape[2]),
            "block_palette": block_palette,
            "block_indices": packed_blocks,
            "block_index_width": block_width,
            "biome_palette": biome_palette,
            "biome_indices": packed_biomes,
            "biome_index_width": biome_width,
            "sky_light": self.sky_light_array.tobytes(),
            "block_light": self.block_light_array.tobytes(),
        }
        return {
            "__class__": "Chunk",
            "format": 2,
            "x": int(self.x),
            "payload": zlib.compress(msgpack.packb(payload, use_bin_type=True), level=1),
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

    def get_full_sky_light_dict(self) -> dict:
        light_dict = {}
        for x in range(self.region_array.shape[0]):
            for y in range(self.region_array.shape[1]):
                light_dict[f"{x},{y}"] = int(self.sky_light_array[x, y])
        return light_dict

    def get_full_block_light_dict(self) -> dict:
        light_dict = {}
        for x in range(self.region_array.shape[0]):
            for y in range(self.region_array.shape[1]):
                light_dict[f"{x},{y}"] = int(self.block_light_array[x, y])
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

        return world.recalculate_light_for_chunks({self.x})


class WorldAttribute:
    def __init__(self, environment = 0, max_build_height = 256):
        self.ENVIRONMENT = environment
        self.MAX_BUILD_HEIGHT = max_build_height

class Weather(Enum):
    CLEAR = "clear"
    RAIN = "rain"


class World:

    def __init__(self,server, id_name, generator, attribute: WorldAttribute, seed):
        self.server = server
        self.id_name = id_name
        self.generator: Generator = generator(seed)
        self.attribute = attribute
        self.seed = seed
        self.regions: dict[int, Chunk] = {}
        self._regions_lock = threading.Lock()  # 保护 regions 字典的并发写入
        self.dirty_chunks: set[int] = set()
        self._dirty_lock = threading.Lock()
        self.world_time = 0
        self.entities: dict[str, Entity] = {}
        self._entities_lock = threading.RLock()
        self._saved_entities_by_chunk: dict[int, list[dict]] = {}
        self.disable_mob_generation = False
        # 每次方块变动都会影响整区块光照。把同一 tick 的变动合并处理，
        # 避免重力/流体连锁时反复重算并发送相同的大型光照包。
        self._pending_light_recalc_chunks: set[int] = set()
        self._light_recalc_lock = threading.RLock()
        self._scheduled_fluid_ticks: set[tuple[int, int, int]] = set()
        self._fluid_lock = threading.RLock()
        self.random_tick_speed = 3
        self.weather: Weather = Weather.CLEAR
        self.weather_tick = self._random_weather_duration(self.weather)

    @staticmethod
    def _random_weather_duration(weather: Weather) -> int:
        # Vanilla-like ranges: precipitation lasts 10-20 minutes, while clear
        # intervals can last from 10 minutes to roughly 2.5 hours.
        if weather is Weather.RAIN:
            return random.randint(12000, 24000)
        return random.randint(12000, 180000)

    def get_weather_packet(self) -> dict:
        return {
            "__class__": "WeatherUpdate",
            "weather": self.weather.value,
            "remaining_ticks": int(self.weather_tick),
        }

    def set_weather(self, weather: Weather | str, duration_ticks: int | None = None) -> None:
        if isinstance(weather, str):
            weather = Weather(weather.lower())
        self.weather = weather
        self.weather_tick = (
            max(1, int(duration_ticks))
            if duration_ticks is not None
            else self._random_weather_duration(weather)
        )
        packet = self.get_weather_packet()
        for player in list(self.server.players):
            if player.world is self:
                self.server.send_client_socket(player, packet, "Forward")

    def tick_weather(self) -> None:
        self.weather_tick -= 1
        if self.weather_tick <= 0:
            next_weather = Weather.RAIN if self.weather is Weather.CLEAR else Weather.CLEAR
            self.set_weather(next_weather)

    def tick_random_blocks(self) -> None:
        """Run three random block selections per loaded 16³ subchunk.

        The selection is deliberately made even for ordinary blocks: a block
        can opt into random ticks simply by overriding ``on_random_tick``.
        Weather effects are checked for the selected top blocks as well, so
        snow accumulation follows the same stochastic cadence as Minecraft.
        """
        section_count = (self.attribute.MAX_BUILD_HEIGHT + 15) // 16
        for rx, chunk in list(self.regions.items()):
            for section in range(section_count):
                y_start = section * 16
                y_end = min(self.attribute.MAX_BUILD_HEIGHT, y_start + 16)
                if y_start >= y_end:
                    continue
                for _ in range(self.random_tick_speed):
                    x = rx * 16 + random.randrange(16)
                    y = random.randrange(y_start, y_end)
                    # Preserve Java's 16x16x16 selection probability even
                    # though PyCraft2D only materializes two Z layers.
                    z = random.randrange(16)
                    if z >= chunk.region_array.shape[2]:
                        continue
                    block = self.get_block(x, y, z)
                    block.on_random_tick()
                    if self.weather is Weather.RAIN and block.solid:
                        self._try_accumulate_snow(x, y, z)

    def _try_accumulate_snow(self, x: int, y: int, z: int) -> bool:
        """Attempt one random-tick snow layer on an exposed solid block."""
        if y + 1 >= self.attribute.MAX_BUILD_HEIGHT:
            return False
        above = self.get_block(x, y + 1, z)
        if not isinstance(above, AIR):
            return False
        biome_id = self.get_biome(x, y + 1)
        if biome.get_precipitation_type(biome_id, y + 1) != "snow":
            return False
        # Snowfall may create one thin layer, but random ticks never stack it
        # into deeper snow.  Existing snow therefore makes this tick a no-op.
        self.set_block(SNOW(layer=1), x, y + 1, z)
        return True


    def mark_chunk_dirty(self, rx: int):
        if getattr(self.server, "save_id", None):
            with self._dirty_lock:
                self.dirty_chunks.add(int(rx))

    def clear_chunk_dirty(self, rx: int):
        with self._dirty_lock:
            self.dirty_chunks.discard(int(rx))

    def take_dirty_chunks(self) -> list[int]:
        with self._dirty_lock:
            dirty_chunks = list(self.dirty_chunks)
            self.dirty_chunks.clear()
        return dirty_chunks

    def recalculate_light_for_chunks(self, chunk_rxs: set[int], padding: int = 1) -> set[int]:
        if not chunk_rxs:
            return set()

        min_rx = min(chunk_rxs) - padding
        max_rx = max(chunk_rxs) + padding
        loaded_rxs = sorted(rx for rx in range(min_rx, max_rx + 1) if rx in self.regions)
        if not loaded_rxs:
            return set()

        spans: list[list[int]] = []
        for rx in loaded_rxs:
            if not spans or rx != spans[-1][-1] + 1:
                spans.append([rx])
            else:
                spans[-1].append(rx)

        changed_chunks: set[int] = set()
        for span in spans:
            changed_chunks.update(self._recalculate_light_span(span))
        return changed_chunks

    def schedule_light_recalculation(self, rx: int) -> None:
        """记录一次方块变动，留待当前 tick 末尾合并更新光照。"""
        with self._light_recalc_lock:
            self._pending_light_recalc_chunks.add(int(rx))

    def flush_light_updates(self) -> set[int]:
        """重算当前 tick 累积的光照，并只同步实际变化的区块。"""
        with self._light_recalc_lock:
            if not self._pending_light_recalc_chunks:
                return set()
            pending_chunks = self._pending_light_recalc_chunks
            self._pending_light_recalc_chunks = set()

        changed_chunks = self.recalculate_light_for_chunks(pending_chunks)
        if changed_chunks:
            self.send_light_updates(changed_chunks)
        return changed_chunks

    def _recalculate_light_span(self, chunk_rxs: list[int]) -> set[int]:
        from resources.server.light_manager import flood_fill_light_2d

        if not chunk_rxs:
            return set()

        chunks = [self.regions[rx] for rx in chunk_rxs]
        chunk_width = chunks[0].region_array.shape[0]
        height = chunks[0].region_array.shape[1]
        ext_width = chunk_width * len(chunks)
        ext_region = np.empty((ext_width, height, 2), dtype=Block)

        for index, chunk in enumerate(chunks):
            start_x = index * chunk_width
            ext_region[start_x:start_x + chunk_width, :, :] = chunk.region_array

        ext_sky = np.zeros((ext_width, height), dtype=np.uint8)
        ext_block = np.zeros((ext_width, height), dtype=np.uint8)

        sky_sources: list[tuple[int, int, int]] = []
        for x in range(ext_width):
            for y in range(height - 1, -1, -1):
                blk = cast(Block, ext_region[x, y, 0])
                if not blk.solid:
                    sky_sources.append((x, y, 15))
                else:
                    break

        if sky_sources:
            flood_fill_light_2d(ext_sky, ext_region, 0, sky_sources)

        block_sources: list[tuple[int, int, int]] = []
        for x in range(ext_width):
            for y in range(height):
                blk0 = cast(Block, ext_region[x, y, 0])
                blk1 = cast(Block, ext_region[x, y, 1])
                light = blk0.light_source + blk1.light_source
                if light > 0:
                    block_sources.append((x, y, min(15, light)))

        if block_sources:
            flood_fill_light_2d(ext_block, ext_region, 0, block_sources)

        changed_chunks: set[int] = set()
        for index, chunk in enumerate(chunks):
            start_x = index * chunk_width
            new_sky = ext_sky[start_x:start_x + chunk_width, :].copy()
            new_block = ext_block[start_x:start_x + chunk_width, :].copy()

            if (
                not np.array_equal(chunk.sky_light_array, new_sky)
                or not np.array_equal(chunk.block_light_array, new_block)
            ):
                changed_chunks.add(chunk.x)

            chunk.sky_light_array = new_sky
            chunk.block_light_array = new_block

        return changed_chunks

    def send_light_updates(self, chunk_rxs: set[int], players=None):
        if players is None:
            players = self.server.players

        for player in players:
            for rx in sorted(chunk_rxs):
                chunk = self.regions.get(rx)
                if chunk is None or rx not in player.loading_regions:
                    continue
                light_update = {
                    'rx': rx,
                    'light_array': chunk.get_full_light_dict(),
                    'sky_light_array': chunk.get_full_sky_light_dict(),
                    'block_light_array': chunk.get_full_block_light_dict(),
                }
                self.server.send_client_socket(player, light_update, "LightUpdate")

    def is_position_loaded(self, x: int, y: int, z: int = 0) -> bool:
        if y < 0 or y >= self.attribute.MAX_BUILD_HEIGHT or z not in (0, 1):
            return False
        return int(x) // 16 in self.regions

    def schedule_fluid_tick(self, x_loc: int | Location, y: int = None, z: int = None):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        x, y, z = int(x), int(y), int(z)
        if not self.is_position_loaded(x, y, z):
            return
        with self._fluid_lock:
            self._scheduled_fluid_ticks.add((x, y, z))

    def schedule_fluid_around(self, x_loc: int | Location, y: int = None, z: int = None):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        x, y, z = int(x), int(y), int(z)
        for nx, ny, nz in (
            (x, y, z),
            (x + 1, y, z),
            (x - 1, y, z),
            (x, y + 1, z),
            (x, y - 1, z),
            (x, y, 1 - z),
        ):
            self.schedule_fluid_tick(nx, ny, nz)

    def schedule_chunk_fluids(self, rx: int):
        from resources.server.block_class import FluidBlock

        chunk = self.regions.get(rx)
        if chunk is None:
            return
        for local_x in range(chunk.region_array.shape[0]):
            world_x = rx * 16 + local_x
            for y in range(chunk.region_array.shape[1]):
                for z in range(chunk.region_array.shape[2]):
                    if isinstance(chunk.region_array[local_x, y, z], FluidBlock):
                        self.schedule_fluid_tick(world_x, y, z)

    def schedule_chunk_and_boundary_fluids(self, rx: int):
        for chunk_rx in (rx - 1, rx, rx + 1):
            self.schedule_chunk_fluids(chunk_rx)

    def tick_fluids(self, max_updates: int = 4096):
        from resources.server.block_class import FluidBlock

        with self._fluid_lock:
            if not self._scheduled_fluid_ticks:
                return
            positions = sorted(self._scheduled_fluid_ticks)
            self._scheduled_fluid_ticks.clear()
            if len(positions) > max_updates:
                overflow = positions[max_updates:]
                self._scheduled_fluid_ticks.update(overflow)
                positions = positions[:max_updates]

        for x, y, z in positions:
            if not self.is_position_loaded(x, y, z):
                continue
            block = self.get_block(x, y, z)
            if isinstance(block, FluidBlock):
                speed = max(1, int(getattr(block, "flow_speed_ticks", 1)))
                server_tick = int(getattr(self.server, "server_ticks", 0))
                if speed > 1 and server_tick % speed != 0:
                    self.schedule_fluid_tick(x, y, z)
                    continue
                block.tick_fluid()

    def spawn_particle(self, particle: Particle, players=None):
        if players is None:
            players = self.server.players

        for player in players:
            if player.is_loading_position(int(particle.x), int(particle.y), particle.z):
                self.server.send_client_socket(player, particle, "Particle")

    def play_particle(
        self,
        particle_id: str | type[Particle],
        x_loc: float | Location,
        y: float = None,
        z: int = None,
        *,
        count: int = 1,
        motion: tuple[float, float] = (0.0, 0.0),
        data: dict | None = None,
        players=None,
    ):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        try:
            particle_cls = get_particle_by_id(particle_id) if isinstance(particle_id, str) else particle_id
        except ValueError:
            logging.warning(f"Unknown particle ID: {particle_id}")
            return
        self.spawn_particle(
            particle_cls(
                float(x),
                float(y),
                int(z),
                count=count,
                motion=motion,
                data=data or {},
            ),
            players=players,
        )

    def spawn_entity(self, entity: Entity):
        entity.world = self
        entity.removed = False
        entity_uuid = str(entity.uuid)
        with self._entities_lock:
            self.entities[entity_uuid] = entity
        for player in self.server.players:
            if player.is_loading_position(math.floor(entity.x), math.floor(entity.y), getattr(entity, "z", 0)):
                self.server.send_client_socket(player, entity, "EntitySpawn")

    def queue_saved_entities(self, records) -> None:
        """Defer entity restore until collision data for its chunk is loaded."""
        self._saved_entities_by_chunk.clear()
        for record in records or ():
            if not isinstance(record, dict):
                continue
            try:
                rx = math.floor(float(record.get("x", 0.0))) // 16
            except (TypeError, ValueError):
                continue
            self._saved_entities_by_chunk.setdefault(rx, []).append(record)

    def _restore_entities_for_chunk(self, rx: int) -> None:
        records = self._saved_entities_by_chunk.pop(int(rx), ())
        if not records:
            return
        from resources.server.entity_registry import create_entity_from_save

        for record in records:
            entity = create_entity_from_save(record, self)
            if entity is not None and entity.health > 0:
                self.spawn_entity(entity)

    def serialize_persistent_entities(self) -> list[dict]:
        with self._entities_lock:
            entities = tuple(self.entities.values())
        records = [
            entity.to_save_data() for entity in entities
            if entity.entity_id != "player"
            and not entity.removed
            and entity.health > 0
            and bool(getattr(entity, "persistence_required", False))
        ]
        for pending in self._saved_entities_by_chunk.values():
            records.extend(dict(record) for record in pending)
        return records

    def remove_entity(self, entity: Entity | str):
        entity_uuid = str(entity.uuid) if isinstance(entity, Entity) else str(entity)
        with self._entities_lock:
            removed = self.entities.pop(entity_uuid, None)
        if removed is not None:
            removed.removed = True
            for player in self.server.players:
                self.server.send_client_socket(player, {'uuid': entity_uuid}, "EntityRemove")

    def update_entities(self):
        with self._entities_lock:
            entities = list(self.entities.values())
        for entity in entities:
            if entity.removed:
                continue
            entity.update()
            if entity.removed:
                continue
            for player in self.server.players:
                if player.is_loading_position(math.floor(entity.x), math.floor(entity.y), getattr(entity, "z", 0)):
                    self.server.send_client_socket(player, entity, "EntityUpdate")

    def send_entities_in_chunk_to_player(self, player, rx: int):
        with self._entities_lock:
            entities = list(self.entities.values())
        for entity in entities:
            if math.floor(entity.x) // 16 == rx:
                self.server.send_client_socket(player, entity, "EntitySpawn")

    def get_block(self, x_loc: int | Location, y: int = None, z: int = None) -> Block:
        """
        获取在某位置的方块
        支持传入 Location 或者 xyz 坐标
        """
        x, y, z = decide_x_or_loc(x_loc, y, z)
        x, y, z = int(x), int(y), int(z)
        chunk = self.regions.get(x // 16)
        if 0 <= y < self.attribute.MAX_BUILD_HEIGHT and z in (0, 1) and chunk is not None:
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
        x, y, z = int(x), int(y), int(z)
        if y < 0 or y >= self.attribute.MAX_BUILD_HEIGHT or z not in (0, 1):
            return set()
        placed_block = block
        block.location = Location(self, x, y, z)
        chunk = self.regions.get(x // 16)
        if chunk is None:
            return set()
        rela_x = x % 16
        old_block = cast(Block, chunk.region_array[rela_x][y][z])
        chunk.region_array[rela_x][y][z] = block
        self.mark_chunk_dirty(chunk.x)
        self.schedule_fluid_around(x, y, z)
        self.schedule_light_recalculation(chunk.x)
        if send_packet:
            for player in self.server.players:
                if player.is_loading_position(x, y, z):
                    self.server.send_client_socket(player, block, "BlockUpdate")
        if block_update:
            # 收集需要触发 on_update 的邻居坐标
            neighbors = [
                (x, y + 1, z),
                (x, y - 1, z),
                (x + 1, y, z),
                (x - 1, y, z),
            ]
            if z == 0:
                neighbors.append((x, y, 1))
            elif z == 1:
                neighbors.append((x, y, 0))

            for nx, ny, nz in neighbors:
                neighbor_block = self.get_block(nx, ny, nz)
                old_nbt = neighbor_block.parse_nbt()  # 更新前快照
                neighbor_block.on_update()
                new_nbt = neighbor_block.parse_nbt()  # 更新后快照

                # 若方块属性确实发生了变化，向加载了该位置的客户端发送单方块更新
                if old_nbt != new_nbt:
                    self.mark_chunk_dirty(nx // 16)
                    for player in self.server.players:
                        if player.is_loading_position(nx, ny, nz):
                            self.server.send_client_socket(player, neighbor_block, "BlockUpdate")
        if getattr(old_block, "is_fluid", False) or getattr(placed_block, "is_fluid", False):
            self.schedule_fluid_around(x, y, z)

        return set()

    def generate_chunk(self, rx: int):
        save_id = getattr(self.server, "save_id", None)
        if save_manager.chunk_exists(save_id, self.id_name, rx):
            logging.debug(f"Loading saved {self.id_name} chunk {rx}")
            try:
                saved_chunk = save_manager.load_chunk(save_id, self.id_name, rx, self)
            except Exception as e:
                logging.error(f"Failed to load saved chunk {self.id_name}:{rx}: {e}")
                logging.error(traceback.format_exc())
                saved_chunk = None
            if saved_chunk is not None:
                with self._regions_lock:
                    if rx in self.regions:
                        return {rx}
                    self.regions[rx] = saved_chunk
                    self._initialize_chunk_blocks(saved_chunk)
                    self.mark_chunk_dirty(rx)
                    changed = self.recalculate_light_for_chunks({rx})
                    self.schedule_chunk_and_boundary_fluids(rx)
                    self._restore_entities_for_chunk(rx)
                    return changed

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
            self._initialize_chunk_blocks(new_chunk)
            self.mark_chunk_dirty(rx)
            # 使用世界上下文重新计算光照以支持跨区块传播
            changed = self.recalculate_light_for_chunks({rx})
            self.schedule_chunk_and_boundary_fluids(rx)
            self._restore_entities_for_chunk(rx)
            from resources.server.entity_spawning import spawn_animals_for_chunk
            spawn_animals_for_chunk(self, rx)
            return changed

    def _initialize_chunk_blocks(self, chunk: Chunk) -> None:
        """运行区块恢复后的方块初始化钩子。

        普通方块没有这个钩子，因此不会增加加载成本；需要持续效果的
        方块（例如火把）可以在这里恢复定时器，而不依赖玩家重新放置。
        """
        for block in chunk.region_array.flat:
            on_load = getattr(block, "on_load", None)
            if callable(on_load):
                on_load()

    def break_block(self, x_loc: int | Location, y: int = None, z: int = None,
                    tool=None, *, explosion_power: float | None = None):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        block = self.get_block(x, y, z)
        if isinstance(block, AIR):
            return 0
        location = Location(self, x, y, z)
        self.spawn_particle(BlockBreakParticleEffect(block, location, count=18))
        block.on_break()
        # Drops exist in the world first; they are never placed directly into
        # the miner's inventory.
        drops = (
            block.get_drops(tool)
            if explosion_power is None
            else block.get_explosion_drops()
        )
        drop_chance = (
            1.0
            if explosion_power is None
            else min(1.0, 1.0 / max(1.0, float(explosion_power)))
        )
        for stack in drops:
            if random.random() > drop_chance:
                continue
            from resources.server.entities.item import Item
            self.spawn_entity(Item(x + 0.5, y + 0.45, self, stack, z))
        experience = block.get_experience(tool)
        for player in self.server.players:
            if player.is_loading_position(x, y, z):
                self.server.send_client_socket(player, location, "BreakBlock")
        self.set_block(AIR(), x, y, z, False)
        return experience

    def is_chunk_loaded(self, x):
        return x in self.regions

    def find_top_block(self, x, z) -> Block | None:
        for y in range(self.attribute.MAX_BUILD_HEIGHT - 1, 0, -1):
            if (block := self.get_block(x, y, z)).block_id != "air":
                return block
        return None

    @staticmethod
    def _explosion_directions() -> tuple[tuple[float, float, float], ...]:
        """Return Minecraft's 1,352 normalized rays from a 16-cube shell."""
        directions = []
        shell_max = 15
        for ix in range(16):
            for iy in range(16):
                for iz in range(16):
                    if ix not in (0, shell_max) and iy not in (0, shell_max) \
                            and iz not in (0, shell_max):
                        continue
                    dx = ix / shell_max * 2.0 - 1.0
                    dy = iy / shell_max * 2.0 - 1.0
                    dz = iz / shell_max * 2.0 - 1.0
                    length = math.sqrt(dx * dx + dy * dy + dz * dz)
                    directions.append((dx / length, dy / length, dz / length))
        return tuple(directions)

    def _collect_explosion_blocks(self, x: float, y: float, z: int,
                                  power: float) -> set[tuple[int, int, int]]:
        """Ray-march blast energy through the two-layer block world."""
        affected: set[tuple[int, int, int]] = set()
        center_z = int(z) + 0.5
        for dx, dy, dz in self._explosion_directions():
            strength = float(power) * random.uniform(0.7, 1.3)
            px, py, pz = x, y, center_z
            while strength > 0.0:
                bx, by, bz = math.floor(px), math.floor(py), math.floor(pz)
                if 0 <= by < self.attribute.MAX_BUILD_HEIGHT and bz in (0, 1):
                    block = self.get_block(bx, by, bz)
                    if not isinstance(block, AIR):
                        resistance = max(0.0, float(getattr(block, "blast_resistance", 0.0)))
                        strength -= (resistance + 0.3) * 0.3
                    if strength > 0.0:
                        affected.add((bx, by, bz))
                px += dx * 0.3
                py += dy * 0.3
                pz += dz * 0.3
                strength -= 0.225
        return affected

    def _explosion_ray_clear(self, start: tuple[float, float, float],
                             end: tuple[float, float, float]) -> bool:
        dx, dy, dz = (end[index] - start[index] for index in range(3))
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        steps = max(1, math.ceil(distance / 0.2))
        for step in range(1, steps):
            amount = step / steps
            px = start[0] + dx * amount
            py = start[1] + dy * amount
            pz = start[2] + dz * amount
            bx, by, bz = math.floor(px), math.floor(py), math.floor(pz)
            if bz not in (0, 1) or not (0 <= by < self.attribute.MAX_BUILD_HEIGHT):
                continue
            block = self.get_block(bx, by, bz)
            shape = block.get_collision_box()
            local_x, local_y = px - bx, py - by
            if any(
                box.min_x <= local_x <= box.max_x
                and box.min_y <= local_y <= box.max_y
                for box in shape
            ):
                return False
        return True

    def _explosion_exposure(self, entity, center: tuple[float, float, float]) -> float:
        width = max(0.01, float(getattr(entity, "width", 1.0)))
        height = max(0.01, float(getattr(entity, "height", 1.0)))
        x_samples = max(2, math.floor(width * 2.0) + 1)
        y_samples = max(2, math.floor(height * 2.0) + 1)
        visible = 0
        total = x_samples * y_samples
        for ix in range(x_samples):
            sample_x = entity.x + width * ((ix + 0.5) / x_samples)
            for iy in range(y_samples):
                sample_y = entity.y + height * ((iy + 0.5) / y_samples)
                sample = (sample_x, sample_y, int(getattr(entity, "z", 0)) + 0.5)
                if self._explosion_ray_clear(center, sample):
                    visible += 1
        return visible / total

    def _damage_entities_from_explosion(self, center: tuple[float, float, float],
                                        power: float, source=None) -> None:
        radius = power * 2.0
        if radius <= 0:
            return
        candidates = list(self.entities.values())
        candidates.extend(getattr(self.server, "players", ()))
        seen: set[str] = set()
        for entity in candidates:
            entity_key = str(getattr(entity, "uuid", id(entity)))
            if entity_key in seen or getattr(entity, "removed", False):
                continue
            seen.add(entity_key)
            entity_x = float(entity.x) + float(getattr(entity, "width", 1.0)) * 0.5
            entity_y = float(entity.y) + float(getattr(entity, "height", 1.0)) * 0.5
            entity_z = int(getattr(entity, "z", 0)) + 0.5
            delta_x = entity_x - center[0]
            delta_y = entity_y - center[1]
            delta_z = entity_z - center[2]
            distance = math.sqrt(delta_x * delta_x + delta_y * delta_y + delta_z * delta_z)
            if distance > radius:
                continue
            exposure = self._explosion_exposure(entity, center)
            impact = (1.0 - distance / radius) * exposure
            if impact <= 0.0:
                continue
            damage = math.floor(7.0 * (impact * impact + impact) * power + 1.0)
            horizontal_length = math.hypot(delta_x, delta_y)
            if horizontal_length < 1.0e-8:
                knockback = Vector(0.0, impact)
            else:
                knockback = Vector(
                    delta_x / horizontal_length * impact,
                    delta_y / horizontal_length * impact,
                )

            damage_type = (
                PLAYER_EXPLOSION
                if getattr(source, "entity_id", None) == "player"
                else EXPLOSION
            )
            apply_damage = getattr(entity, "apply_damage", None)
            actual_damage = 0.0
            if callable(apply_damage):
                actual_damage = apply_damage(
                    damage,
                    damage_type,
                    source=source,
                    knockback=knockback,
                )
            if actual_damage <= 0.0:
                # Explosion impulse is independent of damage immunity.  This
                # also lets primed TNT and creative players be pushed.
                apply_knockback = getattr(entity, "apply_knockback", None)
                if callable(apply_knockback):
                    apply_knockback(knockback)
                if entity in getattr(self.server, "players", ()):
                    self.server.send_client_socket(entity, {
                        "__class__": "PlayerVelocity",
                        "motion": {
                            "x": float(entity.motion.x),
                            "y": float(entity.motion.y),
                        },
                    }, "Forward")

    def _ignite_explosion_fires(self, affected: set[tuple[int, int, int]]) -> None:
        positions = list(affected)
        random.shuffle(positions)
        for x, y, z in positions:
            if random.randrange(3) != 0 or y <= 0:
                continue
            if not isinstance(self.get_block(x, y, z), AIR):
                continue
            support = self.get_block(x, y - 1, z)
            if support.has_collision_box():
                self.set_block(FIRE(), x, y, z)

    def spawn_explosion(self, loc, power=4, break_block=True, catch_fire=False,
                        source=None):
        """Create a Minecraft-style ray-marched explosion.

        Entity exposure is measured before blocks are removed, then affected
        blocks run their polymorphic explosion hook.  This is what allows TNT
        to turn into a short-fuse entity instead of dropping as an item.
        """
        x, y, z = decide_x_or_loc(loc)
        power = max(0.0, float(power))
        z = int(z)
        if power <= 0.0 or z not in (0, 1):
            return set()

        affected = self._collect_explosion_blocks(float(x), float(y), z, power)
        center = (float(x), float(y), z + 0.5)
        self._damage_entities_from_explosion(center, power, source=source)

        if break_block:
            positions = list(affected)
            random.shuffle(positions)
            for bx, by, bz in positions:
                block = self.get_block(bx, by, bz)
                if isinstance(block, AIR):
                    continue
                if block.on_exploded(power, source=source):
                    self.break_block(
                        bx, by, bz,
                        explosion_power=power,
                    )

        if catch_fire:
            self._ignite_explosion_fires(affected)

        self.play_particle(
            (
                "minecraft:explosion_emitter"
                if power >= 2.0 and break_block
                else "minecraft:explosion"
            ),
            float(x), float(y), z,
            data={"power": power},
        )
        self.server.broadcast_sound("random.explode", float(x), float(y), z)
        return affected






