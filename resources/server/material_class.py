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
    name_space_key = "minecraft"
    attribute_modifiers = ()
    Tags = ()

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

        # Always ask the resource manager for the current surface.  Static
        # textures return the same object, while animated textures return the
        # current frame surface.
        original = client.resources_manager.get_texture_img(cls._texture_path)
        if original is None:
            return None
        cls._original_texture = original

        # 缩放结果必须按尺寸缓存。旧实现只记录最后一次尺寸，但命中时
        # 返回了未缩放原图，导致热栏/背包或全屏切换后苹果、面包等忽然变小。
        key = (round(float(size), 4), original)
        # 每种 Material 必须拥有独立缓存；直接使用继承来的类属性会让
        # 苹果与面包在相同 GUI 缩放下互相复用错误纹理。
        cache = cls.__dict__.get("_scaled_texture_cache")
        if cache is None:
            cache = {}
            cls._scaled_texture_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached

        original_width = original.get_width()
        original_height = original.get_height()
        new_width = max(1, int(round(original_width * size)))
        new_height = max(1, int(round(original_height * size)))
        texture = pygame.transform.scale(original, (new_width, new_height))
        cls._last_scaled = key
        cache[key] = texture
        if len(cache) > 64:
            cache.pop(next(iter(cache)))
        return texture

    @classmethod
    @client_method
    def get_texture_animation_key(cls, client):
        if cls._texture_path is None:
            return None
        return client.resources_manager.get_texture_animation_key(cls._texture_path)

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

    @classmethod
    def get_default_attribute_modifiers(cls):
        """Declarative item modifiers, consumed only in matching equipment slots."""
        return tuple(cls.attribute_modifiers)

    @client_method
    def get_anchor(self):
        return {'anchor':(0.5,0.9),'offset':(0, 0),'scale':0.5,'rotation':-90}


class DamageableItem(Material):
    """Base for items which store vanilla-style damage on their ItemStack.

    Concrete items own their event hooks and therefore the amount consumed by
    each successful action.  Server action code only reports what happened.
    """

    max_stack_size = 1
    max_damage = 0

    def damage_stack(self, stack, amount: int, holder=None) -> bool:
        return stack.hurt_and_break(amount, holder)

    def on_mined_block(self, stack, holder, block) -> bool:
        return False

    def on_post_hurt_enemy(self, stack, holder, target) -> bool:
        return False

    def on_successful_block_use(self, stack, holder, block) -> bool:
        return False

    def on_successful_entity_interaction(self, stack, holder, target) -> bool:
        return False


class Food(Material):
    """Common interface for materials which can be eaten.

    Food definitions own their nutrition, saturation and use duration.  The
    consumer owns the kind of food state it supports; this keeps the callback
    usable by future animals or other entities instead of coupling it to
    ``Player``.
    """

    food_value = 0
    saturation_modifier = 0.0
    consume_duration_ticks = 32
    always_edible = False

    def can_consume(self, consumer) -> bool:
        checker = getattr(consumer, "can_consume_food", None)
        if callable(checker):
            return bool(checker(self))
        food_level = getattr(consumer, "food_level", None)
        if food_level is None:
            return True
        return bool(self.always_edible or float(food_level) < 20.0)

    def on_consume(self, consumer) -> None:
        """Apply this food after its use duration has completed."""
        handler = getattr(consumer, "consume_food", None)
        if callable(handler):
            handler(self)


class BlockItem(Material):
    target_block_id = None

    @classmethod
    def create_block(cls):
        """Create the block represented by this inventory material.

        Block classes are resolved only when the item is actually used.  This
        keeps the material definitions independent of ``blocks.py`` during
        module initialization while retaining a stable, serializable link.
        """
        if cls.target_block_id is None:
            return None
        from resources.server.blocks import get_block_by_id
        return get_block_by_id(cls.target_block_id)

    @classmethod
    @client_method
    def get_texture(cls, size: float, client):
        block = cls.create_block()
        if block is None:
            return None
        block_size = max(1, int(round(16 * size)))
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

    @classmethod
    @client_method
    def get_texture_animation_key(cls, client):
        sentinel = object()
        texture_path = cls.__dict__.get("_animation_texture_path", sentinel)
        if texture_path is sentinel:
            block = cls.create_block()
            if block is None:
                texture_path = None
            else:
                path_getter = getattr(block, "get_texture_path", None)
                texture_path = path_getter() if callable(path_getter) else block._texture_path
            cls._animation_texture_path = texture_path
        if texture_path is None:
            return None
        return client.resources_manager.get_texture_animation_key(texture_path)

class Projectile(Material):
    ...
