import pygame
import math

from resources.server.utils import client_method
from resources.server.location import Location


class Material:
    name_id = "null"
    name = "Null"
    max_stack_size = 64
    _texture_path = None
    _original_texture = None
    _last_scaled = None

    def __init__(self):
        self.texture_cache = {}
    
    @classmethod
    @client_method
    def get_texture(cls, size: float, client):
        """
        获取缩放后的纹理（支持浮点倍率）
        (client 参数由 @client_only 自动注入)
        :param size: 缩放倍率（如 2.0 表示放大 2 倍）
        :param client: 客户端实例
        :return: 缩放后的 Surface
        """
        if cls._texture_path is None:
            return None

        # 加载原始纹理（如果还未加载）
        if cls._original_texture is None:
            cls._original_texture = client.resources_manager.get_texture_img(cls._texture_path)

        if cls._original_texture is None:
            return None

        # 使用容差比较，避免浮点精度导致无意义重缩放
        need_rescale = (
                cls._last_scaled is None or
                abs(size - cls._last_scaled) > 1e-6
        )

        if need_rescale:
            original_width = cls._original_texture.get_width()
            original_height = cls._original_texture.get_height()

            # 计算新尺寸（至少为 1，防止缩放为 0 导致错误）
            new_width = max(1, int(original_width * size))
            new_height = max(1, int(original_height * size))

            # 缩放
            texture = pygame.transform.scale(cls._original_texture, (new_width, new_height))
            cls._last_scaled = size

            return texture
        
        return cls._original_texture

    def __eq__(self, other):
        """
        比较两个 Material 实例是否相等。
        基于 name_id 而非对象身份，确保不同实例的同种材料（如两个 DIRT()）可以互相堆叠。
        """
        if isinstance(other, Material):
            return self.name_id == other.name_id
        return NotImplemented

    def __hash__(self):
        """
        基于 name_id 的哈希值，与 __eq__ 保持一致。
        """
        return hash(self.name_id)

    def __str__(self):
        return self.name_id


class BlockItem(Material):
    target_block = None

    @classmethod
    @client_method
    def get_texture(cls, size: float, client):
        if cls.target_block is None:
            return None
        block_size = max(1, int(round(16 * size)))
        block = cls.target_block()
        # Some block item textures (grass/leaves) use biome colouring.  Item
        # entities do not carry a Block instance, so borrow the local player's
        # biome solely for rendering instead of dereferencing a None location.
        player = getattr(client, "client_player", None)
        block.location = Location(
            client.client_world,
            math.floor(player.x) if player is not None else 0,
            math.floor(player.y) if player is not None else 0,
            0,
        )
        return block.get_texture(block_size, client=client)
