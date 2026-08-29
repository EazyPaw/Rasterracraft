# Commented and arranged by ChatGPT
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

    def draw(self):
        """绘制主菜单：布局按钮、背景、Logo 和页脚"""
        self._layout_buttons()
        self._draw_background()
        self._draw_logo()
        for button in self.buttons:
            button.draw(self.render)
        self._draw_footer()

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
        """
        计算并设置每个按钮的位置和尺寸。
        按钮宽度与窗口宽度成比例，高度与窗口高度成比例，并有上下限。
        所有可见按钮在屏幕垂直方向 38%~68% 区域内垂直居中排列。
        """
        screen_w = self.render.SCREEN_WIDTH
        screen_h = self.render.SCREEN_HEIGHT

        # 按钮尺寸随窗口缩放，并限定合理范围
        button_w = max(180, min(400, int(screen_w * 0.35)))
        button_h = max(28, min(48, int(screen_h * 0.055)))
        gap = max(4, int(button_h * 0.3))  # 按钮之间的间距

        visible_buttons = [b for b in self.buttons if b.visible]
        if not visible_buttons:
            return

        # 收集每个可见按钮的实际尺寸（若未自定义则使用默认尺寸）
        button_sizes = [
            (button_w, button_h)
            if button.default_size == Button.DEFAULT_SIZE
            else button.default_size
            for button in visible_buttons
        ]
        # 计算所有按钮加上间距的总高度
        total_h = sum(size[1] for size in button_sizes) + gap * (
            len(visible_buttons) - 1
        )

        # 按钮垂直区间：屏幕 38%~68% 高度
        button_zone_top = int(screen_h * 0.38)
        button_zone_bottom = int(screen_h * 0.68)
        button_zone_height = button_zone_bottom - button_zone_top
        y = button_zone_top + (button_zone_height - total_h) // 2

        # 防止按钮组超出屏幕底部（保留 5% 边距）
        if y + total_h > screen_h - int(screen_h * 0.05):
            y = screen_h - int(screen_h * 0.05) - total_h

        # 逐个设置按钮的位置和尺寸
        for button, (width, height) in zip(visible_buttons, button_sizes):
            button.set_rect((screen_w - width) // 2, y, width, height)
            y += height + gap

    def _draw_background(self):
        """
        绘制背景（泥土纹理 + 半透明遮罩）。
        采用缓存策略，仅当窗口尺寸变化时重新生成。
        """
        cache_key = (self.render.SCREEN_WIDTH, self.render.SCREEN_HEIGHT)
        if self._background_cache is None or self._background_cache_key != cache_key:
            self._background_cache = self._build_background()
            self._background_cache_key = cache_key
        self.render.blit(self._background_cache, (0, 0))

    def _build_background(self):
        """
        构建背景表面：平铺泥土纹理，并覆盖半透明黑色遮罩。
        瓦片大小根据窗口短边的 1/12 自适应，限制在 32~128 之间。
        """
        width = self.render.SCREEN_WIDTH
        height = self.render.SCREEN_HEIGHT
        surface = self.render.create_surface((width, height), convert=True)
        dirt = self.render.client.resources_manager.get_texture_img("blocks.dirt")
        tile_size = max(32, min(128, min(width, height) // 12))
        tile = self.render.scale_surface(dirt, (tile_size, tile_size))

        # 平铺泥土
        for x in range(0, width, tile_size):
            for y in range(0, height, tile_size):
                self.render.blit_to(surface, tile, (x, y))

        # 叠加半透明遮罩
        shade = self.render.create_surface((width, height), alpha=True)
        self.render.fill_surface(shade, (0, 0, 0, 115))
        self.render.blit_to(surface, shade, (0, 0))
        return surface

    def _draw_logo(self):
        """
        绘制游戏 Logo。
        Logo 位于屏幕顶部 35% 区域，宽度不超过屏幕 50%，高度不超过该区域的 60%，
        同时限制最大放大倍数为 2.5 倍以防止模糊。
        """
        screen_w = self.render.SCREEN_WIDTH
        screen_h = self.render.SCREEN_HEIGHT
        logo = self.render.client.resources_manager.get_texture_img(
            "gui.title.minecraft", True
        )

        logo_zone_height = int(screen_h * 0.35)  # Logo 所在区域高度

        # 计算缩放比例：宽度不超过屏幕 50%，高度不超过区域高度的 60%
        max_w = int(screen_w * 0.50)
        max_h = int(logo_zone_height * 0.60)
        scale_w = max_w / logo.get_width()
        scale_h = max_h / logo.get_height()
        scale = min(scale_w, scale_h, 2.5)  # 最大放大 2.5 倍
        logo_w = int(logo.get_width() * scale)
        logo_h = int(logo.get_height() * scale)
        logo_surface = self.render.scale_surface(logo, (logo_w, logo_h))

        # 在 Logo 区域内居中
        x = (screen_w - logo_w) // 2
        y = (logo_zone_height - logo_h) // 2
        self.render.blit(logo_surface, (x, y))

    def _draw_footer(self):
        """
        绘制页脚：显示版本信息和版权声明。
        字体大小随窗口高度缩放。
        """
        version = getattr(self.render.client, "version", "")
        footer_font_size = max(16, int(self.render.SCREEN_HEIGHT * 0.026))
        y = self.render.SCREEN_HEIGHT - footer_font_size - 8

        # 左侧：版本号
        self.render.render_text(
            f"{version}", (8, y), (255, 255, 255), footer_font_size, True
        )

        # 右侧：版权文字
        copyright_text = "Minecraft assets by Mojang Studios"
        font = self.render.get_font(footer_font_size)
        x = self.render.SCREEN_WIDTH - font.size(copyright_text)[0] - 8
        self.render.render_text(
            copyright_text, (x, y), (255, 255, 255), footer_font_size, True
        )
