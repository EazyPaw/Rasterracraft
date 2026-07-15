from abc import ABC

import os
import ast
import logging

from resources.server.utils import is_safe_value, client_method, server_method

if os.environ.get('PYCRAFT_CLIENT') == '1':
    import pygame

from resources.server.location import Location
from resources.server.tags import BlockTag


BLOCK_EXPERIENCE = {
    "coal_ore": (0, 2), "diamond_ore": (3, 7), "emerald_ore": (3, 7),
    "lapis_ore": (2, 5), "redstone_ore": (1, 5),
}


class Block(ABC):
    block_id = None
    name = None
    _texture_path = None          # 图片文件路径
    _texture = None      # 原始 Surface（懒加载）
    _last_scaled = -1
    _last_tex_id = -1    # 用于检测动画帧变化（id(tex)）
    solid = True

    # 方块属性
    hardness = 1.5
    blast_resistance = 0.5
    friction = 0.6
    speed_factor = 1.0
    jump_factor = 1.0
    bounce_restitution = 0
    replaceable = False
    flame_odds = 0
    burn_odds = 0
    lava_flammable = False
    suffocating = True
    redstone_conducting = True

    preferred_tool = None
    requires_correct_tool = False
    required_tool_tier = "wood"
    break_sound = 'dig.stone'
    place_sound = None    # 放置时播放的音效，默认 None 与 break_sound 一样
    breakable = True
    light_attenuation = 5
    light_source = 0
    Tags = []
    has_transparent_pixels = None  # None = 自动从纹理检测，也可手动覆盖为 True/False

    def __init__(self, nbt = None):
        # 方块应该带有的属性
        self.location = None
        if self.place_sound is None:
            self.place_sound = self.break_sound
        if nbt:
            self.write_nbt(nbt)

    @classmethod
    @client_method
    def get_texture(cls, size, client = None):
        """
        返回方块的材质 (client 参数由 @client_only 自动注入)
        :param size:
        :param client:
        :return:
        """
        size = max(1, int(round(size)))

        # 每帧都调用 get_texture_img：静态纹理返回缓存的同一 Surface（id 不变），
        # 动画纹理每帧返回不同的 frame subsurface（id 不同）
        tex = client.resources_manager.get_texture_img(cls._texture_path)
        if tex is None:
            return cls._texture

        # 首次加载纹理时自动检测是否存在透明像素
        if cls.has_transparent_pixels is None:
            cls.has_transparent_pixels = client.resources_manager.has_transparent_pixels(tex)

        # 使用 tex 的 id 作为帧标识：静态纹理 id 不变跳过缩放，动画纹理 id 变化则重新缩放
        if id(tex) != cls._last_tex_id or size != cls._last_scaled:
            cls._texture = pygame.transform.scale(tex, (size, size))
            cls._last_scaled = size
            cls._last_tex_id = id(tex)
        return cls._texture

    def get_safe_attributes(self):
        """
        获取当前实例的所有安全属性，返回一个字典。
        """
        safe_data = {}
        # 使用 vars(self) 获取实例变量（适用于普通类，不处理 __slots__）
        for key, value in vars(self).items():
            if is_safe_value(value):
                safe_data[key] = value
        return safe_data

    def parse_nbt(self) -> dict:
        nbt = self.get_safe_attributes()
        return nbt

    def write_nbt(self, nbt: str | dict):
        if isinstance(nbt, str):
            nbt = ast.literal_eval(nbt)
        for key, value in nbt.items():
            if hasattr(self, key):
                current_attr = getattr(self, key)
                current_type = type(current_attr)
                if type(value) is current_type:  # 严格类型相等
                    setattr(self, key, value)
                else:
                    logging.warning(
                        f"There exists a incorrect type nbt, expect {type(current_attr)}, but got {type(value)}.")
            else:
                logging.warning(f"Block {self.block_id} has no attribute {key}.")

    def place_at(self, location: Location) -> bool:
        """
        在指定位置放置该方块对象，返回是否放置成功
        :param location:
        :return:
        """
        if location.world.get_block(location).replaceable:
            location.world.set_block(self, location)
            return True
        return False

    def on_generate(self):
        """
        当方块在被生成时执行的操作
        :return:
        """
        pass

    def on_break(self):
        pass

    def can_harvest(self, material) -> bool:
        if not self.requires_correct_tool:
            return True
        tiers = {"wood": 0, "stone": 1, "iron": 2, "diamond": 3, "netherite": 4}
        return (
            getattr(material, "tool_type", None) == self.preferred_tool
            and tiers.get(getattr(material, "tier", ""), -1) >= tiers.get(self.required_tool_tier, 0)
        )

    def get_drops(self, material):
        """Base loot until specialised loot tables/functions are implemented."""
        if not self.can_harvest(material):
            return []
        from resources.server.item_class import ItemStack
        from resources.server.materials import get_block_item
        return [ItemStack(get_block_item(self), 1)]

    def get_experience(self, material) -> int:
        if not self.can_harvest(material):
            return 0
        import random
        bounds = BLOCK_EXPERIENCE.get(self.block_id)
        return random.randint(*bounds) if bounds else 0

    def on_right_click(self) -> bool:
        """
        执行方块被右键交互时的操作，返回方块交互是否成功（如果方块不可交互则始终返回 False ）
        :return:
        """
        return False # 返回此方块能否被交互

    def on_left_click(self):
        pass

    def on_update(self):
        pass

    def to_dict(self):
        rst = {
            'id': self.block_id,
        }
        if nbt := self.parse_nbt():
            rst['nbt'] = nbt
        return rst

    def on_random_tick(self):
        pass


