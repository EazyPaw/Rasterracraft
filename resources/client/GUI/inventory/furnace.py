# Commented and arranged by ChatGPT
import pygame

from resources.client.GUI.inventory.backpack import Backpack
from resources.server.inventory import restore_inventory
from resources.server.smelting import find_smelting_recipe, is_fuel


class Furnace(Backpack):
    _texture_path = "gui.container.furnace"
    inventory_offset = (7, 84)
    furnace_offsets = ((56, 17), (56, 53), (116, 35))
    flame_offset = (56, 36)
    arrow_offset = (79, 34)

    def __init__(self, render, packet):
        super().__init__(render)
        del self.crafting_slots
        self.furnace_slots = [self._empty_stack() for _ in range(3)]
        self.container_id = str(packet.get("container", ""))
        self.quick_move_screen = f"container:{self.container_id}"
        self.burn_time = 0
        self.burn_time_total = 0
        self.cook_time = 0
        self.cook_time_total = 200
        self.lit = False
        self._server_closed = False
        self.apply_update(packet)

    @staticmethod
    def _is_crafting_slot(slot):
        return isinstance(slot, tuple) and len(slot) == 2 and slot[0] == "furnace"

    def _slot_descriptor(self, slot):
        if isinstance(slot, int):
            return "inventory", slot
        if self._is_crafting_slot(slot):
            return self.container_id, slot[1]
        return None

    def _get_slot_stack(self, slot):
        if self._is_crafting_slot(slot):
            return self.furnace_slots[slot[1]]
        return self.inventory[slot]

    def _set_slot_stack(self, slot, stack):
        if self._is_crafting_slot(slot):
            self.furnace_slots[slot[1]] = stack
        else:
            self.inventory[slot] = stack

    def _furnace_positions(self):
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        scale = self.render.gui_scale
        return [
            (x + offset_x * scale, y + offset_y * scale)
            for offset_x, offset_y in self.furnace_offsets
        ]

    def _craft_slot_at_pos(self, pos):
        size = self.slot_size * self.render.gui_scale
        for index, (x, y) in enumerate(self._furnace_positions()):
            if x <= pos[0] <= x + size and y <= pos[1] <= y + size:
                return "furnace", index
        return None

    def _refresh_crafting(self):
        return None

    def _slot_capacity(self, slot, source=None):
        if self._is_crafting_slot(slot):
            source = self.dragging_item if source is None else source
            if self._is_empty(source):
                return 0
            index = slot[1]
            if index == 2:
                return 0
            if index == 0:
                recipe = find_smelting_recipe(source)
                if recipe is None or recipe.create_result() is None:
                    return 0
            if index == 1 and not is_fuel(source):
                return 0
        return super()._slot_capacity(slot, source)

    def _finish_drag(self):
        inventory_slots = [slot for slot in self.drag_slots if isinstance(slot, int)]
        furnace_slots = [
            slot[1] for slot in self.drag_slots if self._is_crafting_slot(slot)
        ]
        if inventory_slots:
            self.render.client.sent_packet(
                {
                    "__class__": "ContainerDrag",
                    "container": "inventory",
                    "slots": inventory_slots,
                    "button": self.drag_button,
                }
            )
        if furnace_slots:
            self.render.client.sent_packet(
                {
                    "__class__": "ContainerDrag",
                    "container": self.container_id,
                    "slots": furnace_slots,
                    "button": self.drag_button,
                }
            )
        self._drag_material = None
        self._reset_drag()

    def _draw_progress_sprite(self, path, offset, ratio, *, bottom_up=False):
        ratio = max(0.0, min(1.0, float(ratio)))
        if ratio <= 0:
            return
        original = self.render.client.resources_manager.get_texture_img(path, True)
        if original is None:
            return
        scale = self.render.gui_scale
        width = max(1, round(original.get_width() * scale))
        height = max(1, round(original.get_height() * scale))
        sprite = pygame.transform.scale(original, (width, height))
        texture = self.get_texture(scale, self.render.client)
        gui_x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        gui_y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        x = gui_x + offset[0] * scale
        y = gui_y + offset[1] * scale
        if bottom_up:
            visible = max(1, round(height * ratio))
            self.render.blit(
                sprite.subsurface((0, height - visible, width, visible)),
                (x, y + height - visible),
            )
        else:
            visible = max(1, round(width * ratio))
            self.render.blit(sprite.subsurface((0, 0, visible, height)), (x, y))

    def _draw_crafting(self):
        texture = self.get_texture(
            self.render.gui_scale,
            self.render.client,
        )
        gui_x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        gui_y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        scale = self.render.gui_scale
        font_size = max(8, round(8 * scale))
        translate = self.render.client.resources_manager.get_translation_key
        self.render.render_text(
            translate("tile.furnace.name"),
            (gui_x + 8 * scale, gui_y + 6 * scale),
            (64, 64, 64),
            font_size,
        )
        self.render.render_text(
            translate("container.inventory"),
            (gui_x + 8 * scale, gui_y + 72 * scale),
            (64, 64, 64),
            font_size,
        )
        burn_ratio = (
            self.burn_time / self.burn_time_total if self.burn_time_total > 0 else 0.0
        )
        cook_ratio = (
            self.cook_time / self.cook_time_total if self.cook_time_total > 0 else 0.0
        )
        self._draw_progress_sprite(
            "gui.sprites.container.furnace.lit_progress",
            self.flame_offset,
            burn_ratio,
            bottom_up=True,
        )
        self._draw_progress_sprite(
            "gui.sprites.container.furnace.burn_progress",
            self.arrow_offset,
            cook_ratio,
        )

        hovered = self._craft_slot_at_pos(
            (self.render.mouse_x, self.render.mouse_y),
        )
        positions = self._furnace_positions()
        for index, pos in enumerate(positions):
            target = ("furnace", index)
            if target in self.drag_slots or target == hovered:
                self.render.blit(
                    self.selection_texture,
                    (pos[0] + self.render.gui_scale, pos[1] + self.render.gui_scale),
                )
            self._draw_crafting_stack(self.furnace_slots[index], pos)
        if self._is_crafting_slot(hovered):
            self.selecting_solt = hovered
            self.selecting_item = self.furnace_slots[hovered[1]]

    def apply_update(self, packet):
        if str(packet.get("container", self.container_id)) != self.container_id:
            return
        restore_inventory(self.furnace_slots, packet.get("slots", []))
        for key in (
            "burn_time",
            "burn_time_total",
            "cook_time",
            "cook_time_total",
        ):
            try:
                setattr(self, key, max(0, int(packet.get(key, getattr(self, key)))))
            except (TypeError, ValueError):
                pass
        self.cook_time_total = max(1, self.cook_time_total)
        self.lit = bool(packet.get("lit", self.burn_time > 0))

    def on_close(self):
        self._reset_drag()
        self._pressed_keys.clear()
        if not self._is_empty(self.dragging_item):
            self.dragging_item = self._empty_stack()
        if not self._server_closed:
            self.render.client.sent_packet(
                {
                    "__class__": "CloseFurnace",
                    "container": self.container_id,
                }
            )
        self.render.client.game_manager.release_game_input()
