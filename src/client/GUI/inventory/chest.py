import pygame

from src.client.GUI.inventory.backpack import Backpack
from src.server.inventory import restore_inventory


class Chest(Backpack):
    """Single- or double-chest screen backed by a server-owned inventory."""

    _texture_path = "gui.container.generic_54"
    _background_cache = {}
    chest_offset = (7, 17)

    def __init__(self, render, packet):
        slots = packet.get("slots", [])
        try:
            rows = int(packet.get("rows", 6 if len(slots) > 27 else 3))
        except (TypeError, ValueError):
            rows = 3
        self.chest_rows = 6 if rows == 6 else 3
        self._background_height = 114 + self.chest_rows * 18
        self.inventory_offset = (7, self.chest_rows * 18 + 30)
        super().__init__(render)
        del self.crafting_slots
        self.chest_slots = [
            self._empty_stack() for _ in range(self.chest_rows * 9)
        ]
        self.container_id = str(packet.get("container", ""))
        self.quick_move_screen = f"container:{self.container_id}"
        self._server_closed = False
        self.apply_update(packet)

    def get_texture(self, size, client, path=None):
        if path is not None:
            return super().get_texture(size, client, path)
        size = float(size)
        cache_key = (size, id(client.resources_manager), self.chest_rows)
        cached = self._background_cache.get(cache_key)
        if cached is not None:
            return cached
        original = client.resources_manager.get_texture_img(self._texture_path, True)
        if original.get_width() < 176 or original.get_height() < 222:
            return pygame.transform.scale(
                original,
                (
                    max(1, round(original.get_width() * size)),
                    max(1, round(original.get_height() * size)),
                ),
            )
        if self.chest_rows == 6:
            background = original.copy()
        else:
            # generic_54 stores the six-row chest area above y=126 and the
            # fixed player-inventory area below it. Vanilla's three-row screen
            # keeps the first 71 pixels, then moves the lower section upward.
            background = pygame.Surface(
                (original.get_width(), self._background_height), pygame.SRCALPHA
            )
            chest_height = self.chest_rows * 18 + 17
            background.blit(
                original.subsurface((0, 0, original.get_width(), chest_height)),
                (0, 0),
            )
            lower_height = min(96, original.get_height() - 126)
            if lower_height > 0:
                background.blit(
                    original.subsurface(
                        (0, 126, original.get_width(), lower_height)
                    ),
                    (0, chest_height),
                )
        scaled = pygame.transform.scale(
            background,
            (
                max(1, round(background.get_width() * size)),
                max(1, round(background.get_height() * size)),
            ),
        )
        self._background_cache[cache_key] = scaled
        if len(self._background_cache) > 8:
            self._background_cache.pop(next(iter(self._background_cache)))
        return scaled

    @staticmethod
    def _is_crafting_slot(slot):
        return isinstance(slot, tuple) and len(slot) == 2 and slot[0] == "chest"

    def _slot_descriptor(self, slot):
        if isinstance(slot, int):
            return "inventory", slot
        if self._is_crafting_slot(slot):
            return self.container_id, slot[1]
        return None

    def _get_slot_stack(self, slot):
        if self._is_crafting_slot(slot):
            return self.chest_slots[slot[1]]
        return self.inventory[slot]

    def _set_slot_stack(self, slot, stack):
        if self._is_crafting_slot(slot):
            self.chest_slots[slot[1]] = stack
        else:
            self.inventory[slot] = stack

    def _chest_positions(self):
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        gui_x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        gui_y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        scale = self.render.gui_scale
        return [
            (
                gui_x + (self.chest_offset[0] + col * self.slot_size) * scale,
                gui_y + (self.chest_offset[1] + row * self.slot_size) * scale,
            )
            for row in range(self.chest_rows)
            for col in range(self.slot_cols)
        ]

    def _craft_slot_at_pos(self, pos):
        size = self.slot_size * self.render.gui_scale
        for index, (x, y) in enumerate(self._chest_positions()):
            if x <= pos[0] <= x + size and y <= pos[1] <= y + size:
                return "chest", index
        return None

    def _refresh_crafting(self):
        return None

    def _draw_equipment(self):
        return None

    def _finish_drag(self):
        inventory_slots = [slot for slot in self.drag_slots if isinstance(slot, int)]
        chest_slots = [
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
        if chest_slots:
            self.render.client.sent_packet(
                {
                    "__class__": "ContainerDrag",
                    "container": self.container_id,
                    "slots": chest_slots,
                    "button": self.drag_button,
                }
            )
        self._drag_material = None
        self._reset_drag()

    def _draw_crafting(self):
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        gui_x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        gui_y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        scale = self.render.gui_scale
        font_size = max(8, round(8 * scale))
        translate = self.render.client.resources_manager.get_translation_key
        self.render.render_text(
            translate(
                "container.chestDouble"
                if self.chest_rows == 6
                else "container.chest"
            ),
            (gui_x + 8 * scale, gui_y + 6 * scale),
            (64, 64, 64),
            font_size,
        )
        self.render.render_text(
            translate("container.inventory"),
            (
                gui_x + 8 * scale,
                gui_y + (self.chest_rows * 18 + 19) * scale,
            ),
            (64, 64, 64),
            font_size,
        )

        hovered = self._craft_slot_at_pos(
            (self.render.mouse_x, self.render.mouse_y)
        )
        for index, pos in enumerate(self._chest_positions()):
            target = ("chest", index)
            if target in self.drag_slots or target == hovered:
                self.render.blit(
                    self.selection_texture,
                    (pos[0] + scale, pos[1] + scale),
                )
            self._draw_crafting_stack(self.chest_slots[index], pos)
        if self._is_crafting_slot(hovered):
            self.selecting_solt = hovered
            self.selecting_item = self.chest_slots[hovered[1]]

    def apply_update(self, packet):
        if str(packet.get("container", self.container_id)) != self.container_id:
            return
        restore_inventory(self.chest_slots, packet.get("slots", []))

    def on_close(self):
        self._reset_drag()
        self._pressed_keys.clear()
        if not self._is_empty(self.dragging_item):
            self.dragging_item = self._empty_stack()
        if not self._server_closed:
            self.render.client.sent_packet(
                {
                    "__class__": "CloseChest",
                    "container": self.container_id,
                }
            )
        self.render.client.game_manager.release_game_input()
