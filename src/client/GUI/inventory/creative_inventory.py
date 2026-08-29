"""Minecraft-style creative catalogue with a survival-inventory tab."""

import math

import pygame

from src.client.GUI.inventory.backpack import Backpack
from src.server.item_class import ItemStack
from src.server.materials import (
    get_creative_inventory_materials,
    get_material_by_id,
)
from src.server.utils import reverse_search_dict


class CreativeInventory(Backpack):
    """Unsplit creative item catalogue backed by server-authoritative inventory."""

    _texture_path = "gui.container.creative_inventory.tab_items"
    _inventory_texture_path = "gui.container.creative_inventory.tab_inventory"
    _scroller_texture_path = "gui.sprites.container.creative_inventory.scroller"
    _scroller_disabled_texture_path = (
        "gui.sprites.container.creative_inventory.scroller_disabled"
    )
    _tab_texture_prefix = "gui.sprites.container.creative_inventory.tab_top"

    catalog_columns = 9
    catalog_rows = 5
    catalog_offset = (8, 17)
    hotbar_offset = (8, 111)
    survival_inventory_offset = (8, 52)
    scroll_offset = (175, 18)
    scroll_track_height = 90
    delete_offset = (173, 111)
    tab_stride = 28
    tab_y_offset = -28

    equipment_offsets = (
        ("offhand", (34, 19)),
        ("head", (53, 4)),
        ("chest", (53, 32)),
        ("legs", (107, 32)),
        ("feet", (107, 4)),
    )

    def __init__(self, render):
        super().__init__(render)
        self.active_tab = "items"
        self.catalog = []
        self.scroll_row = 0
        self._scroll_dragging = False
        self._scroll_drag_offset = 0
        self._rebuild_catalog()

    def _rebuild_catalog(self):
        self.catalog = [
            ItemStack(material, 1) for material in get_creative_inventory_materials()
        ]
        self.scroll_row = min(self.scroll_row, self._max_scroll_row())

    def _max_scroll_row(self):
        total_rows = math.ceil(len(self.catalog) / self.catalog_columns)
        return max(0, total_rows - self.catalog_rows)

    def _background_texture(self):
        path = (
            self._texture_path
            if self.active_tab == "items"
            else self._inventory_texture_path
        )
        return self.get_texture(self.render.gui_scale, self.render.client, path)

    def _gui_layout(self):
        texture = self._background_texture()
        x = (self.render.SCREEN_WIDTH - texture.get_width()) // 2
        y = (self.render.SCREEN_HEIGHT - texture.get_height()) // 2
        return texture, x, y

    def _catalog_positions(self, gui_x, gui_y):
        scale = self.render.gui_scale
        origin_x = gui_x + self.catalog_offset[0] * scale
        origin_y = gui_y + self.catalog_offset[1] * scale
        size = self.slot_size * scale
        start = self.scroll_row * self.catalog_columns
        for visible_index in range(self.catalog_columns * self.catalog_rows):
            index = start + visible_index
            if index >= len(self.catalog):
                break
            row, col = divmod(visible_index, self.catalog_columns)
            yield index, (origin_x + col * size, origin_y + row * size)

    def _inventory_positions(self, gui_x, gui_y, *, hotbar_only=False):
        scale = self.render.gui_scale
        size = self.slot_size * scale
        if not hotbar_only:
            origin_x = gui_x + self.survival_inventory_offset[0] * scale
            origin_y = gui_y + self.survival_inventory_offset[1] * scale
            for row in range(3):
                for col in range(9):
                    slot = (3 - row) * 9 + col
                    yield slot, (origin_x + col * size, origin_y + row * size)
        hotbar_x = gui_x + self.hotbar_offset[0] * scale
        hotbar_y = gui_y + self.hotbar_offset[1] * scale
        for slot in range(9):
            yield slot, (hotbar_x + slot * size, hotbar_y)

    def _equipment_positions(self, gui_x, gui_y):
        scale = self.render.gui_scale
        for slot, (offset_x, offset_y) in self.equipment_offsets:
            yield slot, (gui_x + offset_x * scale, gui_y + offset_y * scale)

    @staticmethod
    def _point_in_slot(pos, slot_pos, size):
        return (
            slot_pos[0] <= pos[0] <= slot_pos[0] + size
            and slot_pos[1] <= pos[1] <= slot_pos[1] + size
        )

    def _catalog_at_pos(self, pos, gui_x, gui_y):
        size = self.slot_size * self.render.gui_scale
        for index, slot_pos in self._catalog_positions(gui_x, gui_y):
            if self._point_in_slot(pos, slot_pos, size):
                return index
        return None

    def _inventory_at_pos(self, pos, gui_x, gui_y):
        size = self.slot_size * self.render.gui_scale
        hotbar_only = self.active_tab == "items"
        for slot, slot_pos in self._inventory_positions(
            gui_x, gui_y, hotbar_only=hotbar_only
        ):
            if self._point_in_slot(pos, slot_pos, size):
                return slot
        return None

    def _equipment_at_pos(self, pos, gui_x, gui_y):
        if self.active_tab != "inventory":
            return None
        size = self.slot_size * self.render.gui_scale
        for slot, slot_pos in self._equipment_positions(gui_x, gui_y):
            if self._point_in_slot(pos, slot_pos, size):
                return slot
        return None

    def _tab_at_pos(self, pos, gui_x, gui_y):
        scale = self.render.gui_scale
        for index, tab in enumerate(("items", "inventory")):
            rect = pygame.Rect(
                round(gui_x + index * self.tab_stride * scale),
                round(gui_y + self.tab_y_offset * scale),
                round(26 * scale),
                round(32 * scale),
            )
            if rect.collidepoint(pos):
                return tab
        return None

    def _delete_at_pos(self, pos, gui_x, gui_y):
        if self.active_tab != "inventory":
            return False
        scale = self.render.gui_scale
        return self._point_in_slot(
            pos,
            (
                gui_x + self.delete_offset[0] * scale,
                gui_y + self.delete_offset[1] * scale,
            ),
            self.slot_size * scale,
        )

    def _scroll_rect(self, gui_x, gui_y):
        scale = self.render.gui_scale
        top = gui_y + self.scroll_offset[1] * scale
        maximum = self._max_scroll_row()
        travel = (self.scroll_track_height - 15) * scale
        ratio = 0.0 if maximum == 0 else self.scroll_row / maximum
        return pygame.Rect(
            round(gui_x + self.scroll_offset[0] * scale),
            round(top + travel * ratio),
            round(12 * scale),
            round(15 * scale),
        )

    def _set_scroll_from_mouse(self, mouse_y, gui_y):
        maximum = self._max_scroll_row()
        if maximum <= 0:
            self.scroll_row = 0
            return
        scale = self.render.gui_scale
        top = gui_y + self.scroll_offset[1] * scale
        travel = (self.scroll_track_height - 15) * scale
        handle_y = max(top, min(top + travel, mouse_y - self._scroll_drag_offset))
        self.scroll_row = round((handle_y - top) / travel * maximum)

    def _draw_stack_at(self, stack, pos):
        self._draw_crafting_stack(stack, pos)

    def _draw_tabs(self, gui_x, gui_y):
        scale = self.render.gui_scale
        icons = (
            get_material_by_id("grass_block"),
            get_material_by_id("crafting_table"),
        )
        for index, (tab, icon_material) in enumerate(
            zip(("items", "inventory"), icons), start=1
        ):
            state = "selected" if self.active_tab == tab else "unselected"
            path = f"{self._tab_texture_prefix}_{state}_{index}"
            texture = self.get_texture(scale, self.render.client, path)
            tab_x = gui_x + (index - 1) * self.tab_stride * scale
            tab_y = gui_y + self.tab_y_offset * scale
            self.render.blit(texture, (tab_x, tab_y))
            icon = ItemStack(icon_material, 1).get_gui_texture(scale)
            if icon is not None:
                self.render.blit(
                    icon,
                    (
                        tab_x + (26 * scale - icon.get_width()) / 2,
                        tab_y + (28 * scale - icon.get_height()) / 2,
                    ),
                )

    def _draw_hover(self, pos):
        self.render.blit(
            self.selection_texture,
            (pos[0] + self.render.gui_scale, pos[1] + self.render.gui_scale),
        )

    def _draw_items_tab(self, gui_x, gui_y):
        mouse = (self.render.mouse_x, self.render.mouse_y)
        size = self.slot_size * self.render.gui_scale
        for index, pos in self._catalog_positions(gui_x, gui_y):
            stack = self.catalog[index]
            if self._point_in_slot(mouse, pos, size):
                self._draw_hover(pos)
                self.selecting_solt = ("catalog", index)
                self.selecting_item = stack
            self._draw_stack_at(stack, pos)

        self._draw_inventory_slots(gui_x, gui_y, hotbar_only=True)
        path = (
            self._scroller_disabled_texture_path
            if self._max_scroll_row() == 0
            else self._scroller_texture_path
        )
        scroller = self.get_texture(self.render.gui_scale, self.render.client, path)
        self.render.blit(scroller, self._scroll_rect(gui_x, gui_y).topleft)

    def _draw_inventory_slots(self, gui_x, gui_y, *, hotbar_only=False):
        mouse = (self.render.mouse_x, self.render.mouse_y)
        size = self.slot_size * self.render.gui_scale
        for slot, pos in self._inventory_positions(
            gui_x, gui_y, hotbar_only=hotbar_only
        ):
            if self._point_in_slot(mouse, pos, size):
                self._draw_hover(pos)
                self.selecting_solt = slot
                self.selecting_item = self.inventory[slot]
            self._draw_stack_at(self.inventory[slot], pos)

    def _draw_inventory_tab(self, gui_x, gui_y):
        self._draw_inventory_slots(gui_x, gui_y)
        mouse = (self.render.mouse_x, self.render.mouse_y)
        size = self.slot_size * self.render.gui_scale
        for slot, pos in self._equipment_positions(gui_x, gui_y):
            stack = self.render.client.client_player.equipment[slot]
            if self._point_in_slot(mouse, pos, size):
                self._draw_hover(pos)
                self.selecting_solt = ("equipment", slot)
                self.selecting_item = stack
            self._draw_stack_at(stack, pos)

    def _draw_cursor(self):
        if self._is_empty(self.dragging_item):
            return
        texture = self.dragging_item.get_gui_texture(self.render.gui_scale)
        if texture is None:
            return
        pos = (
            self.render.mouse_x - texture.get_width() / 2,
            self.render.mouse_y - texture.get_height() / 2,
        )
        self.render.blit(texture, pos)
        slot_size = self.slot_size * self.render.gui_scale
        self.dragging_item.draw_durability_bar(
            self.render,
            self.render.mouse_x - slot_size / 2,
            self.render.mouse_y - slot_size / 2,
            slot_size,
        )
        if self.dragging_item.amount > 1:
            self.render.render_text(
                str(self.dragging_item.amount),
                (
                    self.render.mouse_x + texture.get_width() / 4,
                    self.render.mouse_y + texture.get_height() / 4,
                ),
                (255, 255, 255),
                int(20 * self.render.gui_scale / 3.5),
                True,
            )

    def draw(self):
        texture, gui_x, gui_y = self._gui_layout()
        self.render.blit(self.render.ig_gui_layer, (0, 0))
        self.render.blit(texture, (gui_x, gui_y))
        self.selecting_solt = None
        self.selecting_item = None
        if self.active_tab == "items":
            self._draw_items_tab(gui_x, gui_y)
        else:
            self._draw_inventory_tab(gui_x, gui_y)
        self._draw_tabs(gui_x, gui_y)
        if self._is_empty(self.dragging_item) and not self._is_empty(
            self.selecting_item
        ):
            self.item_tooltip.draw(
                self.selecting_item,
                (self.render.mouse_x, self.render.mouse_y),
            )
        self._draw_cursor()

    def _inventory_target_at_pos(self, pos):
        _texture, gui_x, gui_y = self._gui_layout()
        return self._inventory_at_pos(pos, gui_x, gui_y)

    def _finish_inventory_drag(self, event):
        slot = self._inventory_target_at_pos(event.pos)
        self._add_drag_slot(slot)
        if self.drag_moved and self.drag_slots:
            self._finish_drag()
        else:
            if self.drag_start_slot is not None:
                if event.button == 1:
                    self._left_click_slot(self.drag_start_slot)
                else:
                    self._right_click_slot(self.drag_start_slot)
            elif slot is None:
                self._handle_click_outside(event.button)
            self._reset_drag()

    def _take_catalog_item(self, index, button):
        stack = self.catalog[index]
        if button == 1 and not self._is_empty(self.dragging_item):
            self.render.client.client_player.set_creative_cursor("air", 0)
            return
        amount = stack.max_stack_size if button == 2 else 1
        self.render.client.client_player.set_creative_cursor(
            stack.material.name_id,
            amount,
            stack.nbt,
        )

    def _handle_inventory_mouse_down(self, event, slot):
        if self._is_empty(self.dragging_item):
            if event.button == 1:
                self._left_click_slot(slot)
            else:
                self._right_click_slot(slot)
            self._reset_drag()
        else:
            self._start_drag(event.button, slot)

    def _close_key(self, event):
        return event.key == pygame.K_ESCAPE or event.key in reverse_search_dict(
            self.render.client.key_map,
            self.render.client.client_player.game_mode.open_inventory,
        )

    def handle_events(self, events):
        for event in events[:]:
            _texture, gui_x, gui_y = self._gui_layout()
            if event.type == pygame.MOUSEWHEEL and self.active_tab == "items":
                self.scroll_row = max(
                    0,
                    min(self._max_scroll_row(), self.scroll_row - event.y),
                )
                events.remove(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                tab = self._tab_at_pos(event.pos, gui_x, gui_y)
                if event.button == 1 and tab is not None:
                    self.active_tab = tab
                    self._scroll_dragging = False
                    self._reset_drag()
                    events.remove(event)
                    continue
                if (
                    self.active_tab == "items"
                    and event.button == 1
                    and self._scroll_rect(gui_x, gui_y).collidepoint(event.pos)
                ):
                    self._scroll_dragging = True
                    self._scroll_drag_offset = event.pos[1] - self._scroll_rect(
                        gui_x, gui_y
                    ).top
                    events.remove(event)
                    continue
                if event.button not in (1, 2, 3):
                    continue
                catalog_index = (
                    self._catalog_at_pos(event.pos, gui_x, gui_y)
                    if self.active_tab == "items"
                    else None
                )
                if catalog_index is not None:
                    self._take_catalog_item(catalog_index, event.button)
                    self._reset_drag()
                    events.remove(event)
                    continue
                if self._delete_at_pos(event.pos, gui_x, gui_y):
                    mods = getattr(event, "mod", None)
                    if mods is None:
                        mods = pygame.key.get_mods()
                    if event.button == 1 and mods & pygame.KMOD_SHIFT:
                        self.render.client.client_player.clear_creative_inventory()
                    else:
                        self.render.client.client_player.set_creative_cursor("air", 0)
                    self._reset_drag()
                    events.remove(event)
                    continue
                inventory_slot = self._inventory_at_pos(event.pos, gui_x, gui_y)
                if inventory_slot is not None and event.button in (1, 3):
                    mods = getattr(event, "mod", None)
                    if mods is None:
                        mods = pygame.key.get_mods()
                    if mods & pygame.KMOD_SHIFT:
                        self.render.client.client_player.set_creative_slot(
                            inventory_slot, "air", 0
                        )
                    else:
                        self._handle_inventory_mouse_down(event, inventory_slot)
                    events.remove(event)
                    continue
                equipment_slot = self._equipment_at_pos(event.pos, gui_x, gui_y)
                if equipment_slot is not None and event.button in (1, 3):
                    self.render.client.sent_packet(
                        {
                            "__class__": "ContainerClick",
                            "container": "equipment",
                            "slot": equipment_slot,
                            "button": event.button,
                        }
                    )
                    events.remove(event)
                    continue
                if not self._is_empty(self.dragging_item) and event.button in (1, 3):
                    self._handle_click_outside(event.button)
                    self._reset_drag()
                    events.remove(event)
            elif event.type == pygame.MOUSEMOTION:
                if self._scroll_dragging:
                    self._set_scroll_from_mouse(event.pos[1], gui_y)
                    events.remove(event)
                elif self.drag_button in (1, 3):
                    self._add_drag_slot(self._inventory_at_pos(event.pos, gui_x, gui_y))
                    events.remove(event)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and self._scroll_dragging:
                    self._scroll_dragging = False
                    events.remove(event)
                elif event.button in (1, 3) and self.drag_button == event.button:
                    self._finish_inventory_drag(event)
                    events.remove(event)
            elif event.type == pygame.KEYDOWN:
                self._pressed_keys.add(event.key)
                if self._close_key(event):
                    self.render.close_gui(self)
                    events.remove(event)
                elif pygame.K_1 <= event.key <= pygame.K_9:
                    preset = event.key - pygame.K_1
                    catalog_index = (
                        self.selecting_solt[1]
                        if isinstance(self.selecting_solt, tuple)
                        and self.selecting_solt[0] == "catalog"
                        else None
                    )
                    if pygame.K_c in self._pressed_keys:
                        self.render.client.sent_packet(
                            {"__class__": "SaveHotbar", "preset": preset}
                        )
                    elif pygame.K_x in self._pressed_keys:
                        self.render.client.sent_packet(
                            {"__class__": "LoadHotbar", "preset": preset}
                        )
                    elif catalog_index is not None:
                        stack = self.catalog[catalog_index]
                        self.render.client.client_player.set_creative_slot(
                            preset,
                            stack.material.name_id,
                            stack.max_stack_size,
                            stack.nbt,
                        )
                    elif isinstance(self.selecting_solt, int):
                        self._send_slot_swap(
                            self.selecting_solt, "inventory", preset
                        )
                    events.remove(event)
                elif event.key == pygame.K_q:
                    mods = getattr(event, "mod", None)
                    if mods is None:
                        mods = pygame.key.get_mods()
                    single = not bool(mods & pygame.KMOD_CTRL)
                    if not self._is_empty(self.dragging_item):
                        self._drop_cursor_item(single=single)
                    elif isinstance(self.selecting_solt, int):
                        self._drop_slot_item(self.selecting_solt, single=single)
                    events.remove(event)
                elif event.key == pygame.K_f and isinstance(self.selecting_solt, int):
                    self._send_slot_swap(
                        self.selecting_solt, "equipment", "offhand"
                    )
                    events.remove(event)
                elif event.key in (pygame.K_c, pygame.K_x):
                    events.remove(event)
            elif event.type == pygame.KEYUP:
                self._pressed_keys.discard(event.key)

    def on_open(self):
        self._rebuild_catalog()
        cursor = getattr(
            self.render.client.client_player,
            "inventory_cursor",
            self.dragging_item,
        )
        self.dragging_item = cursor
        self.render.client.game_manager.acquire_game_input()

    def on_close(self):
        self._scroll_dragging = False
        self._reset_drag()
        self._pressed_keys.clear()
        self.render.client.game_manager.release_game_input()
