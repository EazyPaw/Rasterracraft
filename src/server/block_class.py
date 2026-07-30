# Commented and arranged by ChatGPT
from abc import ABC

import ast
import logging
import random
from dataclasses import dataclass

import pygame
from pygame import Surface

from src.client.resources_manager import transkey
from src.server.utils import is_safe_value, client_method, server_method

from src.server.location import Location
from src.server.material_class import Material
from src.server.tags import BlockTag
from src.server.block_collision import (
    EMPTY,
    FULL_BLOCK,
    HALF_BOTTOM,
    HALF_TOP,
    BlockCollisionBox,
    coerce_collision_shape,
)

BLOCK_EXPERIENCE = {
    "coal_ore": (0, 2),
    "diamond_ore": (3, 7),
    "emerald_ore": (3, 7),
    "lapis_ore": (2, 5),
    "redstone_ore": (1, 5),
}


@dataclass(frozen=True)
class PlacementContext:
    """射线选面后的通用放置上下文。

    ``hit_face`` 使用 ``top``、``bottom``、``left``、``right`` 表示射线
    进入目标方块的面；坐标系与世界方块一致，y 轴向上。方块只需消费
    自己关心的字段，新增需要定向放置的方块无需改动游戏模式。
    """

    hit_face: str | None
    ray_origin: tuple[float, float]
    ray_direction: tuple[float, float]
    target_z: int
    fore_place: bool = False


@dataclass(frozen=True)
class BlockDrop:
    material_type: type[Material]
    amount: int = 1
    nbt: dict | None = None

    def create_stack(self):
        if self.amount <= 0:
            raise ValueError("Block drop amount must be positive")
        from src.server.item_class import ItemStack

        return ItemStack(
            self.material_type(),
            self.amount,
            dict(self.nbt) if self.nbt is not None else None,
        )


