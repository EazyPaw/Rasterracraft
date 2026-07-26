import colorsys
import math
import random

import pygame

import resources.server.materials as materials

from resources.server.attributes import AttributeModifier
from resources.server.text import Text, TextColor

from resources.server.utils import client_method


class ItemStack:
    _durability_bar_cache = {}

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

    def get_max_damage(self) -> int:
        """Return the stack's data-component override or material durability."""
        raw = self.nbt.get(
            "minecraft:max_damage",
            self.nbt.get("max_damage", getattr(self.material, "max_damage", 0)),
        )
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return max(0, int(getattr(self.material, "max_damage", 0)))

    def is_unbreakable(self) -> bool:
        """Support both modern component presence and legacy boolean NBT."""
        return (
            "minecraft:unbreakable" in self.nbt
            or bool(self.nbt.get("unbreakable", self.nbt.get("Unbreakable", False)))
        )

    def is_damageable(self) -> bool:
        return (
            not self.is_empty()
            and self.amount > 0
            and self.get_max_damage() > 0
            and not self.is_unbreakable()
        )

    def get_damage(self) -> int:
        raw = self.nbt.get(
            "minecraft:damage",
            self.nbt.get("damage", self.nbt.get("Damage", 0)),
        )
        try:
            damage = int(raw)
        except (TypeError, ValueError):
            damage = 0
        return max(0, min(self.get_max_damage(), damage))

    def set_damage(self, damage: int) -> None:
        maximum = self.get_max_damage()
        damage = max(0, min(maximum, int(damage)))
        self.nbt.pop("minecraft:damage", None)
        self.nbt.pop("Damage", None)
        if damage:
            self.nbt["damage"] = damage
        else:
            self.nbt.pop("damage", None)

    def is_damaged(self) -> bool:
        return self.is_damageable() and self.get_damage() > 0

    def get_remaining_durability(self) -> int:
        return max(0, self.get_max_damage() - self.get_damage())

    def _get_enchantment_level(self, enchantment_id: str) -> int:
        """Read common modern and legacy enchantment payload shapes."""
        wanted = str(enchantment_id).split(":")[-1]
        components = (
            self.nbt.get("minecraft:enchantments"),
            self.nbt.get("enchantments"),
            self.nbt.get("Enchantments"),
        )
        for component in components:
            if isinstance(component, dict):
                levels = component.get("levels", component)
                if isinstance(levels, dict):
                    for key, value in levels.items():
                        if str(key).split(":")[-1] != wanted:
                            continue
                        try:
                            return max(0, int(value))
                        except (TypeError, ValueError):
                            return 0
            elif isinstance(component, list):
                for entry in component:
                    if not isinstance(entry, dict):
                        continue
                    key = entry.get("id", entry.get("name", ""))
                    if str(key).split(":")[-1] != wanted:
                        continue
                    try:
                        return max(0, int(entry.get("lvl", entry.get("level", 0))))
                    except (TypeError, ValueError):
                        return 0
        return 0

    @staticmethod
    def _holder_has_infinite_materials(holder) -> bool:
        mode = getattr(holder, "gamemode", None)
        return getattr(mode, "name_id", "survival") == "creative"

    @staticmethod
    def _notify_item_broken(holder) -> None:
        world = getattr(holder, "world", None)
        server = getattr(world, "server", None)
        broadcast_sound = getattr(server, "broadcast_sound", None)
        if callable(broadcast_sound):
            broadcast_sound(
                "random.break",
                float(getattr(holder, "x", 0.0)),
                float(getattr(holder, "y", 0.0)),
                int(getattr(holder, "z", 0)),
            )

    def hurt_and_break(self, amount: int, holder=None) -> bool:
        """Apply server-owned durability damage and remove a broken item.

        Unbreaking is evaluated independently for every requested point, as it
        is for non-armour items in Java Edition.  ``True`` means stack state
        changed and callers should synchronize the authoritative inventory.
        """
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return False
        if (
            amount <= 0
            or not self.is_damageable()
            or self._holder_has_infinite_materials(holder)
        ):
            return False

        unbreaking = self._get_enchantment_level("unbreaking")
        applied = sum(
            1
            for _ in range(amount)
            if unbreaking <= 0 or random.randrange(unbreaking + 1) == 0
        )
        if applied <= 0:
            return False

        new_damage = self.get_damage() + applied
        if new_damage >= self.get_max_damage():
            self.amount -= 1
            self._notify_item_broken(holder)
            if self.amount <= 0:
                self.amount = 0
                self.material = materials.AIR()
                self.max_stack_size = self.material.max_stack_size
                self.nbt = {}
            else:
                self.set_damage(0)
        else:
            self.set_damage(new_damage)
        return True

    def get_durability_bar_width(self) -> int:
        maximum = self.get_max_damage()
        if maximum <= 0:
            return 0
        width = math.floor(13 - self.get_damage() * 13 / maximum + 0.5)
        return max(0, min(13, width))

    def get_durability_bar_color(self) -> tuple[int, int, int]:
        maximum = self.get_max_damage()
        remaining = 0.0 if maximum <= 0 else self.get_remaining_durability() / maximum
        red, green, blue = colorsys.hsv_to_rgb(max(0.0, remaining) / 3.0, 1.0, 1.0)
        return int(red * 255), int(green * 255), int(blue * 255)

    def draw_durability_bar(self, render, slot_x: float, slot_y: float,
                            slot_size: float) -> None:
        """Draw Minecraft's 13x2 durability meter in a GUI slot."""
        if not self.is_damaged():
            return
        pixel = max(1, round(float(slot_size) / 18.0))
        width = 13 * pixel
        x = round(float(slot_x) + (float(slot_size) - width) / 2)
        y = round(float(slot_y) + float(slot_size) - 4 * pixel)
        filled = self.get_durability_bar_width() * pixel
        color = self.get_durability_bar_color()
        cache_key = (pixel, filled, color)
        meter = self._durability_bar_cache.get(cache_key)
        if meter is None:
            meter = pygame.Surface((width, 2 * pixel), pygame.SRCALPHA)
            meter.fill((0, 0, 0, 255))
            if filled > 0:
                meter.fill((*color, 255), pygame.Rect(0, 0, filled, pixel))
            self._durability_bar_cache[cache_key] = meter
            if len(self._durability_bar_cache) > 256:
                self._durability_bar_cache.pop(next(iter(self._durability_bar_cache)))
        render.blit(meter, (x, y))

    def is_stackable_with(
        self, other: 'ItemStack', *, require_full_fit: bool = True
    ) -> bool:
        """
        判断两个物品是否可以堆叠。

        ``require_full_fit=False`` 只检查材质和 NBT 兼容性，供允许部分
        转移的逻辑使用；默认值保留背包原先的“整堆必须能装下”语义。
        """
        compatible = self.material == other.material and self.nbt == other.nbt
        return compatible and (
            not require_full_fit
            or self.amount + other.amount <= self.max_stack_size
        )

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
        lore = []
        if self.is_damageable() and self.get_damage() != 0:
            lore.append(Text(f'durability: {self.get_max_damage() - self.get_damage()} / {self.get_max_damage()}'))
        return lore


class EmptyItemStack(ItemStack):
    def __init__(self):
        super().__init__(materials.AIR(), 0)

    def is_empty(self) -> bool:
        """
        判断物品是否为空
        """
        return True
