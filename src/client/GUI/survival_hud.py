# Commented and arranged by ChatGPT
"""Minecraft风格的生存模式HUD：快捷栏、生命值、饥饿值、经验条以及受伤反馈。

该GUI叠加在快捷栏（HotBar）之上，以原版Minecraft布局渲染状态计量条（生命值和饥饿值）
——生命值在左，饥饿值从右侧镜像排列——经验条则夹在它们与快捷栏之间。
"""

import math
import random

import pygame

from src.client.GUI.inventory.hotbar import HotBar


class SurvivalHUD(HotBar):
    """游戏内生存模式的HUD，使用捆绑的原始精灵图构建。

    扩展 :class:`HotBar` 以绘制：
    - 10颗生命心（左对齐，显示完整/半颗/空心）
    - 10个饥饿鸡腿（右对齐，填充方向镜像）
    - 经验条及等级数字标签
    """

    def __init__(self, render):
        """缓存已加载的图标表面，以精灵名称为键。"""
        super().__init__(render)
        self._icons = {}
        self._health_player = None
        self._last_health = 0
        self._display_health = 0
        self._health_changed_ms = 0
        self._blink_until = 0

    # ------------------------------------------------------------------
    #  内部辅助方法
    # ------------------------------------------------------------------

    def _icon(self, name: str) -> pygame.Surface:
        """返回一个尺寸为 9×gui_scale 像素的HUD精灵图，首次使用时加载并缓存。

        :param name: 精灵图ID，例如 ``"heart.full"``。完整纹理路径
            ``gui.sprites.hud.<name>`` 由资源管理器解析。

        """
        if getattr(self, "_icon_scale", None) != self.render.gui_scale:
            self._icons.clear()
            self._icon_scale = self.render.gui_scale
        key = name
        cached = self._icons.get(key)
        if cached is not None:
            return cached
        texture = self.render.client.resources_manager.get_texture_img(
            f"gui.sprites.hud.{name}"
        )
        size = max(1, round(9 * self.render.gui_scale))
        cached = pygame.transform.scale(texture, (size, size))
        self._icons[key] = cached
        return cached

    def _draw_armor(self, value: float, x: int, y: int) -> bool:
        """Draw the vanilla ten-icon armor bar and report whether it was visible."""
        value = max(0.0, min(20.0, float(value)))
        if value <= 0.0:
            return False
        empty = self._icon("armor_empty")
        half = self._icon("armor_half")
        full = self._icon("armor_full")
        spacing = 8 * self.render.gui_scale
        for index in range(10):
            px = x + index * spacing
            self.render.blit(empty, (px, y))
            units = value - index * 2.0
            if units >= 2.0:
                self.render.blit(full, (px, y))
            elif units > 0.0:
                self.render.blit(half, (px, y))
        return True

    def _health_animation(self, player, now_ms):
        """Track the delayed damage overlay independently of rendering FPS."""
        health = max(0, math.ceil(player.health))
        tick = now_ms // 50
        if self._health_player is not player:
            self._health_player = player
            self._last_health = self._display_health = health
            self._health_changed_ms = now_ms
            self._blink_until = 0
        if health != self._last_health:
            self._health_changed_ms = now_ms
            self._blink_until = tick + (20 if health < self._last_health else 10)
        if now_ms - self._health_changed_ms > 1000:
            self._display_health = health
            self._health_changed_ms = now_ms
        self._last_health = health
        blink = self._blink_until > tick and (self._blink_until - tick) // 3 % 2 == 1
        return health, self._display_health, blink

    def _draw_health(self, player, x: int, y: int) -> int:
        """Draw upper rows first so compressed rows overlap like vanilla."""
        now_ms = pygame.time.get_ticks()
        tick = now_ms // 50
        health, old_health, blink = self._health_animation(player, now_ms)
        rng = random.Random(tick * 312871)
        scale = self.render.gui_scale
        effects = getattr(player, "active_effects", {})
        variant = "poisoned_" if "poison" in effects else "withered_" if "wither" in effects else ""
        maximum = max(float(player.max_health), health, old_health)
        normal_hearts = math.ceil(maximum / 2)
        absorption = max(0, math.ceil(getattr(player, "absorption_amount", 0)))
        total_hearts = normal_hearts + math.ceil(absorption / 2)
        rows = max(1, math.ceil((maximum + absorption) / 20))
        row_step = max(10 - (rows - 2), 3) * scale
        regen = tick % math.ceil(maximum + 5) if "regeneration" in effects else -1
        container = self._icon("heart.container_blinking" if blink else "heart.container")
        for index in range(total_hearts - 1, -1, -1):
            row, column = divmod(index, 10)
            px = round(x + column * 8 * scale)
            offset = rng.randrange(2) if health + absorption <= 4 else 0
            if index < normal_hearts and index == regen:
                offset -= 2
            py = round(y - row * row_step + offset * scale)
            self.render.blit(container, (px, py))
            if index >= normal_hearts:
                units = absorption - (index - normal_hearts) * 2
                absorb_variant = "withered_" if variant == "withered_" else "absorbing_"
                self.render.blit(self._icon(f"heart.{absorb_variant}{'half' if units == 1 else 'full'}"), (px, py))
            if blink and index * 2 < old_health:
                kind = "half" if index * 2 + 1 == old_health else "full"
                self.render.blit(self._icon(f"heart.{variant}{kind}_blinking"), (px, py))
            if index * 2 < health:
                kind = "half" if index * 2 + 1 == health else "full"
                self.render.blit(self._icon(f"heart.{variant}{kind}"), (px, py))
        return round(y - (rows - 1) * row_step)

    def _draw_food(self, player, right: int, y: int):
        tick = pygame.time.get_ticks() // 50
        rng = random.Random(tick * 312871)
        food = max(0, min(20, int(player.food_level)))
        hunger = "hunger" in getattr(player, "active_effects", {})
        suffix = "_hunger" if hunger else ""
        shake = getattr(player, "saturation", 0) <= 0 and tick % (food * 3 + 1) == 0
        scale = self.render.gui_scale
        for index in range(10):
            px = round(right - (index * 8 + 9) * scale)
            py = round(y + (rng.randrange(3) - 1) * scale) if shake else y
            self.render.blit(self._icon(f"food_empty{suffix}"), (px, py))
            if index * 2 < food:
                kind = "half" if index * 2 + 1 == food else "full"
                self.render.blit(self._icon(f"food_{kind}{suffix}"), (px, py))

    # ------------------------------------------------------------------
    #  主绘制方法
    # ------------------------------------------------------------------

    def draw(self):
        """渲染完整的生存HUD（快捷栏 → 经验条 → 生命值 → 饥饿值）。

        在世界绘制之后每帧调用。布局（从下到上）：
        - 快捷栏（继承自 :class:`HotBar`）
        - 经验条，位于快捷栏上方居中
        - 生命心（左）和饥饿鸡腿（右）在同一行，位于经验条上方，
          各自向外偏移一个图标宽度，以在它们之间形成可见间隙。
        """
        # 先绘制快捷栏；物品名称应放在本 HUD 的所有计量条之上，
        # 因此在本方法末尾再绘制它。
        self._draw_hotbar()
        player = self.render.client.client_player
        if player is None:
            return

        # ---- 快捷栏几何信息 ----
        hotbar = self.get_texture(self.render.gui_scale, self.render.client)
        bar_x = (self.render.SCREEN_WIDTH - hotbar.get_width()) // 2
        bar_y = self.render.SCREEN_HEIGHT - hotbar.get_height()
        icon_w = self._icon("heart.container").get_width()

        # ---- 经验条（最下方的辅助行） ----
        experience_background = self.get_texture(
            self.render.gui_scale,
            self.render.client,
            "gui.sprites.hud.experience_bar_background",
        )
        experience_y = (
            bar_y
            - experience_background.get_height()
            - round(self.render.gui_scale * 2)
        )

        # ---- 生命值与饥饿值行（经验条上方） ----
        # 将生命值左移一个图标宽度，饥饿值右移一个图标宽度，
        # 使两个计量条不会紧挨在一起。
        meter_y = experience_y - icon_w - round(self.render.gui_scale * 1)
        health_x = bar_x - (icon_w - self.render.gui_scale * 9)

        health_top_y = self._draw_health(player, health_x, meter_y)
        self._draw_food(player, bar_x + hotbar.get_width(), meter_y)

        try:
            armor_value = player.get_attribute_value("armor")
        except (AttributeError, KeyError, TypeError, ValueError):
            armor_value = 0.0
        armor_y = health_top_y - icon_w - round(self.render.gui_scale)
        armor_visible = self._draw_armor(armor_value, health_x, armor_y)

        # ---- 经验条（填充条 + 等级数字） ----
        self._draw_experience(player, bar_x, bar_y)
        top_meter_y = armor_y if armor_visible else health_top_y
        self.draw_item_name(top_meter_y - round(self.render.gui_scale * 3))

    # ------------------------------------------------------------------
    #  经验条
    # ------------------------------------------------------------------

    def _draw_experience(self, player, x: int, hotbar_y: int):
        """在快捷栏上方绘制经验进度条和等级数字。

        :param player: 本地玩家实体。
        :param x: 屏幕左坐标（与快捷栏对齐）。
        :param hotbar_y: 快捷栏纹理的屏幕顶部坐标。

        """
        background = self.get_texture(
            self.render.gui_scale,
            self.render.client,
            "gui.sprites.hud.experience_bar_background",
        )
        progress = self.get_texture(
            self.render.gui_scale,
            self.render.client,
            "gui.sprites.hud.experience_bar_progress",
        )

        # 将经验条放置在计量条和快捷栏之间。
        y = hotbar_y - background.get_height() - round(self.render.gui_scale * 2)
        self.render.blit(background, (x, y))

        # 根据升级所需经验的进度填充条。
        ratio = min(1.0, player.experience / max(1, player.experience_to_next_level()))
        width = int(progress.get_width() * ratio)
        if width:
            self.render.blit(
                progress.subsurface((0, 0, width, progress.get_height())),
                (x, y),
            )

        # 在经验条上方居中绘制等级数字（绿色带黑色阴影）。
        if player.experience_level > 0:
            text = str(player.experience_level)
            font = self.render.get_font(
                max(12, round(14 * self.render.gui_scale / 3.5))
            )
            surface = font.render(text, True, (128, 255, 32))
            shadow = font.render(text, True, (0, 0, 0))
            center_x = x + background.get_width() // 2
            self.render.render_text(
                text,
                (center_x, y - self.render.gui_scale * 5),
                (128, 255, 32),
                28,
                shadow=True,
            )
