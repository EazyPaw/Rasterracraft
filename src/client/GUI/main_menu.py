# Commented and arranged by ChatGPT
from src.client.GUI.menu_style import draw_dirt, gui_scale

import pygame

from src.client.GUI.button import Button
from src.client.GUI.gui import GUI
from src.client.GUI.multiplayer_menu import MultiplayerMenu
from src.client.GUI.saves_menu import SavesMenu
from src.client.resources_manager import transkey
from src.server.utils import client_method


class MainMenu(GUI):
    """Minecraft 风格主菜单，支持动态注册按钮。"""

    @client_method
    def __init__(self, render, client=None):
        self.client = client
        # 调用父类初始化
        super().__init__(render)
        # 设置优先级（数值越高，在 GUI 堆栈中越靠前）
        self.priority = 100
        # 存储所有菜单按钮
        self.buttons: list[Button] = []
        # 标记是否正在进入世界，避免重复触发
        self.starting_world = False
        # 背景缓存（加速重绘）
        self._background_cache = None
        # 背景缓存对应的屏幕尺寸键值
        self._background_cache_key = None
        # 添加默认的“单人游戏”按钮
        self.add_button(transkey("menu.singleplayer"), self.start_singleplayer)
        self.add_button(transkey("menu.multiplayer"), self.open_multiplayer)
        self.add_button(transkey("mods.title"), self.open_mods)
        self.add_button(transkey("menu.quit"), client.shutdown)

    def add_button(
        self,
        text: str,
        callback=None,
        *,
        size: tuple[int, int] = Button.DEFAULT_SIZE,
        enabled: bool = True,
        visible: bool = True,
    ) -> Button:
        """
        注册一个菜单按钮。
        后续其他 GUI 可借助此方法扩展按钮。
        """
        button = Button(text, callback, size=size, enabled=enabled, visible=visible)
        self.buttons.append(button)
        return button

    def clear_buttons(self):
        """清空所有按钮"""
        self.buttons.clear()

    def start_singleplayer(self):
        """启动单人游戏：关闭本菜单并打开存档选择菜单"""
        if self.starting_world:
            return
        self.render.close_gui(self)  # 关闭主菜单
        self.render.client.saves_menu = SavesMenu(self.render, self)
        self.render.show_gui(self.render.client.saves_menu)  # 显示存档菜单

    def open_multiplayer(self):
        """打开直接连接页面，由玩家输入服务器地址。"""
        if self.starting_world:
            return
        self.render.close_gui(self)
        self.render.client.multiplayer_menu = MultiplayerMenu(self.render, self)
        self.render.show_gui(self.render.client.multiplayer_menu)

    def open_mods(self):
        if self.starting_world or self.client.game_started:
            return
        from src.client.GUI.mods_menu import ModsMenu
        self.render.close_gui(self)
        self.render.show_gui(ModsMenu(self.render, self))

    def draw(self):
        """绘制主菜单：布局按钮、背景、Logo 和页脚"""
        self._layout_buttons()
        self._draw_background()
        self._draw_logo()
        for button in self.buttons:
            button.draw(self.render)
        self._draw_footer()
        service = getattr(self.render.client, "mod_service", None)
        if service is not None:
            active = {record.ctx.namespace for record in service.manager.loaded}
            active.update(service.server_status.get("loaded", []))
            self.render.render_text(transkey("mods.enabledCount", len(active)), (2 * gui_scale(self.render), 2 * gui_scale(self.render)), (255, 255, 255), 8 * gui_scale(self.render), True)

    def handle_events(self, events: list[pygame.event.Event]):
        """
        处理事件循环中的事件。
        优先让按钮响应鼠标事件，按下回车或小键盘回车时触发当前可见且启用的按钮。
        """
        for event in events[:]:
            if event.type in (
                pygame.MOUSEMOTION,
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
            ):
                handled = False
                for button in self.buttons:
                    if button.handle_event(event):
                        handled = True
                # 如果事件被按钮处理，则从事件列表中移除，防止其他 GUI 重复处理
                if handled and event in events:
                    events.remove(event)
            elif event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN,
                pygame.K_KP_ENTER,
            ):
                # 回车键触发第一个可见且启用的按钮
                for button in self.buttons:
                    if button.enabled and button.visible:
                        button.click()
                        events.remove(event)
                        break

    def _layout_buttons(self):
        scale = gui_scale(self.render)
        w, h = self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT
        buttons = [button for button in self.buttons if button.visible]
        gap = 4 * scale
        sizes = [(min(200 * scale, w - 24), 20 * scale)
                 if button.default_size == Button.DEFAULT_SIZE else button.default_size
                 for button in buttons]
        total = sum(height for _, height in sizes) + gap * max(0, len(sizes) - 1)
        y = min(h // 4 + 48 * scale, h - total - 24 * scale)
        for button, (width, height) in zip(buttons, sizes):
            button.set_rect((w - width) // 2, y, width, height)
            y += height + gap

    def _draw_background(self):
        draw_dirt(self)

    def _build_background(self):
        draw_dirt(self)
        return self._dirt_style_surface

    def _draw_logo(self):
        w, h = self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT
        scale = gui_scale(self.render)
        logo = self.render.client.resources_manager.get_texture_img("gui.title.minecraft", True)
        if logo is None:
            return
        ratio = min(274 * scale / logo.get_width(), (w - 32) / logo.get_width(),
                    h * .23 / logo.get_height())
        size = (max(1, int(logo.get_width() * ratio)), max(1, int(logo.get_height() * ratio)))
        self.render.blit(self.render.scale_surface(logo, size), ((w - size[0]) // 2, 30 * scale))

    def _draw_footer(self):
        scale = gui_scale(self.render)
        size = 8 * scale
        y = self.render.SCREEN_HEIGHT - self.render.get_font(size).get_height() - 2 * scale
        self.render.render_text(str(getattr(self.render.client, "version", "")),
                                (2 * scale, y), (255, 255, 255), size, True)
        text = "Minecraft assets by Mojang Studios"
        x = self.render.SCREEN_WIDTH - self.render.get_font(size).size(text)[0] - 2 * scale
        self.render.render_text(text, (x, y), (255, 255, 255), size, True)
