from abc import ABC

import os
import ast
import logging

from resources.server.utils import is_safe_value

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
    solid = True
    friction = 0.6
    break_sound = 'dig.stone'
    place_sound = None    # 放置时播放的音效，默认 None 与 break_sound 一样
    replaceable = False
    breakable = True
    light_attenuation = 5
    light_source = 0
    Tags = []

    def __init__(self, nbt = None):
        # 方块应该带有的属性
        self.location = None
        if self.place_sound is None:
            self.place_sound = self.break_sound
        if nbt:
            self.write_nbt(nbt)

    @classmethod
    def get_texture(cls, size, client):
        """
        返回方块的材质
        :param size:
        :param client:
        :return:
        """
        if cls._texture is None:
            cls._texture = client.resources_manager.get_texture_img(cls._texture_path)
        if size != cls._last_scaled:
            cls._texture = pygame.transform.scale(cls._texture, (size, size))
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
    break_sound = 'dig.grass'
    solid = False
    light_attenuation = 1

    def on_update(self):
        if BlockTag.GRASS_BLOCKS not in self.location.world.get_block(self.location.add(0, -1, 0)).Tags:
            self.location.world.break_block(self.location)