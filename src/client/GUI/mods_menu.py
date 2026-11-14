"""Mod browser and configuration launcher, usable from the pause menu."""

import io
import logging
import os
import subprocess
import sys

import pygame

from src.client.GUI.button import Button
from src.client.GUI.gui import GUI
from src.client.resources_manager import transkey
from src.server.text import Text, TextColor
from src.version import GAME_VERSION


class ModsMenu(GUI):
    def __init__(self, render, parent):
        super().__init__(render)
        self.priority = 100
        self.parent = parent
        self.service = render.client.mod_service
        self.selected = None
        self.list_scroll = 0
        self.detail_scroll = 0
        self.detail_height = 0
        self.error = ""
        self.message = ""
        self.icons = {}
        self.rows = []
        self._panel_cache = {}
        self._shade_cache = None
        self.toggle_button = Button("", self.toggle)
        self.config_button = Button(transkey("mods.configure"), self.configure)
        self.buttons = [self.toggle_button,
                        Button(transkey("mods.refresh"), self.refresh),
                        Button(transkey("mods.openFolder"), self.open_folder),
                        self.config_button,
                        Button(transkey("gui.done"), self.back)]

    def on_open(self):
        if self.in_world:
            self.render.client.game_manager.acquire_game_input()
            self.render.request_text_input(False)
        self.refresh()

    def on_close(self):
        if self.in_world:
            self.render.client.game_manager.release_game_input()

    @property
    def in_world(self):
        return bool(self.render.client.in_game or self.render.client.game_started)

    def refresh(self):
        try:
            if not self.in_world:
                self.service.refresh()
            self.icons.clear()
            self.error = ""
        except Exception as error:
            logging.exception("Failed to refresh Mod menu")
            self.error = str(error)
        entries = self.entries()
        if self.selected not in {info.path for info in entries}:
            self.selected = entries[0].path if entries else None
        self.detail_scroll = 0

    def entries(self):
        return sorted(self.service.manager.candidates.values(),
                      key=lambda info: (info.priority, info.namespace, info.path.name.casefold(), info.path.name))

    def selected_info(self):
        return self.service.manager.candidates.get(self.selected)

    def config_factory(self):
        info = self.selected_info()
        if info and any(record.ctx.info == info for record in self.service.manager.loaded):
            return self.service.manager.config_menus.get(info.namespace)
        return None

    def toggle(self):
        if self.in_world or not self.selected or self.service.busy:
            return
        info = self.selected_info()
        if info is None:
            return
        try:
            key = self.service.manager.key_for(info)
            result = self.service.set_enabled(key, key not in self.service.desired)
            self.message = transkey("mods.result." + result)
            self.error = ""
        except Exception as error:
            self.message = ""
            self.error = str(error)
        self.detail_scroll = 0

    def back(self):
        if self.service.busy:
            return
        self.render.close_gui(self)
        self.render.show_gui(self.parent)

    def open_folder(self):
        try:
            path = self.service.manager.directory
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32":
                os.startfile(str(path))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as error:
            self.error = str(error)

    def configure(self):
        factory = self.config_factory()
        if factory is None or self.service.busy:
            return
        try:
            gui = factory(self.render, self)
            if not isinstance(gui, GUI):
                raise TypeError("Mod config factory must return a GUI")
            self.render.close_gui(self)
            self.render.show_gui(gui)
        except Exception as error:
            logging.exception("Failed to open Mod configuration: %s", self.selected)
            self.render.show_gui(self)
            self.error = str(error)

    def layout(self):
        width, height = self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT
        margin = max(10, min(28, width // 40))
        self.font_size = max(16, min(22, height // 34))
        self.line_height = self.font_size + 7
        self.list_rect = pygame.Rect(margin, 64, max(130, int(width * .35) - margin), max(60, height - 152))
        self.detail_rect = pygame.Rect(self.list_rect.right + 12, 64,
                                      max(80, width - self.list_rect.right - margin - 12), self.list_rect.height)
        self.row_height = 80
        columns = 5 if width >= 760 else 3
        rows = (len(self.buttons) + columns - 1) // columns
        footer_height = 52 + (rows - 1) * 42
        self.list_rect.height = self.detail_rect.height = max(60, height - 100 - footer_height)
        button_width = max(1, (width - margin * 2 - (columns - 1) * 8) // columns)
        for index, button in enumerate(self.buttons):
            button.set_rect(margin + (index % columns) * (button_width + 8),
                            height - footer_height + (index // columns) * 42, button_width, 36)
            button.enabled = not self.service.busy
        info = self.selected_info()
        self.toggle_button.enabled = (info is not None
                                      and not self.service.busy and not self.in_world)
        self.toggle_button.text = transkey("mods.disable" if info and self.service.manager.key_for(info) in self.service.desired
                                          else "mods.enable")
        self.config_button.enabled = not self.service.busy and self.config_factory() is not None

    def status(self, info, text=False) -> str | Text:
        local = {record.ctx.namespace: record.ctx.info for record in self.service.manager.loaded}
        server = set(self.service.server_status.get("loaded", []))
        server_info = {entry["namespace"]: entry for entry in self.service.server_status.get("mods", [])}
        actual = ((not info.supports("client") or info.namespace in local)
                  and (not info.supports("server") or info.namespace in server))
        present = info.namespace in local or info.namespace in server
        desired = self.service.manager.key_for(info) in self.service.desired
        if not desired and (info.namespace not in local or local[info.namespace] != info):
            if text:
                return Text(transkey("mods.disabled"), TextColor.GRAY)
            return transkey("mods.disabled")
        if ((info.namespace in local and local[info.namespace] != info)
                or (info.namespace in server_info and server_info[info.namespace]["version"] != info.version)):
            if text:
                return Text(transkey("mods.pendingRestart"), TextColor.YELLOW)
            return transkey("mods.pendingRestart")
        if desired and actual:
            if text:
                return Text(transkey("mods.enabled"), (190, 220, 170))
            return transkey("mods.enabled")
        if not desired and not present:
            if text:
                return Text(transkey("mods.disabled"), TextColor.GRAY)
            return transkey("mods.disabled")
        if desired and not present and (self.error or self.service.errors
                                       or self.service.server_status.get("diagnostics")):
            if text:
                return Text(transkey("mods.failedOrPending"), TextColor.RED)
            return transkey("mods.failedOrPending")
        if text:
            return Text(transkey("mods.pendingRestart"), TextColor.YELLOW)
        return transkey("mods.pendingRestart")

    def draw(self):
        self.layout()
        self.draw_background()
        title = transkey("mods.title")
        self.render.render_text(title, (self.list_rect.x, 18), (255, 255, 255), 30, True)
        self.render.render_text(transkey("mods.currentVersion", GAME_VERSION),
                                (self.detail_rect.x, 26), (190, 190, 190), self.font_size)
        self.draw_panel(self.list_rect)
        self.draw_panel(self.detail_rect)
        self.draw_list()
        self.draw_details()
        hint = self.message or transkey("mods.inGameHint" if self.in_world else "mods.menuOnly")
        color = (255, 170, 130) if self.error else (190, 220, 190)
        if self.error:
            hint = transkey("mods.operationFailed")
        self.render.render_text(hint, (self.list_rect.x, self.list_rect.bottom + 8), color,
                                max(14, self.font_size - 2), clip_rect=pygame.Rect(
                                    self.list_rect.x, self.list_rect.bottom + 6,
                                    self.render.SCREEN_WIDTH - self.list_rect.x * 2, 28))
        for button in self.buttons:
            button.draw(self.render)

    def draw_panel(self, rect):
        size = rect.size
        if size not in self._panel_cache:
            panel = self.render.create_surface(size, alpha=True)
            self.render.fill_surface(panel, (22, 22, 22, 125))
            # Keep only the current layout's panels when resizing the window.
            current_sizes = {self.list_rect.size, self.detail_rect.size}
            self._panel_cache = {key: value for key, value in self._panel_cache.items()
                                 if key in current_sizes}
            self._panel_cache[size] = panel
        self.render.blit(self._panel_cache[size], rect.topleft)

    def draw_background(self):
        if not self.in_world:
            self.parent._draw_background()
            return
        size = self.render.screen.get_size()
        if self._shade_cache is None or self._shade_cache.get_size() != size:
            self._shade_cache = pygame.Surface(size, pygame.SRCALPHA)
            self._shade_cache.fill((9, 16, 24, 170))
        self.render.blit(self._shade_cache, (0, 0))

    def draw_list(self):
        entries = self.entries()
        self.list_scroll = max(0, min(self.list_scroll, max(0, len(entries) * self.row_height - self.list_rect.height)))
        self.rows = []
        clip = self.render.screen.get_clip()
        self.render.screen.set_clip(self.list_rect)
        try:
            if not entries:
                self.render.render_text(transkey("mods.empty"), (self.list_rect.x + 10, self.list_rect.y + 12),
                                        (190, 190, 190), self.font_size)
            for index, info in enumerate(entries):
                rect = pygame.Rect(self.list_rect.x, self.list_rect.y + index * self.row_height - self.list_scroll,
                                   self.list_rect.width, self.row_height)
                if not rect.colliderect(self.list_rect):
                    continue
                self.rows.append((rect, info.path))
                if self.selected == info.path:
                    self.render.draw_rect((90, 90, 90), rect, 2)
                icon = self.get_icon(info)
                if icon:
                    self.render.blit(icon, (rect.x + 8, rect.y + 10))
                x = rect.x + 76
                text_clip = pygame.Rect(x, rect.y + 3, max(1, rect.right - x - 6), rect.height - 6)
                self.render.render_text(info.name, (x, rect.y + 8), (255, 255, 255), self.font_size,
                                        clip_rect=text_clip)
                self.render.render_text(info.version, (x, rect.y + 31), (180, 180, 180), self.font_size - 2,
                                        clip_rect=text_clip)
                self.render.render_text(self.status(info, True), (x, rect.y + 53), font_size=self.font_size - 2,
                                        clip_rect=text_clip)
        finally:
            self.render.screen.set_clip(clip)
        self.scrollbar(self.list_rect, self.list_scroll, len(entries) * self.row_height)

    def get_icon(self, info):
        key = (info.path, info.version)
        if key not in self.icons:
            try:
                image = pygame.image.load(io.BytesIO(info.read_file("icon.png")))
                # Source aspect ratio and dimensions are deliberately unrestricted.
                self.icons[key] = pygame.transform.smoothscale(image, (58, 58))
            except Exception:
                logging.exception("Invalid Mod icon: %s", info.path)
                self.icons[key] = pygame.transform.scale(self.render.client.resources_manager.missing_texture, (58, 58))
        return self.icons[key]

    def wrap(self, text, width):
        font = self.render.get_font(self.font_size)
        lines = []
        for paragraph in str(text).splitlines() or [""]:
            line = ""
            for character in paragraph:
                if line and font.size(line + character)[0] > width:
                    lines.append(line)
                    line = ""
                line += character
            lines.append(line)
        return lines

    def draw_details(self):
        info = self.selected_info()
        sections = []
        normal, warning, error = (230, 230, 230), (255, 205, 110), (255, 140, 140)
        if self.error:
            sections.append((transkey("mods.operationFailed") + "\n" + self.error, error))
        if info:
            yes, no = transkey("mods.yes"), transkey("mods.no")
            sections.extend([
                (info.name + " — " + self.status(info), normal),
                (transkey("mods.namespace", info.namespace), normal),
                (transkey("mods.authors", ", ".join(info.authors)), normal),
                (transkey("mods.version", info.version), normal),
                (transkey("mods.gameVersions", str(info.game_versions)), normal),
                (transkey("mods.priority", info.priority), normal),
                (transkey("mods.clientSupport", transkey("mods.support." + info.client)), normal),
                (transkey("mods.serverSupport", transkey("mods.support." + info.server)), normal),
                (transkey("mods.hotLoad", yes if info.hot_load else no), normal),
                (transkey("mods.hotUnload", yes if info.hot_unload else no), normal),
            ])
            if info.dependencies:
                sections.append((transkey("mods.dependencies", ", ".join(info.dependencies)), normal))
            if not info.compatible:
                sections.append((transkey("mods.versionWarning"), warning))
            sections.append((info.description, normal))
        diagnostics = list(dict.fromkeys(self.service.errors + self.service.manager.diagnostics
                                        + self.service.server_status.get("diagnostics", [])))
        if diagnostics:
            sections.append((transkey("mods.diagnostics") + "\n" + "\n".join(diagnostics), warning))
        lines = []
        for text, color in sections:
            lines.extend((line, color) for line in self.wrap(text, max(20, self.detail_rect.width - 24)))
            lines.append(("", normal))
        self.detail_height = len(lines) * self.line_height + 20
        self.detail_scroll = max(0, min(self.detail_scroll, max(0, self.detail_height - self.detail_rect.height)))
        clip = self.render.screen.get_clip()
        self.render.screen.set_clip(self.detail_rect)
        try:
            for index, (line, color) in enumerate(lines):
                y = self.detail_rect.y + 10 + index * self.line_height - self.detail_scroll
                if self.detail_rect.y - self.line_height < y < self.detail_rect.bottom:
                    self.render.render_text(line, (self.detail_rect.x + 12, y), color, self.font_size)
        finally:
            self.render.screen.set_clip(clip)
        self.scrollbar(self.detail_rect, self.detail_scroll, self.detail_height)

    def scrollbar(self, rect, offset, total):
        if total <= rect.height:
            return
        height = max(18, int(rect.height * rect.height / total))
        y = rect.y + int(offset / (total - rect.height) * (rect.height - height))
        self.render.draw_rect((130, 130, 130), pygame.Rect(rect.right - 5, y, 3, height))

    def handle_events(self, events):
        self.layout()
        for event in events[:]:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.back()
            elif event.type == pygame.MOUSEWHEEL:
                if self.list_rect.collidepoint(pygame.mouse.get_pos()):
                    self.list_scroll -= event.y * 40
                else:
                    self.detail_scroll -= event.y * 40
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.list_rect.collidepoint(event.pos):
                    for rect, path in self.rows:
                        if rect.collidepoint(event.pos):
                            self.selected, self.detail_scroll = path, 0
                for button in self.buttons:
                    button.handle_event(event)
            elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONUP):
                for button in self.buttons:
                    button.handle_event(event)
            if event in events:
                events.remove(event)
