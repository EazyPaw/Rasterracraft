"""
主渲染器
========
Render 类是整个渲染系统的核心，通过多重继承组合以下 Mixin：
  - SkyMixin：天空背景、昼夜循环、天体渲染
  - BlockRenderMixin：方块绘制、光照/AO 计算

负责：窗口管理、主循环、GUI 调度、玩家绘制、文本渲染。
"""

import logging
import math as _math
from collections import OrderedDict
from typing import TYPE_CHECKING

import pygame

from resources.client.GUI.gui import GUI
from resources.client.camera import Camera

from .block import BlockRenderMixin
from .sky import SkyMixin

if TYPE_CHECKING:
    from resources.client.client_main import Client


class Render(SkyMixin, BlockRenderMixin):
    """PyCraft2D 主渲染器。

    负责：
    - pygame 窗口生命周期管理
    - 主渲染循环（start 方法）
    - 屏幕坐标转换
    - GUI 调度
    - 文本与字体管理
    - 方块悬停高亮
    """

    def __init__(self, client: 'Client'):
        """初始化渲染器。

        参数:
            client: Client 主实例引用
        """
        pygame.init()
        pygame.mixer.init()

        # ---- 核心引用 ----
        self.client = client
        self.client_world = client.client_world

        # ---- 屏幕与窗口 ----
        self.SCREEN_WIDTH: int = 800
        self.SCREEN_HEIGHT: int = 600
        self.screen: pygame.Surface = pygame.display.set_mode(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT),
            pygame.RESIZABLE,
        )
        pygame.display.set_caption("PyCraft 2D - 0.0.1 SNAPSHOT")
        self.icon: pygame.Surface = pygame.image.load("icon.png").convert_alpha()
        pygame.display.set_icon(self.icon)

        # ---- 渲染参数 ----
        self.block_size: int = 64
        self.trans_scale: float = self.block_size / 16
        self.gui_scale: float = 3.5
        self.running: bool = False

        # ---- 相机 ----
        self.camera: Camera = Camera()

        # ---- 鼠标与交互 ----
        self.mouse_x: int = 0
        self.mouse_y: int = 0
        self.choosing_position: tuple[int, int] = (0, 0)

        # ---- 字体 ----
        self.font_path: str = "assets\\minecraft\\font\\Minecraft_AE.ttf"
        self.default_font: pygame.font.Font = pygame.font.Font(self.font_path, 36)
        self.font_cache: dict[int, pygame.font.Font] = {}

        # ---- 事件队列 ----
        self.events: list[pygame.event.Event] = []

        # ---- 时间追踪 ----
        self.day_time: float = 0.0
        self.total_day_ticks: float = 0.0
        self._last_daytime_update: int = pygame.time.get_ticks()

        # ---- 天空渲染状态 ----
        self.sky_base = None
        self.sky_layer: pygame.Surface | None = None
        self.sky_cache_key = None
        self.current_sky_state = None
        self.stars: list[tuple[int, int, int]] = self.generate_stars()

        # ---- 天体纹理 ----
        self.sun_texture: pygame.Surface = self.load_environment_texture(
            "assets\\minecraft\\textures\\environment\\sun.png"
        )
        self.moon_phase_textures: list[pygame.Surface] = self.load_moon_phase_textures()

        # ---- GUI 叠加层（半透明暗色背景） ----
        self.ig_gui_layer: pygame.Surface = pygame.Surface(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        self.ig_gui_layer.fill((0, 0, 0, 128))

        # ---- 渲染缓存（LRU 淘汰策略） ----
        self.gradient_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_GRADIENT_CACHE: int = 256
        self.lit_tex_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_LIT_CACHE: int = 768
        self.corner_color_cache: OrderedDict[tuple, tuple[int, int, int]] = OrderedDict()
        self.MAX_CORNER_COLOR_CACHE: int = 4096
        self.celestial_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_CELESTIAL_CACHE: int = 128

        # ---- AO 系数 ----
        self.ao_multiple: float = 0.05

        # ---- GUI 列表 ----
        self.drawing_GUIs: list[GUI] = []

        # ---- 供外部使用的绘制方法引用 ----
        self.blit = self.screen.blit
        self.debug = False

    # ===================== 坐标转换 =====================

    def transform_pos(self, pos: tuple[float, float]) -> tuple[float, float]:
        """将相对坐标 [0, 100] 转换为绝对屏幕坐标。

        用于处理窗口大小变化时的 GUI 自适应布局。

        参数:
            pos: 相对坐标 (x, y)，范围 [0, 100]

        返回:
            绝对像素坐标
        """
        x = pos[0] / 100 * self.SCREEN_WIDTH
        y = pos[1] / 100 * self.SCREEN_HEIGHT
        return x, y

    def trans_world_location(self, pos: tuple[float, float]) -> tuple[float, float]:
        """将世界坐标转换为屏幕坐标。

        坐标变换公式（等轴测正交投影）：
          screen_x = (world_x - camera_x - 0.5) * block_size + screen_width / 2
          screen_y = screen_height - ((world_y - camera_y + 0.5) * block_size + screen_height / 2)

        参数:
            pos: 世界坐标 (world_x, world_y)

        返回:
            屏幕像素坐标 (screen_x, screen_y)
        """
        world_x, world_y = pos
        screen_x = (world_x - self.camera.x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
        screen_y = self.SCREEN_HEIGHT - ((world_y - self.camera.y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2)
        return screen_x, screen_y

    # ===================== Surface 工具方法（静态） =====================

    @staticmethod
    def create_surface(size: tuple[int, int], *, alpha: bool = False, convert: bool = False) -> pygame.Surface:
        """创建 pygame Surface 的便捷方法。

        参数:
            size: 尺寸 (width, height)
            alpha: 是否启用 Alpha 通道
            convert: 是否立即转换像素格式（提升 blit 性能）

        返回:
            创建的 Surface
        """
        surface = pygame.Surface(size, pygame.SRCALPHA if alpha else 0)
        if convert:
            return surface.convert_alpha() if alpha else surface.convert()
        return surface

    @staticmethod
    def scale_surface(surface: pygame.Surface, size: tuple[int, int], *, smooth: bool = False) -> pygame.Surface:
        """缩放 Surface 的便捷方法。

        参数:
            surface: 原始 Surface
            size: 目标尺寸
            smooth: 是否使用平滑缩放（smoothscale）

        返回:
            缩放后的 Surface
        """
        if smooth:
            return pygame.transform.smoothscale(surface, size)
        return pygame.transform.scale(surface, size)

    @staticmethod
    def fill_surface(surface: pygame.Surface, color: tuple[int, ...], rect=None, special_flags: int = 0) -> None:
        """填充 Surface 的便捷包装。"""
        surface.fill(color, rect, special_flags)

    @staticmethod
    def blit_to(target: pygame.Surface, source: pygame.Surface, dest, area=None, special_flags: int = 0) -> None:
        """blit 操作的便捷包装。"""
        target.blit(source, dest, area, special_flags)

    def draw_rect(
        self,
        color: tuple[int, ...],
        rect,
        width: int = 0,
        *,
        surface: pygame.Surface | None = None,
    ) -> None:
        """绘制矩形的便捷方法。

        参数:
            color: 矩形颜色
            rect: 矩形区域
            width: 线宽（0 = 填充）
            surface: 目标 Surface（默认屏幕）
        """
        pygame.draw.rect(surface or self.screen, color, rect, width)

    def draw_line(
        self,
        color: tuple[int, ...],
        start_pos,
        end_pos,
        width: int = 1,
        *,
        surface: pygame.Surface | None = None,
    ) -> None:
        """绘制直线的便捷方法。

        参数:
            color: 线条颜色
            start_pos: 起点坐标
            end_pos: 终点坐标
            width: 线宽
            surface: 目标 Surface（默认屏幕）
        """
        pygame.draw.line(surface or self.screen, color, start_pos, end_pos, width)

    # ===================== 主循环 =====================

    def start(self) -> None:
        """启动渲染主循环。

        每帧执行：
        1. 处理事件（退出、窗口大小变化、游戏事件）
        2. 若在游戏中：绘制天空 → 更新相机 → 绘制方块 → 悬停高亮 → 绘制玩家 → GUI
        3. 若不在游戏中：填充黑屏 → 仅绘制 GUI
        4. 交换缓冲区（flip）
        """
        self.running = True
        self.sky_base = (120, 167, 255)
        clock = pygame.time.Clock()

        while self.running:
            # ---- 事件处理 ----
            self.events = pygame.event.get()
            for event in self.events:
                if event.type == pygame.QUIT:
                    self.running = False
                    self.client.shutdown()
                elif event.type == pygame.VIDEORESIZE:
                    # 窗口大小变化：重建所有尺寸相关的资源
                    self.SCREEN_WIDTH, self.SCREEN_HEIGHT = event.size
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                    self.sky_cache_key = None
                    self.stars = self.generate_stars()
                    self.celestial_cache.clear()
                    self.ig_gui_layer = pygame.Surface(
                        (self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA
                    )
                    self.ig_gui_layer.fill((0, 0, 0, 128))
                else:
                    # 键盘、鼠标等游戏事件转发给 GameManager
                    self.client.game_manager.event_queue.append(event)

            # 退出检查
            if not self.running or self.client.is_shutting_down:
                break

            try:
                if self.client.in_game and self.client.client_player is not None:
                    # ---- 游戏内渲染流程 ----
                    self.draw_sky()                          # 天空背景（来自 SkyMixin）
                    self.camera.update()
                    self.draw_block()                        # 方块绘制（来自 BlockRenderMixin）
                    self.draw_hovered_block_outline()
                    self.client.client_player.skeleton.update()
                    self.draw_player()
                    self.draw_gui()

                    # 帧率显示
                    fps = clock.get_fps()
                    self.render_text(f"FPS: {int(fps)}", (10, 10), (255, 255, 255), 36, True)
                else:
                    # ---- 非游戏状态：黑屏 + GUI ----
                    self.screen.fill((0, 0, 0))
                    self.draw_gui()

                pygame.display.flip()
                clock.tick(250)

            except pygame.error as e:
                logging.debug(f"Pygame error during shutdown: {e}")
                break

    # ===================== GUI 管理 =====================

    def draw_gui(self) -> None:
        """按优先级顺序绘制所有活动 GUI。"""
        for gui in self.drawing_GUIs:
            gui.draw()

    def show_gui(self, gui: GUI) -> None:
        """打开一个 GUI 界面。

        GUI 按优先级排序绘制，优先级高的 GUI 绘制在上层。

        参数:
            gui: 要打开的 GUI 实例
        """
        if gui in self.drawing_GUIs:
            return
        self.drawing_GUIs.append(gui)
        self.drawing_GUIs.sort(key=lambda gui_: gui_.priority)
        gui.on_open()

    def close_gui(self, gui: GUI) -> None:
        """关闭一个 GUI 界面。

        参数:
            gui: 要关闭的 GUI 实例
        """
        if gui not in self.drawing_GUIs:
            return
        self.drawing_GUIs.remove(gui)
        gui.on_close()

    # ===================== 玩家与交互 =====================

    def draw_player(self) -> None:
        """绘制玩家实体。"""
        self.client.client_player.skeleton.draw()

    def get_hovered_block_position(self) -> tuple[int | None, int | None]:
        """获取鼠标当前悬停的方块世界坐标。

        使用逆投影将屏幕坐标转换为世界坐标，并检查交互距离。

        返回:
            (block_x, block_y) 或 (None, None)（超出交互范围时）
        """
        self.mouse_x, self.mouse_y = pygame.mouse.get_pos()

        # 逆投影：屏幕 → 世界
        world_x = (self.mouse_x - self.SCREEN_WIDTH // 2) / self.block_size + self.camera.x + 0.5
        world_y = -(self.mouse_y - self.SCREEN_HEIGHT // 2) / self.block_size + self.camera.y - 0.5

        block_x = _math.floor(world_x)
        block_y = _math.floor(world_y)

        # 距离检查
        distance = _math.sqrt(
            (self.mouse_x - self.SCREEN_WIDTH / 2) ** 2 +
            (self.mouse_y - self.SCREEN_HEIGHT / 2) ** 2
        ) / self.block_size

        if distance > self.client.client_player.interact_range:
            return None, None

        self.choosing_position = (block_x, block_y)
        return block_x, block_y

    def draw_hovered_block_outline(self) -> None:
        """绘制鼠标悬停方块的黑色边框高亮。"""
        block_x, block_y = self.get_hovered_block_position()
        if block_x is None or block_y is None:
            return

        # 世界坐标 → 屏幕坐标
        screen_x = (block_x - self.camera.x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
        # 方块占据世界坐标 [block_y, block_y+1]，用 block_y+1 定位顶部
        screen_y = self.SCREEN_HEIGHT - (
            ((block_y + 1) - self.camera.y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2
        )

        outline_rect = pygame.Rect(screen_x, screen_y, self.block_size, self.block_size)
        pygame.draw.rect(self.screen, (0, 0, 0), outline_rect, 1)

    # ===================== 调试 =====================

    def debug_mode(self) -> None:
        """切换调试模式（显示方块光照值）。"""
        self.debug = not self.debug

    # ===================== 文本与字体 =====================

    def get_font(self, size: int) -> pygame.font.Font:
        """获取指定大小的字体（带缓存）。

        参数:
            size: 字体大小（像素）

        返回:
            pygame.font.Font 实例
        """
        if size in self.font_cache:
            return self.font_cache[size]
        font = pygame.font.Font(self.font_path, size)
        self.font_cache[size] = font
        return font

    def render_text(
        self,
        text: str,
        pos: tuple[float, float],
        color: tuple[int, int, int] = (255, 255, 255),
        font_size: int = 36,
        shadow: bool = False,
        shadow_strength = 0.4,
        glow: bool = False,
    ) -> None:
        """在屏幕上渲染文本。

        参数:
            text: 文本内容
            pos: 位置 (x, y)
            color: 文本颜色 RGB
            font_size: 字体大小
            shadow: 是否绘制阴影
            shadow_strength: 阴影亮度
            glow: 是否添加发光效果
        """
        text_surface = self.get_font(font_size).render(text, True, color)
        if shadow:
            # 阴影：深色版本偏移绘制在文本下方
            shadow_color = tuple(int(x * shadow_strength) for x in color)
            shadow_surface = self.get_font(font_size).render(text, True, shadow_color)
            self.screen.blit(shadow_surface, (pos[0] + font_size / 8, pos[1] + font_size / 8))
        self.screen.blit(text_surface, pos)