class Block(ABC):
    block_id = None
    name = None
    _texture_path = None  # 图片文件路径
    _texture = None  # 原始 Surface（懒加载）
    _last_scaled = -1
    _last_tex_id = -1  # 用于检测动画帧变化（id(tex)）
    solid = True

    collision_box = FULL_BLOCK

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
    break_sound = "dig.stone"
    place_sound = None  # 放置时播放的音效，默认 None 与 break_sound 一样
    breakable = True
    light_attenuation = 5
    light_source = 0
    Tags = []
    has_transparent_pixels = None  # None = 自动从纹理检测，也可手动覆盖为 True/False
    drops: tuple[BlockDrop, ...] | None = None
    # 世界方块单位中的纯渲染偏移；正 x 向右、正 y 向上。碰撞和逻辑坐标
    # 不受影响。渲染器按区块中实际最大偏移动态预留缓存边距。
    render_offset_blocks = (0.0, 0.0)

    def __init__(self, nbt=None):
        # 方块应该带有的属性
        self.location = None
        if self.place_sound is None:
            self.place_sound = self.break_sound
        if nbt:
            self.write_nbt(nbt)

    def get_collision_box(self) -> BlockCollisionBox:
        return coerce_collision_shape(self.collision_box)

    def has_collision_box(self) -> bool:
        return bool(self.get_collision_box())

    def get_name(self):
        return transkey(self.name)

    def can_precompose_with(self, rear_block: "Block") -> bool:
        return False

    def get_precomposed_texture(self, size, rear_block: "Block"):
        return None

    @classmethod
    @client_method
    def get_texture(cls, size, client=None):
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
            cls.has_transparent_pixels = (
                client.resources_manager.has_transparent_pixels(tex)
            )

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
                        f"There exists a incorrect type nbt, expect {type(current_attr)}, but got {type(value)}."
                    )
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

    def get_placement_location(
        self,
        target,
        *,
        player=None,
        fore_place=False,
        context: PlacementContext | None = None,
    ):
        """返回客户端放置预览应使用的位置。

        普通方块默认沿用项目原有的同格/另一深度层规则。需要根据玩家
        方向、支撑面或方块状态计算位置的方块覆写此接口，游戏模式本身
        不需要知道具体方块类型。
        """
        target_location = getattr(target, "location", None)
        if target_location is None:
            return None
        world = target_location.world
        if world.get_block(target_location).replaceable:
            return target_location

        other_z = 1 if target_location.z == 0 else 0
        alternative = target_location.add(0, 0, other_z - target_location.z)
        return alternative if world.get_block(alternative).replaceable else None

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
        return getattr(
            material, "tool_type", None
        ) == self.preferred_tool and tiers.get(
            getattr(material, "tier", ""), -1
        ) >= tiers.get(self.required_tool_tier, 0)

    def get_drops(self, material):
        if not self.can_harvest(material):
            return []
        from src.server.item_class import ItemStack
        from src.server.materials import get_block_item

        if self.drops is None:
            return [ItemStack(get_block_item(self), 1)]
        return [drop.create_stack() for drop in self.drops]

    def get_explosion_drops(self):
        from src.server.item_class import ItemStack
        from src.server.materials import get_block_item

        if self.drops is None:
            return [ItemStack(get_block_item(self), 1)]
        return [drop.create_stack() for drop in self.drops]

    def get_experience(self, material) -> int:
        if not self.can_harvest(material):
            return 0
        import random

        bounds = BLOCK_EXPERIENCE.get(self.block_id)
        return random.randint(*bounds) if bounds else 0

    def on_use(self, player, material) -> bool:
        return False

    def accepts_item_use(self, material) -> bool:
        return False

    def on_exploded(self, power: float, source=None) -> bool:
        return self.breakable

    def on_right_click(self, player) -> bool:
        """
        执行方块被右键交互时的操作，返回方块交互是否成功（如果方块不可交互则始终返回 False ）
        :return:
        """
        return False  # 返回此方块能否被交互

    def on_left_click(self, player) -> bool:
        return False

    def on_fallen_on(self, entity, fall_distance: float) -> bool:
        return False

    def notify_state_changed(self) -> None:
        if self.location is None:
            return
        world = self.location.world
        mark_dirty = getattr(world, "mark_chunk_dirty", None)
        if callable(mark_dirty):
            mark_dirty(int(self.location.x) // 16)
        invalidate_packet = getattr(world, "invalidate_chunk_packet", None)
        if callable(invalidate_packet):
            invalidate_packet(int(self.location.x) // 16)
        server = getattr(world, "server", None)
        if server is None:
            return
        for player in tuple(getattr(server, "players", ())):
            if player.is_loading_position(
                self.location.x, self.location.y, self.location.z
            ):
                server.send_client_socket(player, self, "BlockUpdate")

    def get_light_state(self) -> tuple[bool, int, int]:
        return bool(self.solid), int(self.light_attenuation), int(self.light_source)

    def on_update(self):
        pass

    def to_dict(self):
        rst = {
            "id": self.block_id,
        }
        if nbt := self.parse_nbt():
            rst["nbt"] = nbt
        return rst

    def on_random_tick(self):
        pass


class FluidBlock(Block):
    solid = False
    collision_box = EMPTY
    replaceable = True
    light_attenuation = 1
    has_transparent_pixels = True
    is_fluid = True

    _flow_texture_path = None

    flow_texture_tile_span = 2
    _texture_cache = {}
    _scaled_atlas_cache = {}
    _precomposed_texture_cache = {}
    max_level = 7
    source_level = 0
    flow_speed_ticks = 5
    can_create_source = True

    source_surface_pixels = 128.0 / 9.0
    flowing_surface_step_pixels = 16.0 / 9.0

    flow_level_step = 1
    horizontal_flow_range = 5

    supported_horizontal_flow_range = 1
    flowing_sound = None
    source_sound = None
    blast_resistance = 100

    def __init__(
        self, level: int = 0, falling: bool = False, flow_direction: int = 0, nbt=None
    ):
        self.level = max(0, min(self.max_level, int(level)))
        self.falling = bool(falling)
        self.flow_direction = (
            -1 if flow_direction < 0 else (1 if flow_direction > 0 else 0)
        )
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

        if self._has_same_fluid_above():
            return 1.0
        amount = 8 if self.is_source or self.falling else max(1, 8 - self.level)
        return max(1.0 / 16.0, min(1.0, amount / 9.0))

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
                neighbor_height = neighbor.fluid_height_ratio()
                own_weight = 10.0 if own >= 0.8 else 1.0
                neighbor_weight = 10.0 if neighbor_height >= 0.8 else 1.0
                edges.append(
                    (own * own_weight + neighbor_height * neighbor_weight)
                    / (own_weight + neighbor_weight)
                )
            else:
                edges.append(own)
        return edges[0], edges[1]

    def can_precompose_with(self, rear_block: Block) -> bool:

        return type(rear_block) is type(self)

    @client_method
    def get_precomposed_texture(self, size, rear_block: Block, client=None):
        if not self.can_precompose_with(rear_block):
            return None

        front = self.get_texture(size, client=client)
        rear = rear_block.get_texture(size, client=client)
        if front is None or rear is None:
            return None

        block_type = type(self)
        cache = block_type.__dict__.get("_precomposed_texture_cache")
        if cache is None:
            cache = {}
            block_type._precomposed_texture_cache = cache
        cache_key = (front, rear)
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        width = max(front.get_width(), rear.get_width())
        height = max(front.get_height(), rear.get_height())
        texture = pygame.Surface((width, height), pygame.SRCALPHA).convert_alpha()
        texture.blit(rear, (0, height - rear.get_height()))
        texture.blit(front, (0, height - front.get_height()))
        cache[cache_key] = texture
        if len(cache) > 256:
            cache.pop(next(iter(cache)))
        return texture

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
        block_type = type(self)
        atlas_cache = block_type.__dict__.get("_scaled_atlas_cache")
        if atlas_cache is None:
            atlas_cache = {}
            block_type._scaled_atlas_cache = atlas_cache
        atlas_key = (base_texture, atlas_size, self.flow_direction < 0)
        scaled = atlas_cache.get(atlas_key)
        if scaled is None:
            scaled = pygame.transform.scale(
                base_texture, (atlas_size, atlas_size)
            ).convert_alpha()
            if self.flow_direction < 0:
                scaled = pygame.transform.flip(scaled, True, False)
            atlas_cache[atlas_key] = scaled
            if len(atlas_cache) > 128:
                atlas_cache.pop(next(iter(atlas_cache)))

        tile = scaled.subsurface(
            pygame.Rect(phase_x * size, phase_y * size, size, size)
        )
        texture = tile.subsurface(pygame.Rect(0, size - tex_h, size, tex_h)).copy()
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
        if self.location is None:
            return

        world = self.location.world
        x = int(self.location.x)
        y = int(self.location.y)
        z = int(self.location.z)

        if getattr(self, "block_id", None) == "lava":
            if self._react_with_adjacent_fluid(world, x, y, z):
                return
        elif getattr(self, "block_id", None) == "water":
            lava_positions = [(x, y - 1, z)]
            lava_positions.extend(
                (x + dx, y, z + dz) for dx, dz, _ in self._iter_horizontal_neighbors(z)
            )
            for lx, ly, lz in lava_positions:
                lava = world.get_block(lx, ly, lz)
                if getattr(lava, "block_id", None) != "lava":
                    continue
                if lava._react_with_adjacent_fluid(world, lx, ly, lz):
                    return

        if hasattr(world, "schedule_fluid_tick"):
            world.schedule_fluid_tick(self.location)

    def tick_fluid(self):
        if self.location is None:
            return

        world = self.location.world
        x = int(self.location.x)
        y = int(self.location.y)
        z = int(self.location.z)

        if self._react_with_adjacent_fluid(world, x, y, z):
            return

        if not self.is_source:
            source_level = self._get_new_source_level(world, x, y, z)
            if source_level is not None:
                updated = self.make_fluid(source_level, False, 0)
                self._replace_self(updated)

                updated.tick_fluid()
                return

            support = self._get_supporting_flow(world, x, y, z)
            if support is None:
                from src.server.blocks import AIR

                world.set_block(
                    AIR(), self.location, send_packet=True, block_update=True
                )
                return

            target_level, target_falling, target_direction = support
            if (
                target_level != self.level
                or target_falling != self.falling
                or target_direction != self.flow_direction
            ):
                updated = self.make_fluid(
                    target_level, target_falling, target_direction
                )
                self._replace_self(updated)

                updated.tick_fluid()
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

        flow_step = max(1, int(getattr(self, "flow_level_step", 1)))
        next_level = self.level + flow_step
        flow_dirs = self._get_horizontal_flow_directions(world, x, y, z, next_level)
        visible_dirs = [direction for _, _, direction in flow_dirs if direction != 0]
        self._set_own_direction(
            visible_dirs[0] if len(visible_dirs) == 1 and len(flow_dirs) == 1 else 0
        )
        for dx, dz, direction in flow_dirs:
            self._try_flow_to(world, x + dx, y, z + dz, next_level, False, direction)

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

    def _replace_self(self, fluid: "FluidBlock"):
        self.location.world.set_block(
            fluid, self.location, send_packet=True, block_update=True
        )

    def _set_own_direction(self, direction: int):
        direction = -1 if direction < 0 else (1 if direction > 0 else 0)
        if self.flow_direction == direction:
            return
        self.flow_direction = direction
        world = self.location.world
        world.mark_chunk_dirty(int(self.location.x) // 16)
        for player in world.server.players:
            if player.is_loading_position(
                self.location.x, self.location.y, self.location.z
            ):
                world.server.send_client_socket(player, self, "BlockUpdate")

    def _can_destroy_with_fluid(self, block: Block) -> bool:
        if getattr(block, "block_id", None) == "air" or self.is_same_fluid(block):
            return False
        if getattr(block, "is_fluid", False):
            return False
        return bool(
            getattr(block, "breakable", False) and not getattr(block, "solid", True)
        )

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

    @staticmethod
    def _iter_horizontal_neighbors(z: int):
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

        level = int(level)
        if level > self.max_level:
            return False
        level = max(self.source_level, level)
        target = world.get_block(x, y, z)

        if (
            getattr(self, "block_id", None) == "lava"
            and getattr(target, "block_id", None) == "water"
            and not falling
        ):
            return False
        interaction_result = self._interaction_result_for_target(target, falling)
        if interaction_result is not None:
            world.set_block(
                interaction_result, x, y, z, send_packet=True, block_update=True
            )
            self._emit_lava_fizz(world, x, y, z)
            return True
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

        world.set_block(
            self.make_fluid(level, falling, direction),
            x,
            y,
            z,
            send_packet=True,
            block_update=True,
        )
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

    def _get_supporting_flow(
        self, world, x: int, y: int, z: int
    ) -> tuple[int, bool, int] | None:
        above = world.get_block(x, y + 1, z)
        if self.is_same_fluid(above):
            return self.source_level, True, 0

        best: tuple[int, bool, int] | None = None
        for dx, dz, _ in self._iter_horizontal_neighbors(z):
            neighbor = world.get_block(x + dx, y, z + dz)
            if not self.is_same_fluid(neighbor):
                continue
            candidate_level = neighbor.level + max(
                1, int(getattr(self, "flow_level_step", 1))
            )
            if candidate_level > self.max_level:
                continue
            candidate_direction = -dx if dx != 0 else 0
            candidate = (candidate_level, False, candidate_direction)
            if best is None or candidate_level < best[0]:
                best = candidate
        return best

    def _get_horizontal_flow_directions(
        self, world, x: int, y: int, z: int, next_level: int | None = None
    ) -> list[tuple[int, int, int]]:
        if next_level is None:
            next_level = self.level + max(1, int(getattr(self, "flow_level_step", 1)))
        candidates = [
            (dx, dz, direction)
            for dx, dz, direction in self._iter_horizontal_neighbors(z)
            if self._can_flow_horizontally(world, x + dx, y, z + dz, next_level)
        ]
        if len(candidates) <= 1:
            return candidates

        drop_distances = {
            candidate: self._distance_to_drop(
                world, x, y, z, candidate[0], candidate[1]
            )
            for candidate in candidates
        }
        best_distance = min(drop_distances.values())
        if best_distance < 999:
            return [
                candidate
                for candidate in candidates
                if drop_distances[candidate] == best_distance
            ]
        return candidates

    def _react_with_adjacent_fluid(self, world, x: int, y: int, z: int) -> bool:
        block_id = getattr(self, "block_id", None)
        if block_id != "lava":
            return False

        from src.server.blocks import COBBLESTONE, OBSIDIAN

        neighbors = [(x, y + 1, z)]
        neighbors.extend(
            (x + dx, y, z + dz) for dx, dz, _ in self._iter_horizontal_neighbors(z)
        )
        for nx, ny, nz in neighbors:
            neighbor = world.get_block(nx, ny, nz)
            if getattr(neighbor, "block_id", None) != "water":
                continue
            result_type = OBSIDIAN if self.is_source else COBBLESTONE
            world.set_block(
                result_type(), self.location, send_packet=True, block_update=True
            )
            self._emit_lava_fizz(world, x, y, z)
            return True
        return False

    @staticmethod
    def _emit_lava_fizz(world, x: int, y: int, z: int) -> None:
        play_particle = getattr(world, "play_particle", None)
        if callable(play_particle):
            play_particle(
                "minecraft:smoke",
                x + 0.5,
                y + 0.5,
                z,
                count=1,
                motion=(0.0, 0.01),
            )

    def _interaction_result_for_target(self, target: Block, falling: bool):
        block_id = getattr(self, "block_id", None)
        target_id = getattr(target, "block_id", None)
        if {block_id, target_id} != {"water", "lava"}:
            return None

        if block_id == "water":
            return None
        if not falling:
            return None
        from src.server.blocks import STONE

        return STONE()

    def _can_flow_horizontally(self, world, x: int, y: int, z: int, level: int) -> bool:
        if level > self.max_level:
            return False
        if z not in (0, 1):
            return False
        if not world.is_position_loaded(x, y, z):
            return False
        target = world.get_block(x, y, z)
        if self.is_same_fluid(target):
            return target.falling or target.level > level
        return self._can_flow_into(target)

    def _distance_to_drop(self, world, x: int, y: int, z: int, dx: int, dz: int) -> int:
        below = world.get_block(x, y - 1, z)
        flow_range = (
            self.supported_horizontal_flow_range
            if self.is_same_fluid(below)
            else self.horizontal_flow_range
        )
        for distance in range(1, flow_range + 1):
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
    break_sound = "dig.grass"
    solid = False
    collision_box = EMPTY
    light_attenuation = 1

    def on_update(self):
        if (
            BlockTag.GRASS_BLOCKS
            not in self.location.world.get_block(self.location.add(0, -1, 0)).Tags
        ):
            self.location.world.break_block(self.location)


class GrassStain(Plant):
    # 需要更据生物群系染色的植物（草）
    _texture_cache = {}

    @client_method
    def get_texture(self, size, client):
        # 获取 biome_id 用于缓存键（不同群系染色不同）
        if self.location is not None and self.location.world is not None:
            biome_id = self.location.world.get_biome(self.location.x, self.location.y)
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
            cls.has_transparent_pixels = (
                client.resources_manager.has_transparent_pixels(base_texture)
            )

        # 2. 缩放至目标尺寸
        texture_scaled = pygame.transform.scale(base_texture, (size, size))

        # 3. 染色纹理 (使用 RGB 元组 (30, 50, 70))
        stained_texture = client.resources_manager.biome_stain(
            texture_scaled, self.location
        ).convert_alpha()

        # 4. 存入缓存
        self._texture_cache[cache_key] = stained_texture

        return stained_texture


class Leaves(Block):
    solid = True
    _texture_cache = {}
    _effect_cache = {}
    break_sound = "dig.grass"
    hardness = 0.2
    preferred_tool = "hoe"

    def __init__(self):
        super().__init__()
        self.distance = 0
        self.persistent = False

    @client_method
    def get_texture(self, size, client):
        # 获取 biome_id 用于缓存键（不同群系染色不同）
        if self.location is not None and self.location.world is not None:
            biome_id = self.location.world.get_biome(self.location.x, self.location.y)
        else:
            biome_id = "__default__"

        # 检测前后层树叶状态
        z = self.location.z if self.location is not None else -1
        front_same = False
        behind_leaf = False
        if self.location is not None and self.location.world is not None:
            if z == 0:
                front = self.location.world.get_block(
                    self.location.x, self.location.y, 1
                )
                front_same = type(front) is type(self)
            elif z == 1:
                behind = self.location.world.get_block(
                    self.location.x, self.location.y, 0
                )
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
                cls.has_transparent_pixels = (
                    client.resources_manager.has_transparent_pixels(base_texture)
                )

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
            result.blit(bottom, (0, 0))  # 下半 → 上半
            result.blit(top, (0, half))  # 上半 → 下半

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
        below = self.location.world.get_block(self.location.add(0, -1, 0))
        if not getattr(below, "has_collision_box", lambda: False)():
            self.location.world.break_block(self.location)


class Log(Block):
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


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
    def on_update(self, server=None):
        if self.location is None:
            return
        # 同一轮连锁更新可能多次通知同一个方块；下落事件尚未执行时只入队一次。
        if getattr(self, "_fall_scheduled", False):
            return
        below = self.location.world.get_block(self.location.add(0, -1, 0))
        if getattr(below, "has_collision_box", lambda: False)():
            return
        self._fall_scheduled = True
        server.register_event(self._start_falling)

    def _start_falling(self):
        if self.location is None or not hasattr(self.location.world, "spawn_entity"):
            return
        from src.server.entities.falling_block import FallingBlock
        from src.server.blocks import AIR

        world = self.location.world
        x, y, z = int(self.location.x), int(self.location.y), int(self.location.z)
        self._fall_scheduled = False

        # 事件延迟到下一 tick；此时方块可能已被替换或重新获得支撑。
        if world.get_block(x, y, z) is not self:
            return
        below = world.get_block(x, y - 1, z)
        if getattr(below, "has_collision_box", lambda: False)():
            return

        world.set_block(AIR(), self.location, send_packet=True, block_update=True)
        falling = FallingBlock(x + 0.01, y, z, world, self)
        world.spawn_entity(falling)


class SLABS(Block):
    _texture_cache = {}
    has_transparent_pixels = True

    def __init__(self, _type="bottom"):
        super().__init__()
        self._type = _type

    def get_collision_box(self) -> BlockCollisionBox:
        if self._type == "bottom":
            return HALF_BOTTOM
        if self._type == "top":
            return HALF_TOP
        if self._type == "double":
            return FULL_BLOCK
        raise ValueError(f"Unknown slabs type {self._type}")

    @client_method
    def get_texture(self, size, client=None):
        size = max(1, int(round(size)))
        full: Surface = client.resources_manager.get_texture_img(self._texture_path)
        if full is None:
            return None

        # get_texture_img 返回的是原始资源尺寸（通常为 16×16），而渲染器传入的
        # size 是屏幕上的方块尺寸。先缩放，否则在 size 大于原图时 subsurface 会越界。
        cache_key = (self._texture_path, full, self._type, size)
        if cache_key in self._texture_cache:
            return self._texture_cache[cache_key]

        scaled = pygame.transform.scale(full, (size, size)).convert_alpha()
        if self._type == "double":
            texture = scaled
        elif self._type in ("bottom", "top"):
            # 保持与普通方块相同的 size×size 画布，以便渲染器正确处理顶部、
            # 底部半砖的位置；未占用的半边保持透明。
            texture = pygame.Surface((size, size), pygame.SRCALPHA)
            half = size // 2
            if self._type == "bottom":
                source = scaled.subsurface((0, half, size, size - half))
                texture.blit(source, (0, half))
            else:
                source = scaled.subsurface((0, 0, size, half))
                texture.blit(source, (0, 0))
        else:
            raise ValueError(f"Unknown slabs type {self._type}")

        self._texture_cache[cache_key] = texture
        if len(self._texture_cache) > 512:
            self._texture_cache.pop(next(iter(self._texture_cache)))
        return texture


class SupportedBlock(Block):
    """需要完整方块支撑的装饰方块基类。

    ``support_offset`` 是相对于方块自身位置的支撑方向。默认值对应
    地面方块；挂壁方块只需要覆写这个属性即可复用存活检查和放置检查。
    """

    support_offset = (0, -1, 0)

    def get_support_offset(self) -> tuple[int, int, int]:
        """返回当前方块状态对应的支撑方向。"""
        return self.support_offset

    def get_support_location(self):
        if self.location is None or self.location.world is None:
            return None
        dx, dy, dz = self.get_support_offset()
        return self.location.add(dx, dy, dz)

    @staticmethod
    def is_full_block(block) -> bool:
        """返回方块是否能提供完整立方体支撑。

        ``solid`` 只表示碰撞/遮挡意义上的实体，半砖仍可能为 solid，
        所以支撑方块还要排除已知的半砖形态；特殊方块可显式提供
        ``full_block`` 覆盖这个默认判断。透明但占满整个格子的方块（如玻璃）
        仍然可以支撑火把。
        """
        if block is None:
            return False
        explicit = getattr(block, "full_block", None)
        if explicit is not None:
            return bool(explicit)
        getter = getattr(block, "get_collision_box", None)
        if not callable(getter):
            return False
        shape = coerce_collision_shape(getter())
        if len(shape) != 1:
            return False
        box = next(iter(shape))
        return box.min_x <= 0 and box.min_y <= 0 and box.max_x >= 1 and box.max_y >= 1

    def get_support_block(self):
        support_location = self.get_support_location()
        if support_location is None:
            return None
        return support_location.world.get_block(support_location)

    def can_survive(self) -> bool:
        return self.location is not None and self.is_full_block(
            self.get_support_block()
        )

    def can_place_at(self, location: Location) -> bool:
        """预检放置位置，避免短暂生成一个无支撑方块。"""
        if location is None or not location.world.get_block(location).replaceable:
            return False
        old_location = self.location
        self.location = location
        try:
            return self.can_survive()
        finally:
            self.location = old_location

    def place_at(self, location: Location) -> bool:
        if not self.can_place_at(location):
            return False
        placed = super().place_at(location)
        if placed:
            # Block.place_at 只负责写入世界；新方块本身不会收到邻居更新。
            self.on_update()
        return placed

    def on_update(self):
        if self.location is not None and not self.can_survive():
            self.location.world.break_block(self.location)


class ParticleEmitterBlock(SupportedBlock):
    """带有持续粒子效果的支撑方块。

    子类只需提供 ``particle_id``、发射间隔和 ``get_particle_position``，
    就能获得放置时立即发射、服务端定时发射以及失去支撑后自动停止的行为。
    """

    particle_id = None
    particle_interval_ticks = 4
    particle_count = 1

    def __init__(self, nbt=None):
        self._particle_event_scheduled = False
        self._particles_active = False
        super().__init__(nbt)

    def get_safe_attributes(self):
        attributes = super().get_safe_attributes()
        attributes.pop("_particle_event_scheduled", None)
        attributes.pop("_particles_active", None)
        return attributes

    def place_at(self, location: Location) -> bool:
        """玩家/命令正常放置时才启用运行时粒子。"""
        self._particles_active = True
        placed = super().place_at(location)
        if not placed:
            self._particles_active = False
        return placed

    def get_particle_position(self) -> tuple[float, float, int]:
        if self.location is None:
            return 0.0, 0.0, 0
        return self.location.x + 0.5, self.location.y + 0.75, self.location.z

    def emit_particle(self) -> bool:
        if self.location is None or not self.can_survive() or not self.particle_id:
            return False
        play_particle = getattr(self.location.world, "play_particle", None)
        if not callable(play_particle):
            return False
        x, y, z = self.get_particle_position()
        play_particle(self.particle_id, x, y, z, count=self.particle_count)
        return True

    def _schedule_particle(self):
        if self._particle_event_scheduled or self.location is None:
            return
        server = getattr(self.location.world, "server", None)
        register_event = getattr(server, "register_event", None)
        if not callable(register_event):
            return
        self._particle_event_scheduled = True
        register_event(
            self._particle_tick, ticks=max(1, int(self.particle_interval_ticks))
        )

    def _particle_tick(self):
        self._particle_event_scheduled = False
        if self.location is None or not self._particles_active:
            return
        world = self.location.world
        if world.get_block(self.location) is not self:
            return
        if not self.can_survive():
            support_location = self.get_support_location()
            is_loaded = getattr(world, "is_position_loaded", None)
            if (
                callable(is_loaded)
                and support_location is not None
                and not is_loaded(
                    support_location.x, support_location.y, support_location.z
                )
            ):
                self._schedule_particle()
                return
            world.break_block(self.location)
            return
        self.emit_particle()
        self._schedule_particle()

    def on_update(self):
        if self.location is None or not self.can_survive():
            super().on_update()
            return
        if self._particles_active:
            self.emit_particle()
            self._schedule_particle()

    def on_generate(self):
        # 世界生成器如果通过 place_at 放置，状态已经启用；这里复用统一
        # 的更新入口，而不需要为每种粒子方块重复写初始化代码。
        self.on_update()

    def on_load(self):
        """存档/区块恢复后的初始化钩子。"""
        # 发射状态是方块固有行为，而非一次放置会话的临时状态。区块重新
        # 载入时会新建方块实例，若保留默认 False，它就再也不会主动安排
        # 粒子任务，直到玩家重新放置该方块。这里恢复状态并重新安排任务，
        # 使存档加载、区块卸载后重载以及玩家重新进入世界都走同一条路径。
        #
        # 不在这里直接调用 on_update()/emit_particle()：区块边界另一侧的
        # 支撑方块可能尚未加载；_particle_tick 会在其可用后校验并继续，
        # 同时避免区块恢复期间突发地向客户端发送大量粒子包。
        self._particles_active = True
        self._particle_event_scheduled = False
        self._schedule_particle()

    def on_random_tick(self):
        # 没有事件调度器的测试世界/工具世界也能看到粒子；正式服务端由
        # _particle_tick 提供固定间隔效果。
        if self._particles_active and not self._particle_event_scheduled:
            self.emit_particle()
            self._schedule_particle()

    def on_break(self):
        self._particles_active = False
        self._particle_event_scheduled = False


class Crop(Block):
    solid = False
    collision_box = EMPTY
    light_attenuation = 1
    has_transparent_pixels = True
    hardness = 0.0
    break_sound = "dig.grass"
    maintains_farmland = True
    max_age = 7
    _crop_texture_cache = {}
    # 耕地表面比完整方块低 2/16 格，作物视觉上应落在其表面。
    render_offset_blocks = (0.0, -2 / 16)

    def __init__(self, nbt=None):
        self.age = 0
        super().__init__(nbt)

    @property
    def is_mature(self) -> bool:
        return self.age >= self.max_age

    def on_update(self):
        if self.location is None:
            return
        loc = self.location
        world = loc.world
        if world.get_block(loc.add(0, -1, 0)).block_id != "farmland":
            world.break_block(loc)

    def _growth_speed(self) -> float:
        loc = self.location
        world = loc.world
        speed = 1.0
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                soil_z = int(loc.z) + dz
                if soil_z not in (0, 1):
                    continue
                soil = world.get_block(int(loc.x) + dx, int(loc.y) - 1, soil_z)
                fertility = 0.0
                if getattr(soil, "block_id", None) == "farmland":
                    fertility = 3.0 if getattr(soil, "moisture", 0) > 0 else 1.0
                if dx != 0 or dz != 0:
                    fertility /= 4.0
                speed += fertility

        crop_id = self.block_id
        has_x_neighbor = any(
            world.get_block(int(loc.x) + dx, int(loc.y), int(loc.z)).block_id == crop_id
            for dx in (-1, 1)
        )
        other_z = 1 - int(loc.z)
        has_z_neighbor = (
            world.get_block(int(loc.x), int(loc.y), other_z).block_id == crop_id
        )
        has_diagonal = any(
            world.get_block(int(loc.x) + dx, int(loc.y), other_z).block_id == crop_id
            for dx in (-1, 1)
        )
        if (has_x_neighbor and has_z_neighbor) or has_diagonal:
            speed /= 2.0
        return speed

    def on_random_tick(self):
        if self.location is None or self.is_mature:
            return
        loc = self.location
        world = loc.world
        if world.get_block(loc.add(0, -1, 0)).block_id != "farmland":
            world.break_block(loc)
            return
        get_light = getattr(world, "get_sum_light", None)
        light = get_light(int(loc.x), int(loc.y)) if callable(get_light) else 15
        if light < 9:
            return
        bound = int(25.0 / max(0.01, self._growth_speed())) + 1
        if random.randrange(bound) != 0:
            return
        self.age = min(self.max_age, self.age + 1)
        self.notify_state_changed()

    def get_texture_path(self) -> str:
        return f"{self._texture_path}_stage_{self.age}"

    @client_method
    def get_texture(self, size, client=None):
        texture_path = self.get_texture_path()
        size = max(1, int(round(size)))
        tex = client.resources_manager.get_texture_img(texture_path)
        if tex is None:
            return None
        if self.has_transparent_pixels is None:
            self.has_transparent_pixels = (
                client.resources_manager.has_transparent_pixels(tex)
            )
        key = (type(self), size, texture_path, tex)
        cached = self._crop_texture_cache.get(key)
        if cached is None:
            cached = pygame.transform.scale(tex, (size, size)).convert_alpha()
            self._crop_texture_cache[key] = cached
            if len(self._crop_texture_cache) > 128:
                self._crop_texture_cache.pop(next(iter(self._crop_texture_cache)))
        return cached
