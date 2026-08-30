# Commented and arranged by ChatGPT
import re

import pygame

from src.client.resources_manager import transkey
from src.server.attributes import AttributeOperation, normalize_id
from src.server.enchantments import get_enchantment
from src.server.text import Text, TextColor


class ItemTooltip:
    _panel_cache: dict[
        tuple[int, int, int], tuple[pygame.Surface, tuple[int, int]]
    ] = {}
    BACKGROUND_TOP = (16, 0, 20, 240)
    BACKGROUND_BOTTOM = (16, 0, 16, 240)
    BORDER_TOP = (80, 0, 255, 80)
    BORDER_BOTTOM = (40, 0, 127, 80)

    def __init__(self, render):
        self.render = render

    @staticmethod
    def _split_line(value: str | Text) -> list[str | Text]:
        if not isinstance(value, Text):
            return str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")

        rows: list[Text] = []
        current: list[dict] = []
        for segment in value.text:
            color = segment.get("color", TextColor.WHITE)
            bold = bool(segment.get("bold", False))
            pieces = (
                str(segment.get("text", ""))
                .replace("\r\n", "\n")
                .replace("\r", "\n")
                .split("\n")
            )
            for index, piece in enumerate(pieces):
                if piece:
                    current.append({"text": piece, "color": color, "bold": bold})
                if index < len(pieces) - 1:
                    rows.append(Text(current))
                    current = []
        rows.append(Text(current))
        return rows

    def _translated_name(self, stack) -> str:
        raw_name = str(stack.get_name())
        resources = self.render.client.resources_manager

        if raw_name in resources._lang_map or raw_name in resources._fallback_lang_map:
            return transkey(raw_name, client=self.render.client)
        return raw_name

    @staticmethod
    def _namespaced_id(stack) -> str:
        material = stack.material
        item_id = str(getattr(material, "name_id", "air"))
        if ":" in item_id:
            return item_id
        namespace = str(getattr(material, "name_space_key", "minecraft") or "minecraft")
        return f"{namespace}:{item_id}"

    def _attribute_lines(self, stack) -> list[Text]:
        get_modifiers = getattr(stack, "get_attribute_modifiers", None)
        if not callable(get_modifiers):
            return []

        lines = []
        totals: dict[tuple[str, AttributeOperation], float] = {}
        material = getattr(stack, "material", None)
        equipment_slot = getattr(material, "equipment_slot", "mainhand")
        names = {
            "minecraft:attack_damage": "attribute.name.generic.attackDamage",
            "minecraft:armor": "attribute.name.generic.armor",
            "minecraft:armor_toughness": "attribute.name.generic.armorToughness",
        }
        for attribute_id, modifier in get_modifiers(equipment_slot):
            normalized_id = normalize_id(attribute_id)
            translation_key = names.get(normalized_id)
            if translation_key is None:
                continue
            key = (normalized_id, modifier.operation)
            totals[key] = totals.get(key, 0.0) + float(modifier.amount)

        for (normalized_id, operation), raw_amount in totals.items():
            translation_key = names[normalized_id]
            attribute_name = transkey(translation_key, client=self.render.client)
            if attribute_name == translation_key:
                attribute_name = {
                    "minecraft:armor": "Armor",
                    "minecraft:armor_toughness": "Armor Toughness",
                }.get(normalized_id, attribute_name)
            amount = raw_amount
            if operation is not AttributeOperation.ADD_VALUE:
                amount *= 100.0
            if amount == 0.0:
                continue
            operation_index = {
                AttributeOperation.ADD_VALUE: 0,
                AttributeOperation.ADD_MULTIPLIED_BASE: 1,
                AttributeOperation.ADD_MULTIPLIED_TOTAL: 2,
            }[operation]
            sign = "plus" if amount > 0.0 else "take"
            description_key = f"attribute.modifier.{sign}.{operation_index}"
            resources = self.render.client.resources_manager
            template = resources._lang_map.get(
                description_key,
                resources._fallback_lang_map.get(description_key, description_key),
            )
            # The bundled 1.8 English language file uses ``%d`` here, but
            # enchantments can make the combined attribute fractional (8.25).
            # Preserve localization/order while allowing that precise value.
            template = re.sub(r"%(\d+\$)?[di]", r"%\1s", template)
            description = resources._format_translation(
                template, (f"{abs(amount):g}", attribute_name)
            )
            lines.append(
                Text(description, TextColor.BLUE if amount > 0.0 else TextColor.RED)
            )
        return lines

    def _enchantment_lines(self, stack) -> list[Text]:
        component = getattr(stack, "nbt", {}).get("minecraft:enchantments")
        if isinstance(component, dict) and not bool(
            component.get("show_in_tooltip", True)
        ):
            return []

        lines = []
        for enchantment_id, level in stack.get_enchantments().items():
            enchantment = get_enchantment(enchantment_id)
            if enchantment is None:
                name = enchantment_id
            else:
                name = transkey(enchantment.translation_key, client=self.render.client)
            level_name = transkey(
                f"enchantment.level.{level}", client=self.render.client
            )
            if level_name == f"enchantment.level.{level}":
                level_name = str(level)
            lines.append(Text(f"{name} {level_name}", TextColor.GRAY))
        return lines

    def _attack_damage_lines(self, stack) -> list[Text]:
        """Compatibility helper retained for callers of the former method."""
        return self._attribute_lines(stack)

    def get_lines(self, stack) -> list[str | Text]:
        translated_name = self._translated_name(stack)
        lines: list[str | Text] = [
            Text(translated_name, TextColor.AQUA)
            if stack.has_enchantments()
            else translated_name
        ]
        lines.extend(self._enchantment_lines(stack))
        lore = stack.get_lore()
        if lore is not None:
            for entry in lore:
                if isinstance(entry, (str, Text)):
                    lines.extend(self._split_line(entry))
                else:
                    lines.extend(self._split_line(str(entry)))
        attribute_lines = self._attribute_lines(stack)
        if attribute_lines:
            lines.append("")
            lines.extend(attribute_lines)
        lines.append(Text(self._namespaced_id(stack), TextColor.DARK_GRAY))
        return lines

    def _font_size(self) -> int:
        return max(14, round(8 * self.render.gui_scale))

    def _line_width(self, line: str | Text, font_size: int) -> int:
        if not isinstance(line, Text):
            return self.render.get_font(font_size).size(str(line))[0]
        return sum(
            self.render.get_font(font_size, bool(segment.get("bold", False))).size(
                str(segment.get("text", ""))
            )[0]
            for segment in line.text
        )

    @staticmethod
    def _lerp_color(start, end, progress: float):
        return tuple(round(a + (b - a) * progress) for a, b in zip(start, end))

    @classmethod
    def _vertical_gradient(cls, surface, rect: pygame.Rect, top, bottom) -> None:
        if rect.width <= 0 or rect.height <= 0:
            return
        denominator = max(1, rect.height - 1)
        for offset in range(rect.height):
            color = cls._lerp_color(top, bottom, offset / denominator)
            surface.fill(color, (rect.x, rect.y + offset, rect.width, 1))

    @classmethod
    def create_panel(
        cls, content_size: tuple[int, int], pixel: int
    ) -> tuple[pygame.Surface, tuple[int, int]]:
        pixel = max(1, int(pixel))
        content_width, content_height = content_size
        cache_key = (content_width, content_height, pixel)
        cached = cls._panel_cache.get(cache_key)
        if cached is not None:
            return cached
        width = max(pixel * 8 + 1, content_width + pixel * 8)
        height = max(pixel * 8 + 1, content_height + pixel * 8)
        panel = pygame.Surface((width, height), pygame.SRCALPHA)

        cls._vertical_gradient(
            panel,
            pygame.Rect(pixel, 0, width - pixel * 2, height),
            cls.BACKGROUND_TOP,
            cls.BACKGROUND_BOTTOM,
        )
        cls._vertical_gradient(
            panel,
            pygame.Rect(0, pixel, width, height - pixel * 2),
            cls.BACKGROUND_TOP,
            cls.BACKGROUND_BOTTOM,
        )

        border = pygame.Surface((width, height), pygame.SRCALPHA)
        border.fill(cls.BORDER_TOP, (pixel, pixel, width - pixel * 2, pixel))
        border.fill(
            cls.BORDER_BOTTOM,
            (pixel, height - pixel * 2, width - pixel * 2, pixel),
        )
        cls._vertical_gradient(
            border,
            pygame.Rect(pixel, pixel * 2, pixel, height - pixel * 4),
            cls.BORDER_TOP,
            cls.BORDER_BOTTOM,
        )
        cls._vertical_gradient(
            border,
            pygame.Rect(width - pixel * 2, pixel * 2, pixel, height - pixel * 4),
            cls.BORDER_TOP,
            cls.BORDER_BOTTOM,
        )
        panel.blit(border, (0, 0))
        result = panel, (pixel * 4, pixel * 4)
        cls._panel_cache[cache_key] = result
        if len(cls._panel_cache) > 64:
            cls._panel_cache.pop(next(iter(cls._panel_cache)))
        return result

    def draw(self, stack, mouse_pos: tuple[float, float]) -> None:
        if stack is None or stack.is_empty():
            return

        lines = self.get_lines(stack)
        font_size = self._font_size()
        font = self.render.get_font(font_size)
        line_height = font.get_linesize()
        line_gap = max(1, round(self.render.gui_scale * 2))
        content_width = max(self._line_width(line, font_size) for line in lines)
        content_height = len(lines) * line_height + max(0, len(lines) - 1) * line_gap
        pixel = max(1, round(self.render.gui_scale))
        panel, content_offset = self.create_panel(
            (content_width, content_height), pixel
        )

        mouse_x, mouse_y = mouse_pos
        cursor_gap = pixel * 3
        x = round(mouse_x + cursor_gap)
        y = round(mouse_y - cursor_gap)
        screen_margin = pixel
        if x + panel.get_width() > self.render.SCREEN_WIDTH - screen_margin:
            x = round(mouse_x - cursor_gap - panel.get_width())
        if y + panel.get_height() > self.render.SCREEN_HEIGHT - screen_margin:
            y = self.render.SCREEN_HEIGHT - screen_margin - panel.get_height()
        x = max(screen_margin, x)
        y = max(screen_margin, y)

        self.render.blit(panel, (x, y))
        text_x = x + content_offset[0]
        text_y = y + content_offset[1]
        for index, line in enumerate(lines):
            self.render.render_text(
                line,
                (text_x, text_y + index * (line_height + line_gap)),
                (255, 255, 255),
                font_size,
                shadow=True,
                shadow_strength=0.25,
            )
