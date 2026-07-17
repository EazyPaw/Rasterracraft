import pygame
import math

from resources.client.resources_manager import transkey
from resources.server.utils import client_method
from resources.server.location import Location


class Material:
    name_id = "null"
    name = "Null"
    max_stack_size = 64
    _texture_path = None
    _original_texture = None
    _last_scaled = None
    _scaled_texture_cache = {}

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
        # 必须检查 cls.__dict__ 而非 cls._original_texture，否则
        # STONE_PICKAXE(WOODEN_PICKAXE) 会沿 MRO 找到木镐已缓存的纹理。
        if cls.__dict__.get("_original_texture") is None:
            cls._original_texture = client.resources_manager.get_texture_img(cls._texture_path)

        if cls._original_texture is None:
            return None

        # 缩放结果必须按尺寸缓存。旧实现只记录最后一次尺寸，但命中时
        # 返回了未缩放原图，导致热栏/背包或全屏切换后苹果、面包等忽然变小。
        key = round(float(size), 4)
        # 每种 Material 必须拥有独立缓存；直接使用继承来的类属性会让
        # 苹果与面包在相同 GUI 缩放下互相复用错误纹理。
        cache = cls.__dict__.get("_scaled_texture_cache")
        if cache is None:
            cache = {}
            cls._scaled_texture_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached

        original_width = cls._original_texture.get_width()
        original_height = cls._original_texture.get_height()
        new_width = max(1, int(round(original_width * size)))
        new_height = max(1, int(round(original_height * size)))
        texture = pygame.transform.scale(cls._original_texture, (new_width, new_height))
        cls._last_scaled = key
        cache[key] = texture
        if len(cache) > 16:
            cache.pop(next(iter(cache)))
        return texture

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


    def get_name(self) -> str:
        """返回用于 HUD、背包等界面的可读物品名称。"""
        return transkey(self.name)

    @client_method
    def get_anchor(self):
        return {'anchor':(0.5,0.9),'offset':(0, 0),'scale':0.5,'rotation':-90}


class BlockItem(Material):
    target_block = None

    @classmethod
    @client_method
    def get_texture(cls, size: float, client):
        if cls.target_block is None:
            return None
        block_size = max(1, int(round(16 * size)))
        block = cls.target_block()
        # Some block item textures (grass/leaves) use biome coloring.  Item
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

class Projectile(Material):
    ...
