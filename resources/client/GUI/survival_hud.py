"""Minecraft风格的生存模式HUD：快捷栏、生命值、饥饿值、经验条以及受伤反馈。

该GUI叠加在快捷栏（HotBar）之上，以原版Minecraft布局渲染状态计量条（生命值和饥饿值）
——生命值在左，饥饿值从右侧镜像排列——经验条则夹在它们与快捷栏之间。
"""

import math

import pygame

from resources.client.GUI.inventory.hotbar import HotBar


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

    # ------------------------------------------------------------------
    #  内部辅助方法
    # ------------------------------------------------------------------

    def _icon(self, name: str) -> pygame.Surface:
        """返回一个尺寸为 9×gui_scale 像素的HUD精灵图，首次使用时加载并缓存。

        参数:
            name: 精灵图ID，例如 ``"heart.full"``。完整纹理路径
                  ``gui.sprites.hud.<name>`` 由资源管理器解析。
        """
        cached = self._icons.get(name)
        if cached is not None:
            return cached
        texture = self.render.client.resources_manager.get_texture_img(
            f"gui.sprites.hud.{name}"
        )
        size = max(1, round(9 * self.render.gui_scale))
        cached = pygame.transform.scale(texture, (size, size))
        self._icons[name] = cached
        return cached

    def _draw_meter(self, value: float, maximum: float, x: int, y: int, *, food: bool):
        """绘制一行包含10个图标的计量条（生命心或饥饿鸡腿）。

        生命值从左向右填充；饥饿值从右向左填充（镜像），
        使得两个计量条在快捷栏上方自然相对。

        参数:
            value:   当前玩家属性值（例如 18.0 生命值）。
            maximum: 最大可能值（例如 20.0）。
            x:       第一个（索引0）图标的屏幕左坐标。
            y:       整行图标的屏幕顶部坐标。
            food:    ``True`` 渲染饥饿鸡腿，``False`` 渲染生命心。
        """
        empty = self._icon("food_empty" if food else "heart.container")
        half = self._icon("food_half" if food else "heart.half")
        full = self._icon("food_full" if food else "heart.full")
        icon_w = empty.get_width()

        # 生命值从左向右填充（索引 0→9）；饥饿值镜像（9→0）
        # 使填充的图标向屏幕中心方向增长。
        for index in range(10):
            display_index = 9 - index if food else index
            px = x + display_index * (icon_w - 4)
            self.render.blit(empty, (px, y))
            units = value - index * (maximum / 10)
            if units >= maximum / 10:
                self.render.blit(full, (px, y))
            elif units > 0:
                self.render.blit(half, (px, y))

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
            self.render.gui_scale, self.render.client,
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
        hunger_x = bar_x + hotbar.get_width() - icon_w * 9

        self._draw_meter(player.health, player.max_health, health_x, meter_y, food=False)
        self._draw_meter(player.food_level, 20, hunger_x, meter_y, food=True)

        # ---- 经验条（填充条 + 等级数字） ----
        self._draw_experience(player, bar_x, bar_y)
        self.draw_item_name(meter_y - round(self.render.gui_scale * 3))

    # ------------------------------------------------------------------
    #  经验条
    # ------------------------------------------------------------------

    def _draw_experience(self, player, x: int, hotbar_y: int):
        """在快捷栏上方绘制经验进度条和等级数字。

        参数:
            player:    本地玩家实体。
            x:         屏幕左坐标（与快捷栏对齐）。
            hotbar_y:  快捷栏纹理的屏幕顶部坐标。
        """
        background = self.get_texture(
            self.render.gui_scale, self.render.client,
            "gui.sprites.hud.experience_bar_background",
        )
        progress = self.get_texture(
            self.render.gui_scale, self.render.client,
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
            font = self.render.get_font(max(12, round(14 * self.render.gui_scale / 3.5)))
            surface = font.render(text, True, (128, 255, 32))
            shadow = font.render(text, True, (0, 0, 0))
            center_x = x + background.get_width() // 2
            self.render.render_text(text, (center_x, y - self.render.gui_scale * 5), (128, 255, 32), 28, shadow = True)
            # self.render.blit(shadow, shadow.get_rect(center=(center_x + 1, y - 1)))
            # self.render.blit(surface, surface.get_rect(center=(center_x, y - 2)))
