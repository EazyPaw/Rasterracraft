"""Enchanting and anvil screens; clients only submit inventory actions."""
import pygame

from src.client.GUI.inventory.furnace import Furnace
from src.client.GUI.inventory.item_tooltip import ItemTooltip
from src.client.workstation_art import render_book
from src.server.enchanting import JavaRandom
from src.server.enchantments import get_enchantment
from src.server.inventory import restore_inventory


class Workstation(Furnace):
    inventory_offset = (7, 83)

    def __init__(self, render, packet):
        self.kind = packet.get("kind", "enchanting_table")
        self._texture_path = "gui.container." + self.kind
        self.furnace_offsets = ((26, 46), (75, 46), (133, 46)) if self.kind == "anvil" else ((14, 46), (34, 46))
        self.offers = []
        self.cost = 0
        self.bookshelves = 0
        self.item_name = ""
        self._name_focus = False
        self._editing_name = False
        self.glyph_seed = 0
        self._book_open = 0.0
        self._book_time = pygame.time.get_ticks()
        super().__init__(render, packet)
        self.furnace_slots = [self._empty_stack() for _ in self.furnace_offsets]
        self.apply_update(packet)

    def get_texture(self, size, client, path=None):
        if path is not None:
            return super().get_texture(size, client, path)
        # Container atlases include unused UV space; only display the 176x166 panel.
        original = client.resources_manager.get_texture_img(self._texture_path, True)
        if original is None:
            return super().get_texture(size, client)
        return pygame.transform.scale(original.subsurface((0, 0, 176, 166)),
                                      (round(176 * size), round(166 * size)))

    def _origin(self):
        scale = self.render.gui_scale
        return ((self.render.SCREEN_WIDTH - round(176 * scale)) // 2,
                (self.render.SCREEN_HEIGHT - round(166 * scale)) // 2, scale)

    def _rect(self, x, y, width, height):
        ox, oy, scale = self._origin()
        return pygame.Rect(round(ox + x * scale), round(oy + y * scale),
                           round(width * scale), round(height * scale))

    def _send_action(self, action, **fields):
        self.render.client.sent_packet({"__class__": "WorkstationAction",
            "container": self.container_id, "action": action, **fields})

    def _slot_capacity(self, slot, source=None):
        if not self._is_crafting_slot(slot):
            # Skip furnace smelting/fuel filters.
            from src.client.GUI.inventory.backpack import Backpack
            return Backpack._slot_capacity(self, slot, source)
        source = self.dragging_item if source is None else source
        if self._is_empty(source):
            return 0
        index = slot[1]
        if self.kind == "anvil" and index == 2:
            return 0
        if self.kind != "anvil" and index == 1 and source.material.name_id != "lapis_lazuli":
            return 0
        from src.client.GUI.inventory.backpack import Backpack
        capacity = Backpack._slot_capacity(self, slot, source)
        if self.kind != "anvil" and index == 0:
            return min(capacity, 1 if self._is_empty(self.furnace_slots[0]) else 0)
        return capacity

    def apply_update(self, packet):
        if str(packet.get("container", self.container_id)) != self.container_id:
            return
        restore_inventory(self.furnace_slots, packet.get("slots", []))
        signature = (self.furnace_slots[0].material.name_id, repr(self.furnace_slots[0].nbt))
        if signature != getattr(self, "_name_item_signature", None):
            self._editing_name = False
            self._name_item_signature = signature
        self.offers = packet.get("offers", [])
        self.cost = int(packet.get("cost", 0))
        self.bookshelves = int(packet.get("bookshelves", 0))
        self.glyph_seed = int(packet.get("glyph_seed", 0))
        if not self._editing_name:
            self.item_name = str(packet.get("name", ""))
            if not self.item_name and not self.furnace_slots[0].is_empty():
                self.item_name = self._translate(self.furnace_slots[0].material.name)

    def _text(self, text, x, y, color=(64, 64, 64), size=8):
        ox, oy, scale = self._origin()
        self.render.render_text(str(text), (ox + x * scale, oy + y * scale), color, max(8, round(size * scale)))

    def _translate(self, key):
        return self.render.client.resources_manager.get_translation_key(key)

    def _sprite(self, key, x, y, width, height):
        source = self.render.client.resources_manager.get_texture_img(key)
        rect = self._rect(x, y, width, height)
        self.render.blit(pygame.transform.scale(source, rect.size), rect.topleft)

    def _measure(self, text):
        return self.render.get_font(max(8, round(8 * self.render.gui_scale))).size(str(text))[0] / self.render.gui_scale

    def _draw_cell(self, stack, rect, hovered=False):
        scale = self.render.gui_scale
        if hovered:
            highlight = pygame.Surface((round(16 * scale), round(16 * scale)), pygame.SRCALPHA)
            highlight.fill((255, 255, 255, 128))
            self.render.blit(highlight, (rect.x + scale, rect.y + scale))
        if self._is_empty(stack):
            return
        icon = stack.get_gui_texture(scale, client=self.render.client)
        if icon is not None:
            # Slot coordinates describe the 18px frame; the icon occupies its
            # 16px interior. Never mix texture-atlas coordinates with hitboxes.
            limit = max(1, round(16 * scale))
            if icon.get_width() > limit or icon.get_height() > limit:
                ratio = min(limit / icon.get_width(), limit / icon.get_height())
                icon = pygame.transform.scale(icon, (max(1, round(icon.get_width() * ratio)), max(1, round(icon.get_height() * ratio))))
            self.render.blit(icon, (round(rect.centerx - icon.get_width() / 2), round(rect.centery - icon.get_height() / 2)))
            stack.draw_durability_bar(self.render, rect.x, rect.y, 18 * scale)
        if stack.amount > 1:
            label = str(stack.amount)
            self.render.render_text(label, (rect.right - scale - self._measure(label) * scale,
                                           rect.y + 9 * scale), (255, 255, 255),
                                    max(8, round(8 * scale)), shadow=True)

    def _craft_slot_at_pos(self, pos):
        for index, (x, y) in enumerate(self.furnace_offsets):
            if self._rect(x, y, 18, 18).collidepoint(pos):
                return "furnace", index
        return None

    def _slot_at_pos(self, pos):
        for row in range(4):
            for col in range(9):
                if self._rect(7 + col * 18, 83 + row * 18 + (4 if row == 3 else 0), 18, 18).collidepoint(pos):
                    return (3 - row) * 9 + col
        return None

    def _send_name(self):
        item = self.furnace_slots[0]
        name = self.item_name
        if not item.nbt.get("display", {}).get("Name") and name == self._translate(item.material.name):
            name = ""
        self._send_action("rename", name=name)

    def _draw_anvil(self):
        self._text(self._translate("container.repair"), 60, 6)
        occupied = not self.furnace_slots[0].is_empty()
        self._sprite("gui.sprites.container.anvil.text_field" + ("" if occupied else "_disabled"), 59, 20, 110, 16)
        rect = self._rect(62, 24, 103, 12)
        shown = self.item_name if occupied else ""
        if self._name_focus and occupied and pygame.time.get_ticks() % 1000 < 500:
            shown += "_"
        old_clip = self.render.screen.get_clip()
        self.render.screen.set_clip(rect)
        if self._name_focus and getattr(self, "_select_all_name", False):
            selection = pygame.Surface((min(rect.width, round(self._measure(shown) * self.render.gui_scale)), rect.height))
            selection.fill((0, 0, 170))
            self.render.blit(selection, rect.topleft)
        self._text(shown, 62, 24, (255, 255, 255))
        self.render.screen.set_clip(old_clip)
        result = not self.furnace_slots[2].is_empty()
        if (occupied or not self.furnace_slots[1].is_empty()) and not result:
            self._sprite("gui.sprites.container.anvil.error", 99, 45, 28, 21)
        if self.cost:
            player = self.render.client.client_player
            creative = getattr(player.game_mode, "name_id", "survival") == "creative"
            expensive = self.cost >= 40 and not creative
            if expensive or result:
                label = self._translate("container.repair.expensive") if expensive else self._translate("container.repair.cost").replace("%1$s", str(self.cost)).replace("%s", str(self.cost))
                x = 168 - self._measure(label)
                color = (255, 96, 96) if expensive or (not creative and player.experience_level < self.cost) else (128, 255, 32)
                backing = self._rect(x - 2, 66, self._measure(label) + 2, 10)
                pygame.draw.rect(self.render.screen, (50, 50, 50), backing)
                self._text(label, x, 67, color)

    def _glyph_words(self):
        # EnchantmentNameParts from MCP 919: decorative, unrelated to the roll.
        words = ("the elder scrolls klaatu berata niktu xyzzy bless curse light darkness fire air earth water hot dry cold wet ignite snuff embiggen twist shorten stretch fiddle destroy imbue galvanize enchant free limited range of towards inside sphere cube self other ball mental physical grow shrink demon elemental spirit animal creature beast humanoid undead fresh stale").split()
        rng = JavaRandom(self.glyph_seed)
        return [" ".join(words[rng.randrange(len(words))] for _ in range(rng.randrange(2) + 3)) for _ in range(3)]

    def _draw_glyphs(self, words, x, y, enabled, hovered):
        atlas = self.render.client.resources_manager.get_texture_img("font.ascii_sga")
        unit = atlas.get_width() // 16
        line, cursor = 0, 0
        color = (255, 255, 128) if hovered and enabled else (104, 89, 74) if enabled else (52, 44, 37)
        for word in words.split():
            if cursor and cursor + len(word) * 6 > 76:
                cursor, line = 0, line + 1
            if line >= 2:
                break
            for char in word:
                glyph = atlas.subsurface(((ord(char) % 16) * unit, (ord(char) // 16) * unit, unit, unit)).copy()
                glyph.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
                rect = self._rect(x + cursor, y + line * 9, 8, 8)
                self.render.blit(pygame.transform.scale(glyph, rect.size), rect.topleft)
                cursor += 6
            cursor += 6

    def _draw_enchanting(self):
        self._text(self._translate("container.enchant"), 12, 5)
        now = pygame.time.get_ticks()
        elapsed = max(0, min(200, now - self._book_time)) / 1000
        self._book_time = now
        target = 1.0 if any(offer.get("level", 0) for offer in self.offers) else 0.0
        self._book_open += max(-elapsed * 4, min(elapsed * 4, target - self._book_open))
        book = render_book(self.render.client.resources_manager, self._book_open, now // 80)
        book_rect = self._rect(6, 12, 52, 34)
        self.render.blit(pygame.transform.scale(book, book_rect.size), book_rect.topleft)
        if self.furnace_slots[1].is_empty():
            self._sprite("gui.sprites.container.slot.lapis_lazuli", 35, 47, 16, 16)
        player = self.render.client.client_player
        creative = getattr(player.game_mode, "name_id", "survival") == "creative"
        words = self._glyph_words()
        for index in range(3):
            offer = self.offers[index] if index < len(self.offers) else {}
            level = int(offer.get("level", 0))
            enabled = bool(level and offer.get("hint") and (creative or (
                player.experience_level >= level and self.furnace_slots[1].amount >= index + 1
                and self.furnace_slots[1].material.name_id == "lapis_lazuli")))
            hovered = self._rect(60, 14 + index * 19, 108, 19).collidepoint((self.render.mouse_x, self.render.mouse_y))
            sprite = "enchantment_slot_highlighted" if hovered and enabled else "enchantment_slot" if enabled else "enchantment_slot_disabled"
            self._sprite("gui.sprites.container.enchanting_table." + sprite, 60, 14 + index * 19, 108, 19)
            if level:
                self._sprite(f"gui.sprites.container.enchanting_table.level_{index + 1}" + ("" if enabled else "_disabled"), 61, 15 + index * 19, 16, 16)
                self._draw_glyphs(words[index], 80, 16 + index * 19, enabled, hovered)
                self._text(level, 166 - self._measure(level), 23 + index * 19,
                           (128, 255, 32) if enabled else (64, 128, 16))

    def enchantment_tooltip(self, index):
        offer = self.offers[index] if index < len(self.offers) else {}
        hint = offer.get("hint")
        level = int(offer.get("level", 0))
        if not hint or level <= 0:
            return []
        enchantment = get_enchantment(hint[0])
        name = self._translate(enchantment.translation_key) if enchantment else hint[0]
        if enchantment is None or enchantment.max_level != 1:
            name += " " + self._translate("enchantment.level." + str(hint[1]))
        lines = [(self._translate("container.enchant.clue").replace("%s", name), (255, 255, 255))]
        player = self.render.client.client_player
        if getattr(player.game_mode, "name_id", "survival") == "creative":
            return lines
        lines.append(("", (255, 255, 255)))
        if player.experience_level < level:
            label = self._translate("container.enchant.level.required").replace("%s", str(level))
            lines.append((label, (255, 85, 85)))
        else:
            amount = index + 1
            lapis = self._translate("container.enchant.lapis.one" if amount == 1 else "container.enchant.lapis.many").replace("%s", str(amount))
            enough = self.furnace_slots[1].material.name_id == "lapis_lazuli" and self.furnace_slots[1].amount >= amount
            lines.append((lapis, (170, 170, 170) if enough else (255, 85, 85)))
            levels = self._translate("container.enchant.level.one" if amount == 1 else "container.enchant.level.many").replace("%s", str(amount))
            lines.append((levels, (170, 170, 170)))
        return lines

    def _draw_option_tooltip(self):
        if self.kind != "enchanting_table":
            return
        for index in range(3):
            if not self._rect(60, 14 + index * 19, 108, 17).collidepoint((self.render.mouse_x, self.render.mouse_y)):
                continue
            lines = self.enchantment_tooltip(index)
            if not lines:
                return
            scale = self.render.gui_scale
            width = max(self._measure(line) for line, _ in lines) * scale
            line_height = 10 * scale
            panel, offset = ItemTooltip.create_panel((round(width), round(len(lines) * line_height)), max(1, round(scale)))
            x = self.render.mouse_x + round(12 * scale)
            if x + panel.get_width() > self.render.SCREEN_WIDTH:
                x = self.render.mouse_x - round(12 * scale) - panel.get_width()
            x = max(round(scale), x)
            y = max(round(scale), min(self.render.mouse_y - round(12 * scale), self.render.SCREEN_HEIGHT - panel.get_height() - round(scale)))
            self.render.blit(panel, (x, y))
            for row, (line, color) in enumerate(lines):
                self.render.render_text(line, (x + offset[0], y + offset[1] + row * line_height), color,
                                        max(8, round(8 * scale)), shadow=True)
            return

    def _draw_crafting(self):
        self._text(self._translate("container.inventory"), 8, 72)
        if self.kind == "anvil":
            self._draw_anvil()
        else:
            self._draw_enchanting()
        mouse = (self.render.mouse_x, self.render.mouse_y)
        hovered = self._craft_slot_at_pos(mouse)
        for index, (x, y) in enumerate(self.furnace_offsets):
            target = ("furnace", index)
            self._draw_cell(self.furnace_slots[index], self._rect(x, y, 18, 18), target == hovered or target in self.drag_slots)
        if self._is_crafting_slot(hovered):
            self.selecting_solt = hovered
            self.selecting_item = self.furnace_slots[hovered[1]]

    def draw(self):
        texture = self.get_texture(self.render.gui_scale, self.render.client)
        self.render.blit(self.render.ig_gui_layer, (0, 0))
        ox, oy, scale = self._origin()
        self.render.blit(texture, (ox, oy))
        self.selecting_solt = self.selecting_item = None
        self.solt_pos = []
        mouse = (self.render.mouse_x, self.render.mouse_y)
        for row in range(4):
            for col in range(9):
                rect = self._rect(7 + col * 18, 83 + row * 18 + (4 if row == 3 else 0), 18, 18)
                self.solt_pos.append(rect.topleft)
                index = (3 - row) * 9 + col
                self._draw_cell(self.inventory[index], rect, rect.collidepoint(mouse) or index in self.drag_slots)
                if rect.collidepoint(mouse):
                    self.selecting_solt, self.selecting_item = index, self.inventory[index]
        self._draw_crafting()
        if self._is_empty(self.dragging_item) and not self._is_empty(self.selecting_item):
            self.item_tooltip.draw(self.selecting_item, mouse)
        elif not self._is_empty(self.dragging_item):
            rect = pygame.Rect(round(mouse[0] - 9 * scale), round(mouse[1] - 9 * scale), round(18 * scale), round(18 * scale))
            self._draw_cell(self.dragging_item, rect)
        self._draw_option_tooltip()

    def handle_events(self, events):
        for event in list(events):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.kind == "enchanting_table":
                    for index in range(3):
                        if self._rect(60, 14 + index * 19, 108, 19).collidepoint(event.pos):
                            self._send_action("enchant", option=index)
                            events.remove(event)
                            break
                else:
                    self._name_focus = not self.furnace_slots[0].is_empty() and self._rect(59, 20, 110, 16).collidepoint(event.pos)
                    if self._name_focus:
                        self._editing_name = True
                        pygame.key.start_text_input()
                        events.remove(event)
            elif self.kind == "anvil" and self._name_focus:
                if event.type == pygame.TEXTINPUT:
                    if getattr(self, "_select_all_name", False):
                        self.item_name = ""
                        self._select_all_name = False
                    self.item_name = (self.item_name + event.text)[:30]
                    self._send_name()
                    self._editing_name = True
                    events.remove(event)
                elif event.type == pygame.KEYDOWN and event.key != pygame.K_ESCAPE:
                    if event.key == pygame.K_BACKSPACE:
                        mods = getattr(event, "mod", 0)
                        self.item_name = "" if mods & pygame.KMOD_CTRL or getattr(self, "_select_all_name", False) else self.item_name[:-1]
                        self._select_all_name = False
                        self._send_name()
                    elif event.key == pygame.K_a and getattr(event, "mod", 0) & pygame.KMOD_CTRL:
                        self._select_all_name = True
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self._name_focus = False
                        pygame.key.stop_text_input()
                    events.remove(event)
        super().handle_events(events)

    def on_close(self):
        self._reset_drag()
        self._pressed_keys.clear()
        pygame.key.stop_text_input()
        if not self._server_closed:
            self._send_action("close")
        self.render.client.game_manager.release_game_input()
