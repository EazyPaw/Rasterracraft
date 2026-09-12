"""Minecraft-style create-world and superflat customization screens."""

from __future__ import annotations

import pygame

from src.client.GUI.button import Button
from src.client.GUI.gui import GUI
from src.client.GUI.input_box import InputBox
from src.server import save_manager
from src.server.blocks import get_block_by_id
from src.server.generator.superflat import (
    BLOCK_DISPLAY_NAMES,
    DEFAULT_SUPERFLAT_SETTINGS,
    SUPERFLAT_PRESETS,
    SuperflatSettings,
    parse_superflat_code,
)
from src.server.location import Location
from src.server.materials import get_material_by_id
from src.server.utils import client_method


WHITE = (255, 255, 255)
GRAY = (165, 165, 165)
ERROR = (255, 85, 85)


class _DirtMenu(GUI):
    """Shared full-screen dirt background and screen-switching helpers."""

    def __init__(self, render):
        super().__init__(render)
        self.priority = 100
        self._background_cache = None
        self._background_cache_key = None

    def _draw_background(self, shade_alpha: int = 150) -> None:
        key = (self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT, shade_alpha)
        if self._background_cache is None or self._background_cache_key != key:
            width, height, _ = key
            surface = self.render.create_surface((width, height), convert=True)
            dirt = self.render.client.resources_manager.get_texture_img("blocks.dirt")
            if dirt is None:
                self.render.fill_surface(surface, (48, 36, 25))
            else:
                tile_size = max(32, min(96, min(width, height) // 12))
                tile = self.render.scale_surface(dirt, (tile_size, tile_size))
                for x in range(0, width, tile_size):
                    for y in range(0, height, tile_size):
                        self.render.blit_to(surface, tile, (x, y))
            shade = self.render.create_surface((width, height), alpha=True)
            self.render.fill_surface(shade, (0, 0, 0, shade_alpha))
            self.render.blit_to(surface, shade, (0, 0))
            self._background_cache = surface
            self._background_cache_key = key
        self.render.blit(self._background_cache, (0, 0))

    def _switch_to(self, other: GUI) -> None:
        self.render.close_gui(self)
        self.render.show_gui(other)

    def _draw_centered(
        self,
        text: str,
        y: int,
        size: int,
        color=WHITE,
        *,
        shadow: bool = True,
    ) -> None:
        font = self.render.get_font(size)
        x = (self.render.SCREEN_WIDTH - font.size(text)[0]) // 2
        self.render.render_text(text, (x, y), color, size, shadow=shadow)

    @staticmethod
    def _handle_buttons(event, buttons: list[Button]) -> bool:
        if event.type not in (
            pygame.MOUSEMOTION,
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
        ):
            return False
        handled = False
        for button in buttons:
            if button.handle_event(event):
                handled = True
        return handled


class CreateWorldMenu(_DirtMenu):
    """Basic and expanded world-creation pages from the reference screens."""

    @client_method
    def __init__(self, render, parent, default_name: str, client=None):
        super().__init__(render)
        self.client = client or render.client
        self.parent = parent
        self.advanced = False
        self.creating = False
        self.game_mode = "survival"
        self.world_type = "default"
        self.generate_structures = True
        self.allow_cheats = False
        self.bonus_chest = False
        self.flat_settings = DEFAULT_SUPERFLAT_SETTINGS

        self.name_box = InputBox(
            default_name,
            label="World Name",
            max_length=64,
            on_change=lambda _text: self._refresh_buttons(),
            on_submit=lambda _text: self.create_world(),
        )
        self.seed_box = InputBox(
            "",
            label="Seed for the World Generator",
            max_length=128,
        )

        self.game_mode_button = Button("", self.toggle_game_mode)
        self.more_options_button = Button("More World Options...", self.show_more_options)
        self.structures_button = Button("", self.toggle_structures)
        self.world_type_button = Button("", self.toggle_world_type)
        self.customize_button = Button("Customize", self.open_customize)
        self.cheats_button = Button("", self.toggle_cheats)
        self.bonus_chest_button = Button("", self.toggle_bonus_chest)
        self.done_button = Button("Done", self.show_basic_options)
        self.create_button = Button("Create New World", self.create_world)
        self.cancel_button = Button("Cancel", self.cancel)
        self.buttons = [
            self.game_mode_button,
            self.more_options_button,
            self.structures_button,
            self.world_type_button,
            self.customize_button,
            self.cheats_button,
            self.bonus_chest_button,
            self.done_button,
            self.create_button,
            self.cancel_button,
        ]
        self._refresh_buttons()

    def on_open(self) -> None:
        if not self.advanced and not self.creating:
            self.name_box.focus()

    def on_close(self) -> None:
        self.name_box.blur()
        self.seed_box.blur()

    def draw(self) -> None:
        self._layout()
        self._draw_background()
        self._draw_centered("Create New World", self.title_y, self.title_size)
        if self.advanced:
            self._draw_advanced()
        else:
            self._draw_basic()
        for button in self.buttons:
            button.draw(self.render)

    def _draw_basic(self) -> None:
        self.name_box.draw(self.render)
        folder = save_manager.suggested_save_folder(self.name_box.text)
        self.render.render_text(
            f"Will be saved in: {folder}",
            (self.name_box.rect.x, self.name_box.rect.bottom + self.small_gap),
            GRAY,
            self.detail_size,
            shadow=True,
        )
        descriptions = {
            "survival": (
                "Search for resources, crafting, gain",
                "levels, health and hunger",
            ),
            "creative": (
                "Unlimited resources, free flying and",
                "destroy blocks instantly",
            ),
        }
        y = self.game_mode_button.rect.bottom + self.small_gap
        for line in descriptions[self.game_mode]:
            self.render.render_text(
                line,
                (self.game_mode_button.rect.x, y),
                GRAY,
                self.detail_size,
                shadow=True,
            )
            y += self.detail_size + 2

    def _draw_advanced(self) -> None:
        self.seed_box.draw(self.render)
        self.render.render_text(
            "Leave blank for a random seed",
            (self.seed_box.rect.x, self.seed_box.rect.bottom + self.small_gap),
            GRAY,
            self.detail_size,
            shadow=True,
        )
        self.render.render_text(
            "Empty template workspace"
            if self.world_type == "structure_build"
            else "Villages, dungeons etc",
            (self.structures_button.rect.x, self.structures_button.rect.bottom + 5),
            GRAY,
            self.detail_size,
            shadow=True,
        )
        self.render.render_text(
            "Commands like /gamemode, /xp",
            (self.cheats_button.rect.x, self.cheats_button.rect.bottom + 5),
            GRAY,
            self.detail_size,
            shadow=True,
        )

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        self._layout()
        active_box = self.seed_box if self.advanced else self.name_box
        for event in events[:]:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.cancel()
                events.remove(event)
                continue
            if active_box.handle_event(event):
                events.remove(event)
                continue
            if self._handle_buttons(event, self.buttons):
                events.remove(event)

    def toggle_game_mode(self) -> None:
        if self.world_type == "structure_build":
            return
        self.game_mode = "creative" if self.game_mode == "survival" else "survival"
        self._refresh_buttons()

    def show_more_options(self) -> None:
        self.name_box.blur()
        self.advanced = True
        self.seed_box.focus()
        self._refresh_buttons()

    def show_basic_options(self) -> None:
        self.seed_box.blur()
        self.advanced = False
        self.name_box.focus()
        self._refresh_buttons()

    def toggle_structures(self) -> None:
        if self.world_type == "structure_build":
            return
        self.generate_structures = not self.generate_structures
        self._refresh_buttons()

    def toggle_world_type(self) -> None:
        if pygame.key.get_mods() & pygame.KMOD_ALT:
            self.world_type = "structure_build"
            self.game_mode = "creative"
            self.generate_structures = False
            self.allow_cheats = True
            self.bonus_chest = False
        else:
            self.world_type = (
                "superflat" if self.world_type == "default" else "default"
            )
        self._refresh_buttons()

    def toggle_cheats(self) -> None:
        self.allow_cheats = not self.allow_cheats
        self._refresh_buttons()

    def toggle_bonus_chest(self) -> None:
        self.bonus_chest = not self.bonus_chest
        self._refresh_buttons()

    def open_customize(self) -> None:
        if self.world_type != "superflat":
            return
        menu = SuperflatCustomizationMenu(self.render, self, self.flat_settings)
        self._switch_to(menu)

    def set_flat_settings(self, settings: SuperflatSettings) -> None:
        self.flat_settings = settings

    def create_world(self) -> None:
        if self.creating:
            return
        display_name = self.name_box.text.strip() or "New World"
        self.creating = True
        for button in self.buttons:
            button.enabled = False
        self.name_box.enabled = False
        self.seed_box.enabled = False
        generator_name = {
            "default": "MinecraftLike2D",
            "superflat": "ClassicFlat",
            "structure_build": "StructureBuild",
        }[self.world_type]
        generator_options = (
            self.flat_settings.to_dict() if self.world_type == "superflat" else None
        )
        data = save_manager.create_save(
            display_name,
            version=getattr(self.client, "version", ""),
            game_mode=self.game_mode,
            seed=self.seed_box.text,
            generator_name=generator_name,
            generator_options=generator_options,
            generate_structures=self.generate_structures,
            allow_cheats=self.allow_cheats,
            bonus_chest=self.bonus_chest,
        )
        self.render.close_gui(self)
        self.client.start_game(data["id"])

    def cancel(self) -> None:
        if self.creating:
            return
        self._switch_to(self.parent)

    def _refresh_buttons(self) -> None:
        mode_name = "Survival" if self.game_mode == "survival" else "Creative"
        self.game_mode_button.text = f"Game Mode: {mode_name}"
        self.structures_button.text = (
            f"Generate Structures: {'ON' if self.generate_structures else 'OFF'}"
        )
        type_name = {
            "default": "Default",
            "superflat": "Superflat",
            "structure_build": "Structure Build",
        }[self.world_type]
        self.world_type_button.text = f"World Type: {type_name}"
        self.cheats_button.text = f"Allow Cheats: {'ON' if self.allow_cheats else 'OFF'}"
        self.bonus_chest_button.text = (
            f"Bonus Chest: {'ON' if self.bonus_chest else 'OFF'}"
        )
        self.customize_button.visible = self.advanced and self.world_type == "superflat"
        self.structures_button.enabled = not self.creating and self.world_type != "structure_build"
        self.game_mode_button.enabled = not self.creating and self.world_type != "structure_build"
        self.game_mode_button.visible = not self.advanced
        self.more_options_button.visible = not self.advanced
        self.structures_button.visible = self.advanced
        self.world_type_button.visible = self.advanced
        self.cheats_button.visible = self.advanced
        self.bonus_chest_button.visible = self.advanced
        self.done_button.visible = self.advanced
        self.create_button.enabled = not self.creating

    def _layout(self) -> None:
        width, height = self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT
        self.title_size = max(25, min(42, int(height * 0.045)))
        self.detail_size = max(17, min(28, int(height * 0.028)))
        self.title_y = max(14, int(height * 0.035))
        content_w = min(760, max(360, int(width * 0.48)))
        field_h = max(38, min(64, int(height * 0.065)))
        button_h = max(36, min(58, int(height * 0.058)))
        self.small_gap = max(6, int(height * 0.009))
        x = (width - content_w) // 2
        bottom_y = height - button_h - max(18, int(height * 0.028))
        bottom_gap = max(8, int(width * 0.012))
        bottom_w = min(920, width - 48)
        half = (bottom_w - bottom_gap) // 2
        bottom_x = (width - bottom_w) // 2
        self.create_button.set_rect(bottom_x, bottom_y, half, button_h)
        self.cancel_button.set_rect(bottom_x + half + bottom_gap, bottom_y, half, button_h)

        if not self.advanced:
            field_y = max(self.title_y + self.title_size + 55, int(height * 0.16))
            self.name_box.set_rect(x, field_y, content_w, field_h)
            mode_y = max(field_y + field_h + 90, int(height * 0.34))
            button_w = min(560, content_w)
            button_x = (width - button_w) // 2
            self.game_mode_button.set_rect(button_x, mode_y, button_w, button_h)
            more_y = max(mode_y + button_h + 130, int(height * 0.56))
            self.more_options_button.set_rect(button_x, more_y, button_w, button_h)
            return

        field_y = max(self.title_y + self.title_size + 55, int(height * 0.16))
        self.seed_box.set_rect(x, field_y, content_w, field_h)
        pair_w = min(930, width - 48)
        pair_gap = max(10, int(width * 0.018))
        half = (pair_w - pair_gap) // 2
        pair_x = (width - pair_w) // 2
        row1_y = max(field_y + field_h + 60, int(height * 0.29))
        self.structures_button.set_rect(pair_x, row1_y, half, button_h)
        self.world_type_button.set_rect(pair_x + half + pair_gap, row1_y, half, button_h)
        customize_y = row1_y + button_h + 5
        self.customize_button.set_rect(
            self.world_type_button.rect.x, customize_y, half, button_h
        )
        row2_y = max(
            row1_y + button_h + (button_h if self.customize_button.visible else 0) + 42,
            int(height * 0.45),
        )
        self.cheats_button.set_rect(pair_x, row2_y, half, button_h)
        self.bonus_chest_button.set_rect(pair_x + half + pair_gap, row2_y, half, button_h)
        done_w = min(560, content_w)
        self.done_button.set_rect(
            (width - done_w) // 2,
            row2_y + button_h + max(48, int(height * 0.05)),
            done_w,
            button_h,
        )


class SuperflatCustomizationMenu(_DirtMenu):
    """Layer overview with removal and preset navigation."""

    def __init__(self, render, parent: CreateWorldMenu, settings: SuperflatSettings):
        super().__init__(render)
        self.parent = parent
        self.settings = settings
        self.selected_row = 0
        self.scroll = 0
        self._row_rects: list[tuple[pygame.Rect, int]] = []
        self._icon_cache: dict[tuple[str, int], pygame.Surface | None] = {}
        self.remove_button = Button("Remove Layer", self.remove_layer)
        self.presets_button = Button("Presets", self.open_presets)
        self.done_button = Button("Done", self.done)
        self.cancel_button = Button("Cancel", self.cancel)
        self.buttons = [
            self.remove_button,
            self.presets_button,
            self.done_button,
            self.cancel_button,
        ]

    def draw(self) -> None:
        self._layout()
        self._draw_background(165)
        self._draw_centered("Superflat Customization", self.title_y, self.title_size)
        self.render.render_text(
            "Layer Material", (self.list_x, self.header_y), WHITE, self.header_size, True
        )
        height_label = "Height"
        font = self.render.get_font(self.header_size)
        self.render.render_text(
            height_label,
            (self.list_right - font.size(height_label)[0], self.header_y),
            WHITE,
            self.header_size,
            True,
        )
        self._draw_layers()
        self._draw_bottom_bar()
        self.remove_button.enabled = len(self.settings.layers) > 1
        for button in self.buttons:
            button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        self._layout()
        for event in events[:]:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.cancel()
                events.remove(event)
                continue
            if self._handle_buttons(event, self.buttons):
                events.remove(event)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, index in self._row_rects:
                    if rect.collidepoint(event.pos):
                        self.selected_row = index
                        events.remove(event)
                        break
            elif event.type == pygame.MOUSEWHEEL:
                self.scroll -= event.y * self.row_h
                self._clamp_scroll()
                events.remove(event)
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_DOWN):
                delta = -1 if event.key == pygame.K_UP else 1
                self.selected_row = max(
                    0, min(len(self.settings.layers) - 1, self.selected_row + delta)
                )
                events.remove(event)

    def remove_layer(self) -> None:
        if len(self.settings.layers) <= 1:
            return
        display_layers = list(reversed(self.settings.layers))
        display_layers.pop(self.selected_row)
        self.settings = SuperflatSettings(
            tuple(reversed(display_layers)),
            self.settings.biome_id,
            self.settings.structures,
        )
        self.selected_row = min(self.selected_row, len(display_layers) - 1)
        self._clamp_scroll()

    def open_presets(self) -> None:
        self._switch_to(SuperflatPresetsMenu(self.render, self, self.settings))

    def apply_preset(self, settings: SuperflatSettings) -> None:
        self.settings = settings
        self.selected_row = 0
        self.scroll = 0

    def done(self) -> None:
        self.parent.set_flat_settings(self.settings)
        self._switch_to(self.parent)

    def cancel(self) -> None:
        self._switch_to(self.parent)

    def _layout(self) -> None:
        width, height = self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT
        self.title_size = max(24, min(40, int(height * 0.043)))
        self.header_size = max(20, min(32, int(height * 0.032)))
        self.row_font = max(19, min(32, int(height * 0.031)))
        self.title_y = max(10, int(height * 0.018))
        list_w = min(720, max(380, int(width * 0.50)))
        self.list_x = (width - list_w) // 2
        self.list_right = self.list_x + list_w
        self.header_y = max(self.title_y + self.title_size + 36, int(height * 0.085))
        self.list_top = self.header_y + self.header_size + 14
        self.bottom_top = height - max(155, int(height * 0.18))
        self.list_bottom = self.bottom_top - 12
        self.row_h = max(54, min(76, int(height * 0.075)))
        self.icon_size = max(36, min(56, self.row_h - 10))
        self._clamp_scroll()

        button_h = max(36, min(58, int(height * 0.058)))
        button_w = min(460, max(210, int(width * 0.31)))
        gap = max(10, int(width * 0.02))
        left = (width - button_w * 2 - gap) // 2
        row1 = self.bottom_top + max(10, int(height * 0.012))
        row2 = row1 + button_h + max(9, int(height * 0.012))
        self.remove_button.set_rect(left, row1, button_w, button_h)
        self.presets_button.set_rect(left + button_w + gap, row1, button_w, button_h)
        self.done_button.set_rect(left, row2, button_w, button_h)
        self.cancel_button.set_rect(left + button_w + gap, row2, button_w, button_h)

    def _draw_layers(self) -> None:
        display_layers = list(reversed(self.settings.layers))
        clip = pygame.Rect(0, self.list_top, self.render.SCREEN_WIDTH, self.list_bottom - self.list_top)
        old_clip = self.render.screen.get_clip()
        self.render.screen.set_clip(clip)
        self._row_rects.clear()
        for index, layer in enumerate(display_layers):
            y = self.list_top + index * self.row_h - self.scroll
            rect = pygame.Rect(self.list_x, y, self.list_right - self.list_x, self.row_h)
            if rect.bottom < self.list_top or rect.top > self.list_bottom:
                continue
            self._row_rects.append((rect, index))
            if index == self.selected_row:
                self.render.draw_rect((255, 255, 255), rect, 2)
                self.render.draw_rect((25, 25, 25), rect.inflate(-4, -4), 1)
            self._draw_icon(layer.block_id, self.icon_size, rect.x + 7, rect.centery - self.icon_size // 2)
            name = BLOCK_DISPLAY_NAMES.get(layer.block_id, layer.block_id.replace("_", " ").title())
            self.render.render_text(
                name,
                (rect.x + self.icon_size + 20, rect.centery - self.row_font // 2),
                WHITE,
                self.row_font,
                True,
            )
            if index == 0:
                height_text = f"Top - {layer.height}"
            elif index == len(display_layers) - 1:
                height_text = f"Bottom - {layer.height}"
            else:
                height_text = str(layer.height)
            font = self.render.get_font(self.row_font)
            self.render.render_text(
                height_text,
                (rect.right - font.size(height_text)[0] - 8, rect.centery - self.row_font // 2),
                WHITE,
                self.row_font,
                True,
            )
        self.render.screen.set_clip(old_clip)

    def _draw_icon(self, icon_id: str, size: int, x: int, y: int) -> None:
        if icon_id == "air":
            rect = pygame.Rect(x, y, size, size)
            self.render.draw_rect((230, 230, 230), rect, 2)
            self.render.draw_line((220, 30, 30), rect.topleft, rect.bottomright, max(3, size // 8))
            return
        key = (icon_id, size)
        if key not in self._icon_cache:
            texture = None
            material = get_material_by_id(icon_id)
            if getattr(material, "name_id", "air") != "air":
                texture = material.get_texture(size / 16.0, client=self.render.client)
            if texture is None:
                block = get_block_by_id(icon_id)
                block.location = Location(self.render.client.client_world, 0, 64, 0)
                texture = block.get_texture(size, client=self.render.client)
            if texture is not None and texture.get_size() != (size, size):
                texture = self.render.scale_surface(texture, (size, size))
            self._icon_cache[key] = texture
        texture = self._icon_cache[key]
        if texture is not None:
            self.render.blit(texture, (x, y))

    def _draw_bottom_bar(self) -> None:
        bar = pygame.Rect(0, self.bottom_top, self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT - self.bottom_top)
        overlay = self.render.create_surface(bar.size, alpha=True)
        self.render.fill_surface(overlay, (0, 0, 0, 125))
        self.render.blit(overlay, bar.topleft)
        self.render.draw_line((55, 55, 55), bar.topleft, bar.topright, 2)

    def _clamp_scroll(self) -> None:
        visible = max(1, getattr(self, "list_bottom", 1) - getattr(self, "list_top", 0))
        maximum = max(0, len(self.settings.layers) * getattr(self, "row_h", 1) - visible)
        self.scroll = max(0, min(self.scroll, maximum))


class SuperflatPresetsMenu(SuperflatCustomizationMenu):
    """Preset-code input and the complete built-in preset list."""

    def __init__(
        self,
        render,
        parent: SuperflatCustomizationMenu,
        settings: SuperflatSettings,
    ):
        _DirtMenu.__init__(self, render)
        self.parent = parent
        self.settings = settings
        self.selected_row = self._matching_preset(settings.code)
        self.scroll = 0
        self.error_message = ""
        self._row_rects = []
        self._icon_cache = {}
        self.code_box = InputBox(settings.code, max_length=1230)
        self.use_button = Button("Use Preset", self.use_preset)
        self.cancel_button = Button("Cancel", self.cancel)
        self.buttons = [self.use_button, self.cancel_button]

    def on_open(self) -> None:
        self.code_box.focus()

    def on_close(self) -> None:
        self.code_box.blur()

    def draw(self) -> None:
        self._layout_presets()
        self._draw_background(165)
        self._draw_centered("Select a Preset", self.title_y, self.title_size)
        self.render.render_text(
            "Want to share your preset with someone? Use the below box!",
            (self.field_x, self.field_y - self.label_size - 8),
            GRAY,
            self.label_size,
            True,
        )
        self.code_box.draw(self.render)
        prompt_y = self.code_box.rect.bottom + max(14, self.label_size // 2)
        self.render.render_text(
            "Alternatively, here's some we made earlier!",
            (self.field_x, prompt_y),
            GRAY,
            self.label_size,
            True,
        )
        if self.error_message:
            font = self.render.get_font(self.error_size)
            x = self.render.SCREEN_WIDTH - self.field_x - font.size(self.error_message)[0]
            self.render.render_text(
                self.error_message, (x, prompt_y), ERROR, self.error_size, True
            )
        self._draw_presets()
        self._draw_bottom_bar()
        for button in self.buttons:
            button.draw(self.render)

    def handle_events(self, events: list[pygame.event.Event]) -> None:
        self._layout_presets()
        for event in events[:]:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.cancel()
                events.remove(event)
                continue
            if self.code_box.handle_event(event):
                self.error_message = ""
                events.remove(event)
                continue
            if self._handle_buttons(event, self.buttons):
                events.remove(event)
                continue
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, index in self._row_rects:
                    if rect.collidepoint(event.pos):
                        self._select_preset(index)
                        events.remove(event)
                        break
            elif event.type == pygame.MOUSEWHEEL:
                self.scroll -= event.y * self.row_h
                self._clamp_preset_scroll()
                events.remove(event)
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_DOWN):
                delta = -1 if event.key == pygame.K_UP else 1
                self._select_preset(max(0, min(len(SUPERFLAT_PRESETS) - 1, self.selected_row + delta)))
                events.remove(event)

    def use_preset(self) -> None:
        try:
            parsed = parse_superflat_code(self.code_box.text)
            structures = ()
            if 0 <= self.selected_row < len(SUPERFLAT_PRESETS):
                selected = SUPERFLAT_PRESETS[self.selected_row]
                if selected.settings.code == parsed.code:
                    structures = selected.settings.structures
            settings = SuperflatSettings(parsed.layers, parsed.biome_id, structures)
        except (TypeError, ValueError):
            settings = DEFAULT_SUPERFLAT_SETTINGS
            self.error_message = "Invalid code - Classic Flat selected"
        self.parent.apply_preset(settings)
        self._switch_to(self.parent)

    def cancel(self) -> None:
        self._switch_to(self.parent)

    def _select_preset(self, index: int) -> None:
        if not hasattr(self, "row_h"):
            self._layout_presets()
        self.selected_row = index
        self.settings = SUPERFLAT_PRESETS[index].settings
        self.code_box.set_text(self.settings.code, notify=False)
        self.error_message = ""
        top = index * self.row_h
        visible = self.list_bottom - self.list_top
        if top < self.scroll:
            self.scroll = top
        elif top + self.row_h > self.scroll + visible:
            self.scroll = top + self.row_h - visible
        self._clamp_preset_scroll()

    @staticmethod
    def _matching_preset(code: str) -> int:
        for index, preset in enumerate(SUPERFLAT_PRESETS):
            if preset.settings.code == code:
                return index
        return 0

    def _layout_presets(self) -> None:
        width, height = self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT
        self.title_size = max(24, min(40, int(height * 0.042)))
        self.label_size = max(18, min(28, int(height * 0.028)))
        self.error_size = max(15, self.label_size - 3)
        self.row_font = max(20, min(32, int(height * 0.032)))
        self.title_y = max(8, int(height * 0.012))
        field_w = min(1120, width - 70)
        self.field_x = (width - field_w) // 2
        self.field_y = max(self.title_y + self.title_size + 65, int(height * 0.105))
        field_h = max(40, min(64, int(height * 0.064)))
        self.code_box.set_rect(self.field_x, self.field_y, field_w, field_h)
        self.list_top = self.field_y + field_h + self.label_size + max(28, int(height * 0.035))
        self.bottom_top = height - max(105, int(height * 0.115))
        self.list_bottom = self.bottom_top - 8
        list_w = min(680, max(360, int(width * 0.43)))
        self.list_x = (width - list_w) // 2
        self.list_right = self.list_x + list_w
        self.row_h = max(54, min(72, int(height * 0.071)))
        self.icon_size = max(36, min(54, self.row_h - 8))
        self._clamp_preset_scroll()

        button_h = max(36, min(58, int(height * 0.058)))
        buttons_w = min(930, width - 48)
        gap = max(10, int(width * 0.02))
        half = (buttons_w - gap) // 2
        x = (width - buttons_w) // 2
        y = self.bottom_top + (height - self.bottom_top - button_h) // 2
        self.use_button.set_rect(x, y, half, button_h)
        self.cancel_button.set_rect(x + half + gap, y, half, button_h)

    def _draw_presets(self) -> None:
        clip = pygame.Rect(0, self.list_top, self.render.SCREEN_WIDTH, self.list_bottom - self.list_top)
        old_clip = self.render.screen.get_clip()
        self.render.screen.set_clip(clip)
        self._row_rects.clear()
        for index, preset in enumerate(SUPERFLAT_PRESETS):
            y = self.list_top + index * self.row_h - self.scroll
            rect = pygame.Rect(self.list_x, y, self.list_right - self.list_x, self.row_h)
            if rect.bottom < self.list_top or rect.top > self.list_bottom:
                continue
            self._row_rects.append((rect, index))
            if index == self.selected_row:
                self.render.draw_rect((255, 255, 255), rect, 2)
                self.render.draw_rect((35, 35, 35), rect.inflate(-4, -4), 1)
            self._draw_icon(
                preset.icon_id,
                self.icon_size,
                rect.x + 8,
                rect.centery - self.icon_size // 2,
            )
            self.render.render_text(
                preset.name,
                (rect.x + self.icon_size + 22, rect.centery - self.row_font // 2),
                WHITE,
                self.row_font,
                True,
            )
        self.render.screen.set_clip(old_clip)

    def _clamp_preset_scroll(self) -> None:
        visible = max(1, getattr(self, "list_bottom", 1) - getattr(self, "list_top", 0))
        maximum = max(0, len(SUPERFLAT_PRESETS) * getattr(self, "row_h", 1) - visible)
        self.scroll = max(0, min(self.scroll, maximum))
