import resources.server.materials as materials
import pygame

from resources.server.attributes import AttributeModifier
from resources.server.text import Text, TextColor

from resources.server.utils import client_method


class ItemStack:
    def __init__(self, material, amount: int = 1, nbt = None):
        if nbt is None:
            nbt = {}
        self.nbt = nbt
        self.material = material
        self.amount = amount
        self.max_stack_size = material.max_stack_size
        self.name = None

    def get_name(self):
        if self.name is None:
            return self.material.get_name()
        return self.name

    def is_empty(self) -> bool:
        """
        判断物品是否为空
        """
        return self.material == materials.AIR() or self.amount == 0

    def is_stackable_with(self, other: 'ItemStack') -> bool:
        """
        判断两个物品是否可以堆叠
        """
        return (self.material == other.material and
                self.nbt == other.nbt and self.amount + other.amount <= self.max_stack_size)

    def get_attribute_modifiers(self, equipment_slot: str = "mainhand"):
        """Return validated ``(attribute id, modifier)`` pairs for this slot.

        An explicit modern ``attribute_modifiers`` item component replaces the
        material defaults, matching Java Edition's data-component behavior.
        """
        slot = str(equipment_slot).lower().replace("_", "")
        sentinel = object()
        component = self.nbt.get(
            "attribute_modifiers",
            self.nbt.get("minecraft:attribute_modifiers", sentinel),
        )
        if component is sentinel:
            raw_entries = self.material.get_default_attribute_modifiers()
        elif isinstance(component, dict):
            raw_entries = component.get("modifiers", ())
        elif isinstance(component, list):
            raw_entries = component
        else:
            raw_entries = ()

        result = []
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            entry_slot = str(entry.get("slot", "any")).lower().replace("_", "")
            valid_slot = (
                entry_slot == "any"
                or entry_slot == slot
                or entry_slot == "hand" and slot in {"mainhand", "offhand"}
                or entry_slot == "armor" and slot in {"head", "chest", "legs", "feet"}
            )
            if not valid_slot:
                continue
            attribute_id = entry.get("type", entry.get("attribute"))
            if attribute_id is None or "id" not in entry:
                continue
            try:
                result.append((str(attribute_id), AttributeModifier.from_dict(entry)))
            except (KeyError, TypeError, ValueError):
                continue
        return tuple(result)

    def stack_item(self, other: 'ItemStack') -> bool:
        """
        尝试将两个物品堆叠在一起, 返回是否成功
        """
        if self.is_stackable_with(other):
            self.amount += other.amount
            other.amount = 0
            other.material = materials.AIR()
            return True
        else:
            return False

    def add_amount(self, amount: int) -> bool:
        """
        增加物品数量, 修改原 ItemStack
        """
        if self.amount + amount <= self.max_stack_size:
            self.amount += amount
            return True
        else:
            return False

    def reduce_amount(self, amount: int) -> bool:
        """
        减少物品数量, 修改原 ItemStack
        """
        if self.amount - amount >= 0:
            self.amount -= amount
            if self.amount == 0:
                self.material = materials.AIR()
            return True
        else:
            return False

    @client_method
    def get_texture(self, scale: float, client, shadow=False, multiply=1):
        animation_key = self.material.get_texture_animation_key()
        cache_key = (round(scale, 4), shadow, multiply, animation_key)
        if cache_key in self.material.texture_cache:
            return self.material.texture_cache[cache_key]

        px_scale = max(1, int(round(client.render.gui_scale)))

        res = self.material.get_texture(scale)
        if shadow and res is not None:

            # 创建带阴影的最终纹理
            width = res.get_width()
            height = res.get_height()
            
            # 创建一个更大的surface来容纳阴影偏移
            result = pygame.Surface((width + px_scale, height + px_scale), pygame.SRCALPHA)
            
            # Vectorised alpha-preserving shadow tint.  The old nested Python
            # pixel loop ran again for every animated frame.
            shadow_surface = res.copy()
            shadow_surface.fill(
                (0, 0, 0, 128),
                special_flags=pygame.BLEND_RGBA_MULT,
            )
            
            # 将阴影绘制到结果surface（向右下偏移1px）
            result.blit(shadow_surface, (px_scale, px_scale))

            # 将原纹理绘制到结果surface
            result.blit(res, (0, 0))

            result.convert_alpha()

            self.material.texture_cache[cache_key] = result
            if len(self.material.texture_cache) > 128:
                self.material.texture_cache.pop(next(iter(self.material.texture_cache)))
            
            return result
        
        return res

    def get_lore(self) -> list[str | Text]:
        return []


class EmptyItemStack(ItemStack):
    def __init__(self):
        super().__init__(materials.AIR(), 0)

    def is_empty(self) -> bool:
        """
        判断物品是否为空
        """
        return True
