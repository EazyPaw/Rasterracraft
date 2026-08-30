# Commented and arranged by ChatGPT
import colorsys
import math
import random

import numpy as np
import pygame

import src.server.materials as materials

from src.server.attributes import AttributeModifier
from src.server.material_class import BlockItem
from src.server.text import Text, TextColor

from src.server.utils import client_method


class ItemStack:
    _durability_bar_cache = {}
    _glint_texture_cache = {}
    _glint_coordinate_cache = {}
    _glint_strength = 1.0
    _glint_speed = 0.5
    # Item surfaces use local 0..1 UVs instead of Minecraft's atlas UVs.
    # Sampling one eighth of the glint makes the glint texture eight times
    # larger than the isolated item icon instead of repeating it eight times.
    _glint_uv_scale = 1.0 / 8.0
    _glint_rotation_degrees = 10.0
    _glint_x_period_units = 110000
    _glint_y_period_units = 30000
    _glint_frames_per_second = 60

    def __init__(self, material, amount: int = 1, nbt=None):
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
        raw = self.nbt.get(
            "minecraft:max_damage",
            self.nbt.get("max_damage", getattr(self.material, "max_damage", 0)),
        )
        try:
            return max(0, int(raw))
        except (TypeError, ValueError):
            return max(0, int(getattr(self.material, "max_damage", 0)))

    def is_unbreakable(self) -> bool:
        return "minecraft:unbreakable" in self.nbt or bool(
            self.nbt.get("unbreakable", self.nbt.get("Unbreakable", False))
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

    def get_enchantments(self) -> dict[str, int]:
        """Return normalized enchantment levels from current and legacy NBT shapes."""
        from src.server.enchantments import normalize_enchantment_id

        result: dict[str, int] = {}
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
                        if str(key) in {"show_in_tooltip", "tooltip_display"}:
                            continue
                        try:
                            enchantment_id = normalize_enchantment_id(key)
                            level = max(0, int(value))
                        except (TypeError, ValueError):
                            continue
                        if level:
                            result.setdefault(enchantment_id, level)
            elif isinstance(component, list):
                for entry in component:
                    if not isinstance(entry, dict):
                        continue
                    key = entry.get("id", entry.get("name", ""))
                    try:
                        enchantment_id = normalize_enchantment_id(key)
                        level = max(0, int(entry.get("lvl", entry.get("level", 0))))
                    except (TypeError, ValueError):
                        continue
                    if level:
                        result.setdefault(enchantment_id, level)
        return result

    def has_enchantments(self) -> bool:
        return bool(self.get_enchantments())

    def get_enchantment_level(self, enchantment_id: str) -> int:
        from src.server.enchantments import normalize_enchantment_id

        try:
            wanted = normalize_enchantment_id(enchantment_id)
        except ValueError:
            return 0
        return self.get_enchantments().get(wanted, 0)

    def _get_enchantment_level(self, enchantment_id: str) -> int:
        """Compatibility alias for the former durability-only helper."""
        return self.get_enchantment_level(enchantment_id)

    def set_enchantment(self, enchantment_id: str, level: int) -> None:
        """Apply or replace one registered enchantment using canonical component NBT."""
        from src.server.enchantments import get_enchantment

        enchantment = get_enchantment(enchantment_id)
        if enchantment is None:
            raise ValueError(f"unknown enchantment: {enchantment_id}")
        level = enchantment.validate_level(level)
        if not enchantment.supports(self):
            raise ValueError(f"{enchantment.id} cannot be applied to this item")

        levels = self.get_enchantments()
        levels[enchantment.id] = level
        self.nbt.pop("enchantments", None)
        self.nbt.pop("Enchantments", None)
        component = self.nbt.get("minecraft:enchantments")
        show_in_tooltip = True
        if isinstance(component, dict):
            show_in_tooltip = bool(component.get("show_in_tooltip", True))
        updated_component = (
            dict(component)
            if isinstance(component, dict) and "levels" in component
            else {
                key: value
                for key, value in (component.items() if isinstance(component, dict) else ())
                if key in {"show_in_tooltip", "tooltip_display"}
            }
        )
        updated_component["levels"] = levels
        updated_component["show_in_tooltip"] = show_in_tooltip
        self.nbt["minecraft:enchantments"] = updated_component

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

    def draw_durability_bar(
        self, render, slot_x: float, slot_y: float, slot_size: float
    ) -> None:
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
        self, other: "ItemStack", *, require_full_fit: bool = True
    ) -> bool:
        """
        判断两个物品是否可以堆叠。

        ``require_full_fit=False`` 只检查材质和 NBT 兼容性，供允许部分
        转移的逻辑使用；默认值保留背包原先的“整堆必须能装下”语义。
        """
        compatible = self.material == other.material and self.nbt == other.nbt
        return compatible and (
            not require_full_fit or self.amount + other.amount <= self.max_stack_size
        )

    def get_attribute_modifiers(self, equipment_slot: str = "mainhand"):
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
                or entry_slot == "hand"
                and slot in {"mainhand", "offhand"}
                or entry_slot == "armor"
                and slot in {"head", "chest", "legs", "feet"}
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

        from src.server.enchantments import get_enchantment

        for enchantment_id, level in self.get_enchantments().items():
            enchantment = get_enchantment(enchantment_id)
            if enchantment is None:
                continue
            try:
                enchantment_entries = enchantment.get_attribute_modifiers(level)
            except (TypeError, ValueError):
                continue
            for entry in enchantment_entries:
                entry_slot = str(entry.get("slot", "any")).lower().replace("_", "")
                valid_slot = (
                    entry_slot == "any"
                    or entry_slot == slot
                    or entry_slot == "hand" and slot in {"mainhand", "offhand"}
                    or entry_slot == "armor"
                    and slot in {"head", "chest", "legs", "feet"}
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

    def stack_item(self, other: "ItemStack") -> bool:
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
    def get_base_texture(self, scale: float, client):
        """Return this stack's material/variant texture without enchantment glint."""
        stack_texture_getter = getattr(self.material, "get_stack_texture", None)
        if callable(stack_texture_getter):
            return stack_texture_getter(self, scale, client=client)
        return self.material.get_texture(scale, client=client)

    @client_method
    def get_texture(self, scale: float, client, shadow=False, multiply=1):
        animation_key = self.material.get_texture_animation_key()
        variant_getter = getattr(self.material, "get_texture_variant_key", None)
        variant_key = variant_getter(self) if callable(variant_getter) else None
        cache_key = (
            round(scale, 4),
            shadow,
            multiply,
            animation_key,
            variant_key,
        )
        px_scale = max(1, int(round(client.render.gui_scale)))
        res = self.get_base_texture(scale, client=client)
        if shadow and res is not None:
            cached = self.material.texture_cache.get(cache_key)
            if cached is not None:
                if not self.has_enchantments():
                    return cached
                result = cached.copy()
                result.blit(self._apply_enchantment_glint(res, client), (0, 0))
                return result

            # 创建带阴影的最终纹理
            width = res.get_width()
            height = res.get_height()

            # 创建一个更大的surface来容纳阴影偏移
            result = pygame.Surface(
                (width + px_scale, height + px_scale), pygame.SRCALPHA
            )

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

            if self.has_enchantments():
                result = result.copy()
                result.blit(self._apply_enchantment_glint(res, client), (0, 0))
            return result

        return self._apply_enchantment_glint(res, client)

    def get_texture_state_key(self, client):
        """Return every state that can change this stack's rendered texture."""
        animation_key = self.material.get_texture_animation_key(client=client)
        variant_getter = getattr(self.material, "get_texture_variant_key", None)
        variant_key = variant_getter(self) if callable(variant_getter) else None
        enchantments = tuple(sorted(self.get_enchantments().items()))
        glint_frame = None
        if enchantments:
            time_units, _, _ = self._get_glint_offsets(client)
            glint_frame = (
                time_units % self._glint_x_period_units,
                time_units % self._glint_y_period_units,
            )
        return animation_key, variant_key, enchantments, glint_frame

    def get_enchantment_glint_overlay(self, texture, client):
        """Return only the additive glint contribution for a separate render pass."""
        if texture is None or not self.has_enchantments():
            return None

        time_units, x_offset, y_offset = self._get_glint_offsets(client)
        glint_source = client.resources_manager.get_texture_img(
            "misc.enchanted_glint_item"
        )
        cache_key = (
            "overlay",
            texture,
            glint_source,
            self._glint_strength,
            self._glint_uv_scale,
            self._glint_rotation_degrees,
            time_units % self._glint_x_period_units,
            time_units % self._glint_y_period_units,
        )
        cached = self._glint_texture_cache.get(cache_key)
        if cached is not None:
            return cached

        width, height = texture.get_size()
        sampled_rgb, sampled_alpha = self._sample_glint_texture(
            glint_source,
            width,
            height,
            x_offset,
            y_offset,
        )
        overlay = self._source_color_glint_overlay(
            texture, sampled_rgb, sampled_alpha
        )
        self._glint_texture_cache[cache_key] = overlay
        if len(self._glint_texture_cache) > 256:
            self._glint_texture_cache.pop(next(iter(self._glint_texture_cache)))
        return overlay

    def _apply_enchantment_glint(self, texture, client):
        if texture is None or not self.has_enchantments():
            return texture

        time_units, x_offset, y_offset = self._get_glint_offsets(client)
        glint_source = client.resources_manager.get_texture_img(
            "misc.enchanted_glint_item"
        )
        cache_key = (
            texture,
            glint_source,
            self._glint_strength,
            self._glint_uv_scale,
            self._glint_rotation_degrees,
            time_units % self._glint_x_period_units,
            time_units % self._glint_y_period_units,
        )
        cached = self._glint_texture_cache.get(cache_key)
        if cached is not None:
            return cached

        width, height = texture.get_size()
        sampled_rgb, sampled_alpha = self._sample_glint_texture(
            glint_source,
            width,
            height,
            x_offset,
            y_offset,
        )
        result = self._source_color_additive_glint(
            texture, sampled_rgb, sampled_alpha
        )
        self._glint_texture_cache[cache_key] = result
        if len(self._glint_texture_cache) > 256:
            self._glint_texture_cache.pop(next(iter(self._glint_texture_cache)))
        return result

    @classmethod
    def _get_glint_offsets(cls, client):
        """Return vanilla's two wall-clock glint translations at a bounded frame rate."""
        try:
            elapsed_millis = max(
                0.0,
                float(
                    getattr(client, "glint_time_millis", pygame.time.get_ticks())
                ),
            )
        except (TypeError, ValueError):
            elapsed_millis = float(pygame.time.get_ticks())
        frame = int(elapsed_millis * cls._glint_frames_per_second / 1000.0)
        elapsed_millis = frame * 1000.0 / cls._glint_frames_per_second
        time_units = int(elapsed_millis * cls._glint_speed * 8.0)
        return (
            time_units,
            (time_units % cls._glint_x_period_units) / cls._glint_x_period_units,
            (time_units % cls._glint_y_period_units) / cls._glint_y_period_units,
        )

    @classmethod
    def _get_glint_coordinates(cls, width, height):
        cache_key = (width, height, cls._glint_uv_scale, cls._glint_rotation_degrees)
        cached = cls._glint_coordinate_cache.get(cache_key)
        if cached is not None:
            return cached

        u = (np.arange(width, dtype=np.float32) + 0.5) / max(1, width)
        v = (np.arange(height, dtype=np.float32) + 0.5) / max(1, height)
        scaled_u, scaled_v = np.meshgrid(
            u * cls._glint_uv_scale,
            v * cls._glint_uv_scale,
            indexing="ij",
        )
        angle = math.radians(cls._glint_rotation_degrees)
        cosine = math.cos(angle)
        sine = math.sin(angle)
        coordinates = (
            scaled_u * cosine - scaled_v * sine,
            scaled_u * sine + scaled_v * cosine,
        )
        cls._glint_coordinate_cache[cache_key] = coordinates
        if len(cls._glint_coordinate_cache) > 16:
            cls._glint_coordinate_cache.pop(
                next(iter(cls._glint_coordinate_cache))
            )
        return coordinates

    @classmethod
    def _sample_glint_texture(
        cls, source, width, height, x_offset, y_offset
    ):
        """Repeat and linearly sample the glint using vanilla's texture matrix."""
        base_u, base_v = cls._get_glint_coordinates(width, height)
        sample_u = np.mod(base_u - x_offset, 1.0)
        sample_v = np.mod(base_v + y_offset, 1.0)

        source_width, source_height = source.get_size()
        source_x = sample_u * source_width - 0.5
        source_y = sample_v * source_height - 0.5
        x0 = np.floor(source_x).astype(np.int32)
        y0 = np.floor(source_y).astype(np.int32)
        x1 = (x0 + 1) % source_width
        y1 = (y0 + 1) % source_height
        x0 %= source_width
        y0 %= source_height
        x_weight = (source_x - np.floor(source_x))[:, :, None]
        y_weight = (source_y - np.floor(source_y))[:, :, None]

        source_rgb = pygame.surfarray.array3d(source).astype(np.float32)
        top = source_rgb[x0, y0] * (1.0 - x_weight) + source_rgb[
            x1, y0
        ] * x_weight
        bottom = source_rgb[x0, y1] * (1.0 - x_weight) + source_rgb[
            x1, y1
        ] * x_weight
        sampled_rgb = top * (1.0 - y_weight) + bottom * y_weight

        if source.get_flags() & pygame.SRCALPHA:
            source_alpha = pygame.surfarray.array_alpha(source).astype(np.float32)
            x_weight_2d = x_weight[:, :, 0]
            y_weight_2d = y_weight[:, :, 0]
            top_alpha = source_alpha[x0, y0] * (1.0 - x_weight_2d) + source_alpha[
                x1, y0
            ] * x_weight_2d
            bottom_alpha = source_alpha[x0, y1] * (
                1.0 - x_weight_2d
            ) + source_alpha[x1, y1] * x_weight_2d
            sampled_alpha = top_alpha * (1.0 - y_weight_2d) + bottom_alpha * y_weight_2d
        else:
            sampled_alpha = np.full((width, height), 255.0, dtype=np.float32)
        return sampled_rgb, sampled_alpha

    @classmethod
    def _source_color_additive_glint(cls, texture, sampled_rgb, sampled_alpha):
        """Emulate vanilla's SRC_COLOR/ONE glint pass while preserving item alpha."""
        base_rgb = pygame.surfarray.array3d(texture).astype(np.float32)
        item_alpha = pygame.surfarray.array_alpha(texture).astype(np.float32)
        source_color = sampled_rgb * (cls._glint_strength / 255.0)
        contribution = source_color * source_color * 255.0
        fragment_visible = sampled_alpha >= 25.5
        coverage = (item_alpha / 255.0) * fragment_visible
        blended = np.clip(
            base_rgb + contribution * coverage[:, :, None], 0.0, 255.0
        )

        result = texture.copy()
        pygame.surfarray.blit_array(result, np.rint(blended).astype(np.uint8))
        result_alpha = pygame.surfarray.pixels_alpha(result)
        result_alpha[:] = item_alpha.astype(np.uint8)
        del result_alpha
        return result

    @classmethod
    def _source_color_glint_overlay(cls, texture, sampled_rgb, sampled_alpha):
        """Build the RGB contribution used by a later additive render pass."""
        item_alpha = pygame.surfarray.array_alpha(texture).astype(np.float32)
        source_color = sampled_rgb * (cls._glint_strength / 255.0)
        contribution = source_color * source_color * 255.0
        fragment_visible = sampled_alpha >= 25.5
        coverage = (item_alpha / 255.0) * fragment_visible
        overlay_rgb = np.clip(
            contribution * coverage[:, :, None], 0.0, 255.0
        )

        overlay = pygame.Surface(texture.get_size(), pygame.SRCALPHA)
        pygame.surfarray.blit_array(
            overlay, np.rint(overlay_rgb).astype(np.uint8)
        )
        overlay_alpha = pygame.surfarray.pixels_alpha(overlay)
        overlay_alpha[:] = item_alpha.astype(np.uint8)
        del overlay_alpha
        return overlay

    @client_method
    def get_gui_texture(self, gui_scale: float, client = None):
        """Return an icon sized and styled for an 18x18 GUI slot."""
        is_block_item = isinstance(self.material, BlockItem)
        scale = float(gui_scale) * (0.7 if is_block_item else 1.0)
        return self.get_texture(scale, shadow=is_block_item, client=client)

    def get_lore(self) -> list[str | Text]:
        lore = []
        if self.is_damageable() and self.get_damage() != 0:
            lore.append(
                Text(
                    f"durability: {self.get_max_damage() - self.get_damage()} / {self.get_max_damage()}"
                )
            )
        return lore


class EmptyItemStack(ItemStack):
    def __init__(self):
        super().__init__(materials.AIR(), 0)

    def is_empty(self) -> bool:
        """
        判断物品是否为空
        """
        return True
