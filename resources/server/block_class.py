from abc import ABC

import os
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

    def __init__(self):
        # 方块应该带有的属性
        self.nbt = {}
        self.location = None
        if self.place_sound is None:
            self.place_sound = self.break_sound

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
        return {
            'id': self.block_id,
            'nbt': self.nbt
        }

class Plant(Block):
    break_sound = 'dig.grass'
    solid = False
    light_attenuation = 1

    def on_update(self):
        if BlockTag.GRASS_BLOCKS not in self.location.world.get_block(self.location.add(0, -1, 0)).Tags:
            self.location.world.break_block(self.location)