class FluidBlock(Block):
    solid = False
    replaceable = True
    light_attenuation = 1
    has_transparent_pixels = True
    is_fluid = True

    _flow_texture_path = None
    # water_flow frames are 32x32: one frame spans a 2x2 block area.
    flow_texture_tile_span = 2
    _texture_cache = {}
    max_level = 7
    source_level = 0
    flow_speed_ticks = 5
    can_create_source = True
    source_surface_pixels = 14
    flowing_surface_step_pixels = 2
    horizontal_flow_range = 5

    def __init__(self, level: int = 0, falling: bool = False, flow_direction: int = 0, nbt=None):
        self.level = max(0, min(self.max_level, int(level)))
        self.falling = bool(falling)
        self.flow_direction = -1 if flow_direction < 0 else (1 if flow_direction > 0 else 0)
        super().__init__(nbt)

    @property
    def is_source(self) -> bool:
        return self.level == self.source_level and not self.falling

    def is_same_fluid(self, block: Block) -> bool:
        return type(block) is type(self)

    def make_fluid(self, level: int, falling: bool = False, flow_direction: int = 0):
        return type(self)(level, falling, flow_direction)

    def get_texture_path(self) -> str:
        if self.falling or self.level > self.source_level or self.flow_direction != 0:
            return self._flow_texture_path or self._texture_path
        if self.location is not None and not self._has_same_fluid_above():
            left_ratio, right_ratio = self.get_surface_edge_ratios()
            if abs(left_ratio - right_ratio) > 0.001:
                return self._flow_texture_path or self._texture_path
        return self._texture_path

    def _has_same_fluid_above(self) -> bool:
        if self.location is None:
            return False
        above = self.location.world.get_block(self.location.add(0, 1, 0))
        return self.is_same_fluid(above)

    def fluid_height_ratio(self) -> float:
        if self.location is None:
            return 1.0
        if self._has_same_fluid_above() or self.falling:
            return 1.0
        pixels = self.source_surface_pixels - self.level * self.flowing_surface_step_pixels
        return max(1.0 / 16.0, min(1.0, pixels / 16.0))

    def water_height_ratio(self) -> float:
        return self.fluid_height_ratio()

    def get_surface_edge_ratios(self) -> tuple[float, float]:
        own = self.fluid_height_ratio()
        if self.location is None or self._has_same_fluid_above() or self.falling:
            return own, own

        world = self.location.world
        x = int(self.location.x)
        y = int(self.location.y)
        z = int(self.location.z)
        edges = []
        for direction in (-1, 1):
            neighbor = world.get_block(x + direction, y, z)
            if self.is_same_fluid(neighbor):
                edges.append((own + neighbor.fluid_height_ratio()) * 0.5)
            else:
                edges.append(own)
        return edges[0], edges[1]

    @client_method
    def get_texture(self, size, client=None):
        size = max(1, int(round(size)))
        texture_path = self.get_texture_path()
        base_texture = client.resources_manager.get_texture_img(texture_path)
        if base_texture is None:
            return None

        left_ratio, right_ratio = self.get_surface_edge_ratios()
        left_h = max(1, min(size, int(round(size * left_ratio))))
        right_h = max(1, min(size, int(round(size * right_ratio))))
        tex_h = max(left_h, right_h)

        is_flow_texture = bool(
            self._flow_texture_path and texture_path == self._flow_texture_path
        )
        tile_span = self.flow_texture_tile_span if is_flow_texture else 1
        tile_span = max(1, int(tile_span))
        if self.location is None or tile_span == 1:
            phase_x = phase_y = 0
        else:
            world_x = int(self.location.x)
            world_y = int(self.location.y)
            phase_x = world_x % tile_span
            # World Y grows upward while image rows grow downward.
            phase_y = (-world_y - 1) % tile_span

        cache_key = (
            texture_path,
            base_texture,
            size,
            left_h,
            right_h,
            self.flow_direction,
            tile_span,
            phase_x,
            phase_y,
        )
        if cache_key in self._texture_cache:
            return self._texture_cache[cache_key]

        atlas_size = size * tile_span
        scaled = pygame.transform.scale(
            base_texture, (atlas_size, atlas_size)
        ).convert_alpha()
        if self.flow_direction < 0:
            scaled = pygame.transform.flip(scaled, True, False)

        tile = scaled.subsurface(
            pygame.Rect(phase_x * size, phase_y * size, size, size)
        )
        texture = tile.subsurface(
            pygame.Rect(0, size - tex_h, size, tex_h)
        ).copy()
        if left_h != right_h:
            denom = max(1, size - 1)
            for px in range(size):
                t = px / denom
                column_h = int(round(left_h + (right_h - left_h) * t))
                clear_h = tex_h - max(1, min(tex_h, column_h))
                if clear_h > 0:
                    texture.fill((0, 0, 0, 0), (px, 0, 1, clear_h))

        self._texture_cache[cache_key] = texture
        if len(self._texture_cache) > 512:
            self._texture_cache.pop(next(iter(self._texture_cache)))
        return texture

    def on_update(self):
        if self.location is not None and hasattr(self.location.world, "schedule_fluid_tick"):
            self.location.world.schedule_fluid_tick(self.location)

    def tick_fluid(self):
        if self.location is None:
            return

        world = self.location.world
        x = int(self.location.x)
        y = int(self.location.y)
        z = int(self.location.z)

        if not self.is_source:
            source_level = self._get_new_source_level(world, x, y, z)
            if source_level is not None:
                self._replace_self(self.make_fluid(source_level, False, 0))
                return

            support = self._get_supporting_flow(world, x, y, z)
            if support is None:
                from resources.server.blocks import AIR
                world.set_block(AIR(), self.location, send_packet=True, block_update=True)
                return

            target_level, target_falling, target_direction = support
            if (
                target_level != self.level
                or target_falling != self.falling
                or target_direction != self.flow_direction
            ):
                self._replace_self(self.make_fluid(target_level, target_falling, target_direction))
                return

        flowed_down = self._try_flow_to(world, x, y - 1, z, self.source_level, True, 0)
        if flowed_down:
            self._set_own_direction(0)
            if not self.is_source:
                return
        if self.falling and self.is_same_fluid(world.get_block(x, y - 1, z)):
            self._set_own_direction(0)
            return
        below = world.get_block(x, y - 1, z)
        if (
            not self.is_source
            and not self.falling
            and self.is_same_fluid(below)
            and below.falling
        ):
            self._set_own_direction(0)
            return

        if self.level >= self.max_level:
            return

        flow_dirs = self._get_horizontal_flow_directions(world, x, y, z)
        visible_dirs = [direction for _, _, direction in flow_dirs if direction != 0]
        self._set_own_direction(visible_dirs[0] if len(visible_dirs) == 1 and len(flow_dirs) == 1 else 0)
        for dx, dz, direction in flow_dirs:
            self._try_flow_to(world, x + dx, y, z + dz, self.level + 1, False, direction)

    def get_flow_vector(self) -> tuple[float, float]:
        horizontal = float(self.flow_direction)
        vertical = -1.0 if self.falling else 0.0
        if horizontal == 0.0 and vertical == 0.0 and self.location is not None:
            left_ratio, right_ratio = self.get_surface_edge_ratios()
            if left_ratio > right_ratio + 0.001:
                horizontal = 1.0
            elif right_ratio > left_ratio + 0.001:
                horizontal = -1.0

        if horizontal == 0.0 and vertical == 0.0 and self.location is not None:
            x = int(self.location.x)
            y = int(self.location.y)
            z = int(self.location.z)
            for dx, dz, direction in self._iter_horizontal_neighbors(z):
                if direction == 0:
                    continue
                neighbor = self.location.world.get_block(x + dx, y, z + dz)
                if self.is_same_fluid(neighbor) and neighbor.level < self.level:
                    horizontal -= direction
        return horizontal, vertical

    def _replace_self(self, fluid: 'FluidBlock'):
        self.location.world.set_block(fluid, self.location, send_packet=True, block_update=True)

    def _set_own_direction(self, direction: int):
        direction = -1 if direction < 0 else (1 if direction > 0 else 0)
        if self.flow_direction == direction:
            return
        self.flow_direction = direction
        world = self.location.world
        world.mark_chunk_dirty(int(self.location.x) // 16)
        for player in world.server.players:
            if player.is_loading_position(self.location.x, self.location.y, self.location.z):
                world.server.send_client_socket(player, self, "BlockUpdate")

    def _can_destroy_with_fluid(self, block: Block) -> bool:
        if getattr(block, "block_id", None) == "air" or self.is_same_fluid(block):
            return False
        if getattr(block, "is_fluid", False):
            return False
        return bool(getattr(block, "breakable", False) and not getattr(block, "solid", True))

    def _can_flow_into(self, block: Block) -> bool:
        if self.is_same_fluid(block):
            return True
        if getattr(block, "is_fluid", False):
            return False
        return (
            getattr(block, "block_id", None) == "air"
            or getattr(block, "replaceable", False)
            or self._can_destroy_with_fluid(block)
        )

    def _iter_horizontal_neighbors(self, z: int):
        for dx, dz, direction in ((-1, 0, -1), (1, 0, 1), (0, -1, 0), (0, 1, 0)):
            nz = z + dz
            if nz in (0, 1):
                yield dx, dz, direction

    def _try_flow_to(
        self,
        world,
        x: int,
        y: int,
        z: int,
        level: int,
        falling: bool,
        direction: int,
    ) -> bool:
        if y < 0 or y >= world.attribute.MAX_BUILD_HEIGHT or z not in (0, 1):
            return False
        if not world.is_position_loaded(x, y, z):
            return False

        level = max(self.source_level, min(self.max_level, int(level)))
        target = world.get_block(x, y, z)
        if self.is_same_fluid(target):
            should_replace = False
            if falling and not target.falling:
                should_replace = not target.is_source
            elif target.falling == falling and target.level > level:
                should_replace = True
            elif target.falling and not falling and target.level >= level:
                should_replace = True
            if not should_replace:
                return False
        elif not self._can_flow_into(target):
            return False
        elif self._can_destroy_with_fluid(target):
            target.on_break()

        world.set_block(self.make_fluid(level, falling, direction), x, y, z, send_packet=True, block_update=True)
        return True

    def _get_new_source_level(self, world, x: int, y: int, z: int) -> int | None:
        if not self.can_create_source:
            return None
        below = world.get_block(x, y - 1, z)
        if not (getattr(below, "solid", False) or self.is_same_fluid(below)):
            return None
        source_neighbors = 0
        for dx, dz, _ in self._iter_horizontal_neighbors(z):
            neighbor = world.get_block(x + dx, y, z + dz)
            if self.is_same_fluid(neighbor) and neighbor.is_source:
                source_neighbors += 1
        if source_neighbors >= 2:
            return self.source_level
        return None

    def _get_supporting_flow(self, world, x: int, y: int, z: int) -> tuple[int, bool, int] | None:
        above = world.get_block(x, y + 1, z)
        if self.is_same_fluid(above):
            return self.source_level, True, 0

        best: tuple[int, bool, int] | None = None
        for dx, dz, _ in self._iter_horizontal_neighbors(z):
            neighbor = world.get_block(x + dx, y, z + dz)
            if not self.is_same_fluid(neighbor):
                continue
            candidate_level = neighbor.level + 1
            if candidate_level > self.max_level:
                continue
            candidate_direction = -dx if dx != 0 else 0
            candidate = (candidate_level, False, candidate_direction)
            if best is None or candidate_level < best[0]:
                best = candidate
        return best

    def _get_horizontal_flow_directions(self, world, x: int, y: int, z: int) -> list[tuple[int, int, int]]:
        candidates = [
            (dx, dz, direction)
            for dx, dz, direction in self._iter_horizontal_neighbors(z)
            if self._can_flow_horizontally(world, x + dx, y, z + dz, self.level + 1)
        ]
        if len(candidates) <= 1:
            return candidates

        drop_distances = {
            candidate: self._distance_to_drop(world, x, y, z, candidate[0], candidate[1])
            for candidate in candidates
        }
        best_distance = min(drop_distances.values())
        if best_distance < 999:
            return [candidate for candidate in candidates if drop_distances[candidate] == best_distance]
        return candidates

    def _can_flow_horizontally(self, world, x: int, y: int, z: int, level: int) -> bool:
        if z not in (0, 1):
            return False
        if not world.is_position_loaded(x, y, z):
            return False
        target = world.get_block(x, y, z)
        if self.is_same_fluid(target):
            return target.falling or target.level > level
        return self._can_flow_into(target)

    def _distance_to_drop(self, world, x: int, y: int, z: int, dx: int, dz: int) -> int:
        for distance in range(1, self.horizontal_flow_range + 1):
            nx = x + dx * distance
            nz = z + dz * distance
            if nz not in (0, 1):
                break
            if not world.is_position_loaded(nx, y, nz):
                break
            target = world.get_block(nx, y, nz)
            if not (self.is_same_fluid(target) or self._can_flow_into(target)):
                break
            below = world.get_block(nx, y - 1, nz)
            if self._can_flow_into(below) and not self.is_same_fluid(below):
                return distance
        return 999



class Plant(Block):
    # 所有植物基类
    break_sound = 'dig.grass'
    solid = False
    light_attenuation = 1

    def on_update(self):
        if BlockTag.GRASS_BLOCKS not in self.location.world.get_block(self.location.add(0, -1, 0)).Tags:
            self.location.world.break_block(self.location)

class GrassStain(Plant):
    # 需要更据生物群系染色的植物（草）
    _texture_cache = {}  # key: (size, biome_id)

    @client_method
    def get_texture(self, size, client: 'Client'):
        # 获取 biome_id 用于缓存键（不同群系染色不同）
        if self.location is not None and self.location.world is not None:
            biome_id = self.location.world.get_biome(
                self.location.x, self.location.y)
        else:
            biome_id = "__default__"

        cache_key = (type(self), self._texture_path, size, biome_id)
        if cache_key in self._texture_cache:
            return self._texture_cache[cache_key]

        # 1. 获取基础材质
        base_texture = client.resources_manager.get_texture_img(self._texture_path)

        if base_texture is None:
            return None

        # 首次加载纹理时自动检测是否存在透明像素
        cls = type(self)
        if cls.has_transparent_pixels is None:
            cls.has_transparent_pixels = client.resources_manager.has_transparent_pixels(base_texture)

        # 2. 缩放至目标尺寸
        texture_scaled = pygame.transform.scale(base_texture, (size, size))

        # 3. 染色纹理 (使用 RGB 元组 (30, 50, 70))
        stained_texture = client.resources_manager.biome_stain(texture_scaled, self.location).convert_alpha()

        # 4. 存入缓存
        self._texture_cache[cache_key] = stained_texture

        return stained_texture

class Leaves(Block):
    solid = True
    _texture_cache = {}   # key: (size, biome_id)
    _effect_cache = {}    # key: (size, biome_id, z, front_same, behind_leaf)
    break_sound = 'dig.grass'
    hardness = 0.2
    preferred_tool = "hoe"

    @client_method
    def get_texture(self, size, client: 'Client'):
        # 获取 biome_id 用于缓存键（不同群系染色不同）
        if self.location is not None and self.location.world is not None:
            biome_id = self.location.world.get_biome(
                self.location.x, self.location.y)
        else:
            biome_id = "__default__"

        # 检测前后层树叶状态
        z = self.location.z if self.location is not None else -1
        front_same = False
        behind_leaf = False
        if self.location is not None and self.location.world is not None:
            if z == 0:
                front = self.location.world.get_block(
                    self.location.x, self.location.y, 1)
                front_same = type(front) is type(self)
            elif z == 1:
                behind = self.location.world.get_block(
                    self.location.x, self.location.y, 0)
                behind_leaf = isinstance(behind, Leaves)

        # 效果缓存键（含世界状态，状态变化时自动失效）
        effect_key = (size, biome_id, z, front_same, behind_leaf, type(self))
        if effect_key in self._effect_cache:
            return self._effect_cache[effect_key]

        # 获取/生成染色纹理
        tex_key = (size, biome_id, type(self))
        if tex_key in self._texture_cache:
            stained = self._texture_cache[tex_key]
        else:
            base_texture = client.resources_manager.get_texture_img(self._texture_path)
            if base_texture is None:
                return None

            # 首次加载纹理时自动检测是否存在透明像素
            cls = type(self)
            if cls.has_transparent_pixels is None:
                cls.has_transparent_pixels = client.resources_manager.has_transparent_pixels(base_texture)

            scaled = pygame.transform.scale(base_texture, (size, size))
            stained = client.resources_manager.biome_stain(
                scaled, self.location, "foliage"
            ).convert_alpha()
            self._texture_cache[tex_key] = stained

        result = stained

        # z=0 背景层：前方有同种树叶 → 纹理上下半交换
        if front_same:
            half = size // 2
            top = stained.subsurface((0, 0, size, half)).copy()
            bottom = stained.subsurface((0, half, size, half)).copy()
            result = pygame.Surface((size, size), pygame.SRCALPHA)
            result.blit(bottom, (0, 0))       # 下半 → 上半
            result.blit(top, (0, half))       # 上半 → 下半

        # z=1 前景层：后方有任意树叶 → RGB 乘法加深（保护 alpha 通道）
        if behind_leaf:
            if result is stained:
                result = stained.copy()
            mask = pygame.Surface((size, size))
            mask.fill((50, 50, 50))
            result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

        self._effect_cache[effect_key] = result
        return result

class BottomSupport(Block):
    """
    底部需要支撑的方块
    """
    def on_update(self):
        if not self.location.world.get_block(self.location.add(0, -1, 0)).solid:
            self.location.world.break_block(self.location)

class Log(Block):
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"
    hardness = 2.0
    preferred_tool = 'axe'


class GravityBlock(Block):
    def __init__(self, nbt=None):
        # 仅服务端运行期使用，不能作为方块 NBT 发给客户端或写入存档。
        self._fall_scheduled = False
        super().__init__(nbt)

    def get_safe_attributes(self):
        attributes = super().get_safe_attributes()
        attributes.pop("_fall_scheduled", None)
        return attributes

    def place_at(self, location: Location) -> bool:
        placed = super().place_at(location)
        if placed and hasattr(location.world, "spawn_entity"):
            self.on_update()
        return placed

    @server_method
    def on_update(self, server = None):
        if self.location is None:
            return
        # 同一轮连锁更新可能多次通知同一个方块；下落事件尚未执行时只入队一次。
        if getattr(self, "_fall_scheduled", False):
            return
        below = self.location.world.get_block(self.location.add(0, -1, 0))
        if getattr(below, "solid", False):
            return
        self._fall_scheduled = True
        server.register_event(self._start_falling)

    def _start_falling(self):
        if self.location is None or not hasattr(self.location.world, "spawn_entity"):
            return
        from resources.server.entities.falling_block import FallingBlock
        from resources.server.blocks import AIR

        world = self.location.world
        x, y, z = int(self.location.x), int(self.location.y), int(self.location.z)
        self._fall_scheduled = False

        # 事件延迟到下一 tick；此时方块可能已被替换或重新获得支撑。
        if world.get_block(x, y, z) is not self:
            return
        below = world.get_block(x, y - 1, z)
        if getattr(below, "solid", False):
            return

        world.set_block(AIR(), self.location, send_packet=True, block_update=True)
        falling = FallingBlock(x + 0.01, y, z, world, self)
        world.spawn_entity(falling)
