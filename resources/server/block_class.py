import logging

import pygame

class Block:
    block_id = None
    name = None
    _texture_path = None          # 图片文件路径
    _texture = None      # 原始 Surface（懒加载）
    _last_scaled = -1

    def __init__(self):
        # 方块应该带有的属性
        pass

    @classmethod
    def get_texture(cls, size):
        if cls._texture is None:
            cls._texture = pygame.image.load(cls._texture_path)
            print(type(cls._texture))
        if size != cls._last_scaled:
            cls._texture = pygame.transform.scale(cls._texture, (size, size))
        return cls._texture

    def on_generate(self):
        pass

    def on_break(self):
        pass

    def on_right_click(self):
        pass

    def on_left_click(self):
        pass