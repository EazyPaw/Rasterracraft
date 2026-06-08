from abc import ABC, abstractmethod

import pygame


class GUI(ABC):
    _texture_cache = {}
    _texture_path = "gui.sprites.hud.hotbar"

    def __init__(self, render: 'Render'):
        self.render = render
        self.priority = 0.0

    @classmethod
    def get_texture(cls, size: float, client, path=None):
        """
        获取缩放后的纹理（支持浮点倍率）
        :param path: 加载其它纹理
        :param size: 缩放倍率（如 2.0 表示放大 2 倍）
        :param client: 客户端实例
        :return: 缩放后的 Surface
        """
        if path is None:
            path = cls._texture_path
        
        if path is None:
            return None

        cache_key = (path, size)
        
        if cache_key in cls._texture_cache:
            return cls._texture_cache[cache_key]

        original_texture = client.resources_manager.get_texture_img(path,True)

        if original_texture is None:
            return None

        original_width = original_texture.get_width()
        original_height = original_texture.get_height()

        new_width = max(1, int(original_width * size))
        new_height = max(1, int(original_height * size))

        scaled_texture = pygame.transform.scale(original_texture, (new_width, new_height))

        cls._texture_cache[cache_key] = scaled_texture

        return scaled_texture

    def draw(self):
        pass

    def handle_events(self, events: list[pygame.event.Event]):
        """
        此处传入 events，如果此 GUI 已经处理了这个事件，那么应该将该事件从 events 中移除，以防止其被二次执行
        :param events:
        :return:
        """
        pass

    def on_open(self):
        pass

    def on_close(self):
        pass



