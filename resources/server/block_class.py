import logging

import pygame

from resources.server.location import Location


class Block:
    block_id = None
    name = None
    _texture_path = None          # 图片文件路径
    _texture = None      # 原始 Surface（懒加载）
    _last_scaled = -1
    solid = True
    friction = 0.6
    break_sound = 'dig.stone'
    replaceable = False
    breakable = True
    light_attenuation = 3

    def __init__(self):
        # 方块应该带有的属性
        self.nbt = {}
        self.location = None

    @classmethod
    def get_texture(cls, size, client: 'Client'):
        if cls._texture is None:
            cls._texture = client.resources_manager.get_texture_img(cls._texture_path)
        if size != cls._last_scaled:
            cls._texture = pygame.transform.scale(cls._texture, (size, size))
        return cls._texture

    def place_at(self, location: Location) -> bool:
        if location.world.get_block(location).replaceable:
            location.world.set_block(self, location)
            return True
        return False

    def on_generate(self):
        pass

    def on_break(self):
        pass

    def on_right_click(self) -> bool:
        return False # 返回此方块能否被交互

    def on_left_click(self):
        pass

    def to_dict(self):
        return {
            'id': self.block_id,
            'nbt': self.nbt
        }