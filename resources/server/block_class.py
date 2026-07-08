from abc import ABC

import os
import ast
import logging

from resources.server.utils import is_safe_value, client_method

if os.environ.get('PYCRAFT_CLIENT') == '1':
    import pygame

from resources.server.location import Location
from resources.server.tags import BlockTag


class Block(ABC):
    block_id = None
    name = None
    _texture_path = None          # 图片文件路径
    _texture = None      # 原始 Surface（懒加载）
    _last_scaled = -1
    _last_tex_id = -1    # 用于检测动画帧变化（id(tex)）
    solid = True
    friction = 0.6
    break_sound = 'dig.stone'
    place_sound = None    # 放置时播放的音效，默认 None 与 break_sound 一样
    replaceable = False
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
        effect_key = (size, biome_id, z, front_same, behind_leaf)
        if effect_key in self._effect_cache:
            return self._effect_cache[effect_key]

        # 获取/生成染色纹理
        tex_key = (size, biome_id)
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
