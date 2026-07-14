import datetime as _datetime
import time

import pygame

from resources.client.resources_manager import transkey
from resources.server import save_manager
from resources.client.GUI.button import Button
from resources.client.GUI.gui import GUI
from resources.client.GUI.input_box import InputBox
from resources.server.utils import client_method


class SavesMenu(GUI):
    """Minecraft-style single player world selection menu."""

    @client_method
    def __init__(self, render, main_menu=None, client=None):
        super().__init__(render)
        self.client = client
        self.priority = 100
        self.main_menu = main_menu
        self.saves: list[dict] = []
        self.selected_id: str | None = None
        self.scroll = 0
        self.starting_world = False
        self.confirm_delete_id: str | None = None
        self._entry_rects: list[tuple[pygame.Rect, dict]] = []
        self._last_click_id: str | None = None
        self._last_click_time = 0.0
        self._background_cache = None
        self._background_cache_key = None
        self._preview_cache: dict[tuple, pygame.Surface] = {}

        self.search_box = InputBox(
            "",
            placeholder="",
            max_length=64,
            on_change=lambda _text: self._on_search_changed(),
        )
        self.enter_button = Button(transkey("selectWorld.select"), self.start_selected)
        self.create_button = Button(transkey("selectWorld.create"), self.create_world)
        self.edit_button = Button(transkey("selectServer.edit"), enabled=False)
        self.delete_button = Button(transkey("selectWorld.delete"), self.delete_selected)
        self.recreate_button = Button(transkey("selectWorld.recreate"), enabled=False)
        self.back_button = Button(transkey("gui.back"), self.back)
        self.buttons = [
            self.enter_button,
            self.create_button,
            self.edit_button,
            self.delete_button,
            self.recreate_button,
            self.back_button,
        ]
        self._load_saves()

    def _load_saves(self, select_id: str | None = None):
        self.saves = save_manager.list_saves()
        ids = [save["id"] for save in self.filtered_saves()]
        if select_id in ids:
            self.selected_id = select_id
        elif self.selected_id not in ids:
            self.selected_id = ids[0] if ids else None
        self.confirm_delete_id = None
        self._update_buttons()

    def filtered_saves(self) -> list[dict]:
        query = self.search_box.text.strip().lower()
        if not query:
            return self.saves
        return [
            save for save in self.saves
            if query in str(save.get("display_name", "")).lower()
            or query in str(save.get("id", "")).lower()
        ]

    def draw(self):
        self._layout()
        self._draw_background()
        self._draw_title()
        self.search_box.draw(self.render)
        self._draw_list()
        self._draw_bottom_bar()
        for button in self.buttons:
            button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]):
        self._layout()
        for event in events[:]:
            if self.search_box.handle_event(event):
                events.remove(event)
                continue

            handled = False
            if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
                for button in self.buttons:
                    if button.handle_event(event):
                        handled = True
                if handled:
                    events.remove(event)
                    continue

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self._handle_list_click(event.pos):
                    events.remove(event)
                    continue
            elif event.type == pygame.MOUSEWHEEL:
                self._scroll_by(-event.y)
                events.remove(event)
                continue
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.back()
                    events.remove(event)
                    continue
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self.start_selected()
                    events.remove(event)
                    continue
                if event.key == pygame.K_DELETE:
                    self.delete_selected()
                    events.remove(event)
                    continue
                if event.key in (pygame.K_UP, pygame.K_w):
                    self._move_selection(-1)
                    events.remove(event)
                    continue
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    self._move_selection(1)
                    events.remove(event)
                    continue

    def start_selected(self):
        if self.starting_world or not self.selected_id:
            return
        self.starting_world = True
        for button in self.buttons:
            button.enabled = False
        self.enter_button.text = transkey("menu.loadingLevel")
        self.search_box.blur()
        self.render.client.start_game(self.selected_id)

    def create_world(self):
        if self.starting_world:
            return
        name = self._next_world_name()
        data = save_manager.create_save(
            name,
            version=getattr(self.render.client, "version", ""),
            game_mode="survival",
        )
        self._load_saves(data["id"])
        self.start_selected()

    def delete_selected(self):
        if self.starting_world or not self.selected_id:
            return
        if self.confirm_delete_id != self.selected_id:
            self.confirm_delete_id = self.selected_id
            self.delete_button.text = transkey("selectWorld.deleteButton")
            return
        save_manager.delete_save(self.selected_id)
        self.selected_id = None
        self.scroll = 0
        self._load_saves()

    def back(self):
        if self.starting_world:
            return
        self.search_box.blur()
        self.render.close_gui(self)
        if self.main_menu is not None:
            self.render.show_gui(self.main_menu)

    def _layout(self):
        w = self.render.SCREEN_WIDTH
        h = self.render.SCREEN_HEIGHT
        self.list_w = min(950, max(360, int(w * 0.70)))
        self.list_x = (w - self.list_w) // 2
        self.title_font = max(24, min(42, int(h * 0.052)))
        search_w = min(800, max(320, int(w * 0.55)))
        search_h = max(34, min(54, int(h * 0.07)))
        search_y = max(54, int(h * 0.085))
        self.search_box.set_rect((w - search_w) // 2, search_y, search_w, search_h)

        self.list_top = search_y + search_h + max(24, int(h * 0.045))
        self.bottom_top = h - max(120, int(h * 0.22))
        self.list_bottom = self.bottom_top - 12
        self.entry_h = max(70, min(98, int(h * 0.13)))
        self.preview_size = max(58, min(84, self.entry_h - 14))

        button_h = max(32, min(48, int(h * 0.058)))
        gap = max(8, int(button_h * 0.25))
        total_w = min(900, w - 80)
        x = (w - total_w) // 2
        row1_y = self.bottom_top + gap
        row2_y = row1_y + button_h + gap
        half_w = (total_w - gap) // 2
        quarter_w = (total_w - gap * 3) // 4
        self.enter_button.set_rect(x, row1_y, half_w, button_h)
        self.create_button.set_rect(x + half_w + gap, row1_y, half_w, button_h)
        self.edit_button.set_rect(x, row2_y, quarter_w, button_h)
        self.delete_button.set_rect(x + (quarter_w + gap), row2_y, quarter_w, button_h)
        self.recreate_button.set_rect(x + (quarter_w + gap) * 2, row2_y, quarter_w, button_h)
        self.back_button.set_rect(x + (quarter_w + gap) * 3, row2_y, quarter_w, button_h)
        self._clamp_scroll()

    def _draw_background(self):
        key = (self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT)
        if self._background_cache is None or self._background_cache_key != key:
            self._background_cache = self._build_background()
            self._background_cache_key = key
        self.render.blit(self._background_cache, (0, 0))

    def _build_background(self):
        width = self.render.SCREEN_WIDTH
        height = self.render.SCREEN_HEIGHT
        surface = self.render.create_surface((width, height), convert=True)
        dirt = self.render.client.resources_manager.get_texture_img("blocks.dirt")
        tile_size = max(32, min(96, min(width, height) // 12))
        tile = self.render.scale_surface(dirt, (tile_size, tile_size))
        for x in range(0, width, tile_size):
            for y in range(0, height, tile_size):
                self.render.blit_to(surface, tile, (x, y))
        shade = self.render.create_surface((width, height), alpha=True)
        self.render.fill_surface(shade, (0, 0, 0, 160))
        self.render.blit_to(surface, shade, (0, 0))
        return surface

    def _draw_title(self):
        text = transkey("selectWorld.title")
        font = self.render.get_font(self.title_font)
        x = (self.render.SCREEN_WIDTH - font.size(text)[0]) // 2
        y = max(10, int(self.render.SCREEN_HEIGHT * 0.018))
        self.render.render_text(text, (x, y), (255, 255, 255), self.title_font, True)

    def _draw_list(self):
        self.render.draw_line((55, 55, 55), (0, self.list_top - 12), (self.render.SCREEN_WIDTH, self.list_top - 12), 2)
        self.render.draw_line((55, 55, 55), (0, self.list_bottom + 8), (self.render.SCREEN_WIDTH, self.list_bottom + 8), 2)
        self._entry_rects.clear()
        saves = self.filtered_saves()
        if not saves:
            msg = transkey("selectWorld.empty")
            font_size = max(22, min(34, int(self.render.SCREEN_HEIGHT * 0.04)))
            font = self.render.get_font(font_size)
            x = (self.render.SCREEN_WIDTH - font.size(msg)[0]) // 2
            y = self.list_top + max(20, (self.list_bottom - self.list_top - font_size) // 2)
            self.render.render_text(msg, (x, y), (170, 170, 170), font_size, True)
            return

        clip = pygame.Rect(0, self.list_top, self.render.SCREEN_WIDTH, max(1, self.list_bottom - self.list_top))
        old_clip = self.render.screen.get_clip()
        self.render.screen.set_clip(clip)
        for index, save in enumerate(saves):
            y = self.list_top + index * self.entry_h - self.scroll
            rect = pygame.Rect(self.list_x, y, self.list_w, self.entry_h)
            if rect.bottom < self.list_top or rect.top > self.list_bottom:
                continue
            self._entry_rects.append((rect, save))
            self._draw_entry(rect, save)
        self.render.screen.set_clip(old_clip)

    def _draw_entry(self, rect: pygame.Rect, save: dict):
        selected = save.get("id") == self.selected_id
        if selected:
            self.render.draw_rect((255, 255, 255), rect, 2)
            inner = rect.inflate(-4, -4)
            self.render.draw_rect((45, 45, 45), inner, 1)
        elif rect.collidepoint(pygame.mouse.get_pos()):
            self.render.draw_rect((120, 120, 120), rect, 1)

        preview_rect = pygame.Rect(rect.x + 12, rect.y + (rect.height - self.preview_size) // 2, self.preview_size, self.preview_size)
        preview = self._get_preview(save, self.preview_size)
        if preview is not None:
            self.render.blit(preview, preview_rect.topleft)

        text_x = preview_rect.right + 12
        text_w = rect.right - text_x - 8
        title = str(save.get("display_name") or save.get("id") or transkey("selectWorld.world"))
        last_played = self._format_time(float(save.get("last_played", 0) or 0))
        version = str(save.get("version") or getattr(self.render.client, "version", ""))
        mode = self._mode_text(str(save.get("game_mode", "")))
        line1 = title
        line2 = f"{title} ({last_played})"
        line3 = f"{mode}, {version}" if version else mode

        title_size = max(22, min(32, int(rect.height * 0.34)))
        detail_size = max(18, min(28, int(rect.height * 0.28)))
        clip = pygame.Rect(text_x, rect.y + 4, text_w, rect.height - 8)
        self.render.render_text(line1, (text_x, rect.y + 8), (255, 255, 255), title_size, True, clip_rect=clip)
        self.render.render_text(line2, (text_x, rect.y + 8 + title_size), (160, 160, 160), detail_size, True, clip_rect=clip)
        self.render.render_text(line3, (text_x, rect.y + 8 + title_size + detail_size), (160, 160, 160), detail_size, True, clip_rect=clip)

    def _draw_bottom_bar(self):
        rect = pygame.Rect(0, self.bottom_top, self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT - self.bottom_top)
        bar = self.render.create_surface(rect.size, alpha=True)
        self.render.fill_surface(bar, (0, 0, 0, 130))
        self.render.blit(bar, rect.topleft)
        self.render.draw_line((55, 55, 55), rect.topleft, rect.topright, 2)

    def _get_preview(self, save: dict, size: int) -> pygame.Surface | None:
        icon_path = save_manager.icon_path(str(save.get("id", "")))
        if not icon_path.exists():
            return None
        mtime = icon_path.stat().st_mtime
        key = (str(icon_path), size, mtime)
        if key in self._preview_cache:
            return self._preview_cache[key]
        try:
            surface = pygame.image.load(str(icon_path)).convert()
            if surface.get_size() != (size, size):
                surface = pygame.transform.scale(surface, (size, size))
            self._preview_cache[key] = surface
            return surface
        except pygame.error:
            return None

    def _handle_list_click(self, pos: tuple[int, int]) -> bool:
        for rect, save in self._entry_rects:
            if rect.collidepoint(pos):
                save_id = save["id"]
                now = time.perf_counter()
                double_click = self._last_click_id == save_id and now - self._last_click_time < 0.35
                self.selected_id = save_id
                self.confirm_delete_id = None
                self._last_click_id = save_id
                self._last_click_time = now
                self._update_buttons()
                if double_click:
                    self.start_selected()
                return True
        return False

    def _scroll_by(self, steps: int):
        self.scroll += steps * max(24, self.entry_h // 2)
        self._clamp_scroll()

    def _clamp_scroll(self):
        visible_h = max(1, self.list_bottom - self.list_top)
        max_scroll = max(0, len(self.filtered_saves()) * self.entry_h - visible_h)
        self.scroll = max(0, min(self.scroll, max_scroll))

    def _move_selection(self, delta: int):
        saves = self.filtered_saves()
        if not saves:
            self.selected_id = None
            self._update_buttons()
            return
        ids = [save["id"] for save in saves]
        if self.selected_id not in ids:
            index = 0
        else:
            index = ids.index(self.selected_id)
            index = max(0, min(len(ids) - 1, index + delta))
        self.selected_id = ids[index]
        self.confirm_delete_id = None
        self._ensure_selection_visible(index)
        self._update_buttons()

    def _ensure_selection_visible(self, index: int):
        top = index * self.entry_h
        bottom = top + self.entry_h
        visible_h = max(1, self.list_bottom - self.list_top)
        if top < self.scroll:
            self.scroll = top
        elif bottom > self.scroll + visible_h:
            self.scroll = bottom - visible_h
        self._clamp_scroll()

    def _on_search_changed(self):
        self.scroll = 0
        ids = [save["id"] for save in self.filtered_saves()]
        if self.selected_id not in ids:
            self.selected_id = ids[0] if ids else None
        self.confirm_delete_id = None
        self._update_buttons()

    def _update_buttons(self):
        has_selection = self.selected_id is not None
        if not self.starting_world:
            self.enter_button.enabled = has_selection
            self.delete_button.enabled = has_selection
            self.create_button.enabled = True
            self.back_button.enabled = True
        self.delete_button.text = transkey("selectWorld.deleteButton") if self.confirm_delete_id == self.selected_id and has_selection else transkey("selectWorld.delete")

    def _next_world_name(self) -> str:
        names = {str(save.get("display_name", "")) for save in self.saves}
        base_name = transkey("selectWorld.newWorld")
        if base_name not in names:
            return base_name
        for i in range(2, 1000):
            name = f"{base_name} ({i})"
            if name not in names:
                return name
        return f"{base_name} ({int(time.time())})"

    @staticmethod
    def _format_time(timestamp: float) -> str:
        if timestamp <= 0:
            return transkey("selectWorld.empty")
        dt = _datetime.datetime.fromtimestamp(timestamp)
        return f"{dt.month}/{dt.day}/{str(dt.year)[-2:]}, {dt.strftime('%I:%M %p')}"

    @staticmethod
    def _mode_text(mode: str) -> str:
        mode = mode.lower()
        if mode == "creative":
            return transkey("gameMode.creative")
        if mode == "survival":
            return transkey("gameMode.survival")
        return transkey("selectWorld.gameMode")
