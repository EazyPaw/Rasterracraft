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
import os
from collections import OrderedDict
from typing import TYPE_CHECKING

import pygame

from resources.client.GUI.gui import GUI
from resources.client.camera import Camera
from resources.server.biome import get_biome_by_id
from resources.server.block_class import PlacementContext
from resources.server.text import Text

from .block import BlockRenderMixin
from .constants import BLOCK_TINT_COLOR_STEP
from .render_utils import cyclic_lerp_color, lerp_color, quantize_color, draw_dashed_rect
from .sky import SkyMixin
from .weather import WeatherMixin

if TYPE_CHECKING:
    from resources.client.client_main import Client


class Render(WeatherMixin, SkyMixin, BlockRenderMixin):
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
        # SDL2 默认隐藏原生输入法候选窗；必须在视频子系统初始化前启用。
        os.environ["SDL_IME_SHOW_UI"] = "1"
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

        # SDL 的文本输入 API 必须由窗口主线程驱动。GUI 事件在游戏线程
        # 消费，只更新下面的请求状态，真正的 start/stop 在渲染循环执行。
        self._text_input_requested = False
        self._text_input_active = False
        self._text_input_rect: pygame.Rect | None = None
        self._text_input_repeat = (0, 0)
        self._window_focused = True
        pygame.key.stop_text_input()
        pygame.key.set_repeat(0, 0)

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
        self.font_cache: dict[int | tuple[int, bool], pygame.font.Font] = {}

        # ---- 事件队列 ----
        self.events: list[pygame.event.Event] = []

        # ---- 时间追踪 ----
        self.day_time: float = 0.0
        self.total_day_ticks: float = 0.0
        self._last_daytime_update: int = pygame.time.get_ticks()

        # ---- FPS 统计 ----
        self._fps_samples: list[float] = []
        self._fps_display_text: str = "avg. 0 max. 0 min. 0"
        self._last_fps_update: int = pygame.time.get_ticks()

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
        self.init_weather_rendering()

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
        self.tinted_surface_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_TINTED_SURFACE_CACHE: int = 768
        self.block_section_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_BLOCK_SECTION_CACHE: int = 192
        self.block_section_surface_pool: dict[tuple[int, int], list[pygame.Surface]] = {}
        self.MAX_BLOCK_SECTION_SURFACE_POOL: int = 64
        self.block_section_animation_cache: OrderedDict[tuple, tuple[str, ...]] = OrderedDict()
        self.MAX_BLOCK_SECTION_ANIMATION_CACHE: int = 256
        self.block_section_direct_cache: OrderedDict[tuple, bool] = OrderedDict()
        self.MAX_BLOCK_SECTION_DIRECT_CACHE: int = 256
        self.animated_texture_path_cache: dict[str, bool] = {}
        self.partial_alpha_surface_cache: dict[int, bool] = {}
        self.BLOCK_SECTION_WIDTH: int = 8
        self.BLOCK_SECTION_HEIGHT: int = 4
        self.MAX_BLOCK_SECTION_PREFETCH_PER_FRAME: int = 2
        self._last_block_cache_cam: tuple[float, float] | None = None
        self.biome_debug_colors: dict[str, tuple[int, int, int]] = {}

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

    def get_world_light_tint(self, world_x: float, world_y: float) -> tuple[int, int, int]:
        block_x = _math.floor(world_x)
        block_y = _math.floor(world_y)
        chunk_rx = block_x // 16
        local_x = block_x % 16

        sky_map = getattr(self.client_world, "sky_light_map", {}).get(chunk_rx)
        block_map = getattr(self.client_world, "block_light_map", {}).get(chunk_rx)
        if sky_map is None or block_map is None:
            return (255, 255, 255)
        if block_y < 0 or block_y >= self.client_world.y_max:
            return (255, 255, 255)

        sky_state = self.current_sky_state or self.get_sky_state()
        sky_level = float(sky_map[local_x, block_y]) / 15.0 * sky_state["sky_light_weight"]
        block_level = float(block_map[local_x, block_y]) / 15.0
        brightness = min(1.0, sky_level + block_level)
        if brightness <= 0.0:
            return (0, 0, 0)

        night_tint = (36, 48, 128)
        sky_color = lerp_color(
            cyclic_lerp_color(self.SKY_LOWER_KEYFRAMES, self.day_time),
            sky_state["twilight_color"],
            sky_state["twilight"],
        )
        sky_color = lerp_color(sky_color, night_tint, sky_state["night"] * 0.85)
        sky_color = quantize_color(sky_color, BLOCK_TINT_COLOR_STEP)
        total = sky_level + block_level
        sky_ratio = sky_level / total if total > 0.001 else 0.5
        return self._compute_corner_color(brightness, sky_ratio, sky_color)

    def get_tinted_surface(self, surface: pygame.Surface, tint: tuple[int, int, int]) -> pygame.Surface:
        if tint == (255, 255, 255):
            return surface
        key = (surface, tint)
        cache = self.tinted_surface_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]

        tinted = surface.copy()
        mask = pygame.Surface(tinted.get_size())
        mask.fill(tint)
        tinted.blit(mask, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        cache[key] = tinted
        if len(cache) > self.MAX_TINTED_SURFACE_CACHE:
            cache.popitem(last=False)
        return tinted

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
                    self._weather_texture_cache.clear()
                    self._weather_lit_cache.clear()
                    self._cloud_surface_cache.clear()
                    self.tinted_surface_cache.clear()
                    self.block_section_cache.clear()
                    self.block_section_surface_pool.clear()
                    self.block_section_animation_cache.clear()
                    self.block_section_direct_cache.clear()
                    self._last_block_cache_cam = None
                    self.ig_gui_layer = pygame.Surface(
                        (self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA
                    )
                    self.ig_gui_layer.fill((0, 0, 0, 128))
                else:
                    if event.type == pygame.WINDOWFOCUSLOST:
                        self._window_focused = False
                    elif event.type == pygame.WINDOWFOCUSGAINED:
                        self._window_focused = True
                    # 键盘、鼠标等游戏事件转发给 GameManager
                    self.client.game_manager.event_queue.append(event)

            self._sync_text_input_state()

            # 退出检查
            if not self.running or self.client.is_shutting_down:
                break

            try:
                if self.client.in_game and self.client.client_player is not None:
                    # ---- 游戏内渲染流程 ----
                    self.draw_sky()                          # 天空背景（来自 SkyMixin）
                    self.camera.update()
                    self.draw_entities(z_filter=1)
                    self.draw_block()                        # 方块绘制（来自 BlockRenderMixin）
                    if self.debug:
                        self.draw_biome_debug_overlay()
                    self.draw_precipitation()
                    self.draw_entities(z_filter=0)
                    # Keep particles in their world layer.  In particular,
                    # rain splashes on z=0 must remain over the foreground,
                    # while z=1 splashes are not accidentally mixed into it.
                    self.client.particle_manager.draw(self, z_filter=1)
                    self.client.particle_manager.draw(self, z_filter=0)
                    self.draw_hovered_block_outline()
                    self.draw_destroy_progress()
                    self.client.client_player.skeleton.update()
                    self.draw_player()
                    self.draw_gui()

                    # 帧率统计（每秒更新一次）
                    current_ticks = pygame.time.get_ticks()
                    self._fps_samples.append(clock.get_fps())
                    if current_ticks - self._last_fps_update >= 1000:
                        if self._fps_samples:
                            avg_fps = sum(self._fps_samples) / len(self._fps_samples)
                            max_fps = max(self._fps_samples)
                            min_fps = min(self._fps_samples)
                            self._fps_display_text = (
                                f"avg. {int(avg_fps)} max. {int(max_fps)} min. {int(min_fps)}"
                            )
                        self._fps_samples.clear()
                        self._last_fps_update = current_ticks
                    self.render_text(self._fps_display_text, (10, 10), (255, 255, 255), 36, True)
                else:
                    # ---- 非游戏状态：黑屏 + GUI ----
                    self.stop_weather_audio()
                    self.screen.fill((0, 0, 0))
                    self.draw_gui()

                pygame.display.flip()
                clock.tick(250)

            except pygame.error as e:
                logging.debug(f"Pygame error during shutdown: {e}")
                break

        # 退出按钮会在后台继续完成存档和线程清理。pygame
        # 由创建并驱动窗口的渲染主线程关闭，避免跨线程退出死锁。
        if self.client.is_shutting_down:
            pygame.quit()

    # ===================== GUI 管理 =====================

    def request_text_input(
        self,
        enabled: bool,
        rect: pygame.Rect | None = None,
        repeat: tuple[int, int] = (0, 0),
    ) -> None:
        """线程安全地请求主线程启停 SDL 文本输入。"""
        self._text_input_requested = bool(enabled)
        self._text_input_rect = pygame.Rect(rect) if rect is not None else None
        self._text_input_repeat = repeat if enabled else (0, 0)

    def _sync_text_input_state(self) -> None:
        """只在渲染/窗口线程调用 SDL 键盘与 IME API。"""
        should_be_active = self._text_input_requested and self._window_focused
        if should_be_active and self._text_input_rect is not None:
            pygame.key.set_text_input_rect(self._text_input_rect)
        if should_be_active != self._text_input_active:
            if should_be_active:
                pygame.key.start_text_input()
            else:
                pygame.key.stop_text_input()
            self._text_input_active = should_be_active
        pygame.key.set_repeat(*(
            self._text_input_repeat if should_be_active else (0, 0)
        ))

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

    def draw_entities(self, z_filter: int | None = None) -> None:
        """绘制服务端同步的非本地实体。"""
        entities = self.client_world.iter_entities()
        entities.sort(key=lambda entity: entity.y)
        for entity in entities:
            if entity.entity_id in (
                "falling_block", "item", "zombie", "primed_tnt",
                "chicken", "cow", "pig", "sheep",
            ):
                if entity.z != z_filter:
                    continue
            elif z_filter == 1:
                continue
            if entity.skeleton is not None:
                entity.skeleton.update()
                entity.skeleton.draw()

    def get_mouse_world_position(self) -> tuple[float, float]:
        """将当前鼠标位置转换为世界坐标。"""
        self.mouse_x, self.mouse_y = pygame.mouse.get_pos()
        return (
            (self.mouse_x - self.SCREEN_WIDTH // 2) / self.block_size + self.camera.x + 0.5,
            -(self.mouse_y - self.SCREEN_HEIGHT // 2) / self.block_size + self.camera.y - 0.5,
        )

    def get_hovered_entity(self):
        """Return the closest damageable entity under the cursor and in reach."""
        player = self.client.client_player
        if player is None:
            return None
        mouse_x, mouse_y = self.get_mouse_world_position()
        player_center_x = player.x + player.width * 0.5
        player_center_y = player.y + player.height * 0.5
        reach_sq = max(0.0, float(player.interact_range)) ** 2
        candidates = []
        for entity in self.client_world.iter_entities():
            if getattr(entity, "health", 0) <= 0:
                continue
            if int(getattr(entity, "z", 0)) != int(getattr(player, "z", 0)):
                continue
            if not (
                entity.x <= mouse_x <= entity.x + entity.width
                and entity.y <= mouse_y <= entity.y + entity.height
            ):
                continue
            nearest_x = min(max(player_center_x, entity.x), entity.x + entity.width)
            nearest_y = min(max(player_center_y, entity.y), entity.y + entity.height)
            distance_sq = (
                (nearest_x - player_center_x) ** 2
                + (nearest_y - player_center_y) ** 2
            )
            if distance_sq <= reach_sq:
                candidates.append((distance_sq, entity))
        if not candidates:
            return None
        return min(candidates, key=lambda item: item[0])[1]

    def get_hovered_block_position(self) -> tuple[int | None, int | None]:
        """获取鼠标当前悬停的方块世界坐标。

        使用逆投影将屏幕坐标转换为世界坐标，并检查交互距离。

        返回:
            (block_x, block_y) 或 (None, None)（超出交互范围时）
        """
        world_x, world_y = self.get_mouse_world_position()

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

    @staticmethod
    def _ray_hit_face(origin: tuple[float, float], direction: tuple[float, float],
                      location) -> str | None:
        """返回射线进入方块矩形时首先穿过的面。"""
        ox, oy = origin
        dx, dy = direction
        x0, x1 = location.x, location.x + 1
        y0, y1 = location.y, location.y + 1
        epsilon = 1e-8
        candidates = []

        def add_candidate(t, face, coordinate, low, high):
            if t <= epsilon:
                return
            other = coordinate(t)
            if low - epsilon <= other <= high + epsilon:
                candidates.append((t, face))

        if dx > epsilon:
            add_candidate((x0 - ox) / dx, "left", lambda t: oy + dy * t, y0, y1)
        elif dx < -epsilon:
            add_candidate((x1 - ox) / dx, "right", lambda t: oy + dy * t, y0, y1)
        if dy > epsilon:
            add_candidate((y0 - oy) / dy, "bottom", lambda t: ox + dx * t, x0, x1)
        elif dy < -epsilon:
            add_candidate((y1 - oy) / dy, "top", lambda t: ox + dx * t, x0, x1)
        return min(candidates, default=(0, None))[1]

    def get_placement_context(self, target, player=None) -> PlacementContext | None:
        """从玩家视线构造可复用的定向放置上下文。"""
        location = getattr(target, "location", None)
        if location is None:
            return None
        player = player or getattr(self.client, "client_player", None)
        if player is None:
            return None
        mouse_world = self.get_mouse_world_position()
        eye = (
            player.x + getattr(player, "width", 0.3) * 0.5,
            player.y + getattr(player, "height", 1.8) * 0.9,
        )
        direction = (mouse_world[0] - eye[0], mouse_world[1] - eye[1])
        if abs(direction[0]) < 1e-8 and abs(direction[1]) < 1e-8:
            return None
        hit_face = self._ray_hit_face(eye, direction, location)
        return PlacementContext(
            hit_face=hit_face,
            ray_origin=eye,
            ray_direction=direction,
            target_z=0 if getattr(player, "fore_place", False) else int(location.z),
            fore_place=bool(getattr(player, "fore_place", False)),
        )

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

        if getattr(self.client.client_player, "fore_place", False):
            temp_surf = pygame.Surface((outline_rect.width, outline_rect.height), pygame.SRCALPHA)
            temp_surf.fill((255, 255, 255, 20))
            self.screen.blit(temp_surf, (outline_rect.x, outline_rect.y))
        if not any(
            getattr(self.client_world.get_block(block_x, block_y, z), "solid", False)
            for z in (0, 1)
        ):
            draw_dashed_rect(self.screen, (0, 0, 0), outline_rect, dash_length=8, gap_length=4, width=1)
            return
        pygame.draw.rect(self.screen, (0, 0, 0), outline_rect, 1)

    def draw_destroy_progress(self) -> None:
        """Draw server-authoritative destroy stages for every visible miner."""
        states = self.client_world.iter_break_progress()
        # Multiple players mining one block share one overlay; render the most
        # advanced authoritative stage instead of alpha-stacking duplicates.
        targets: dict[tuple[int, int, int], float] = {}
        for state in states:
            progress = max(0.0, min(1.0, float(state.get('progress', 0.0))))
            if progress <= 0.0:
                continue
            target = (int(state['x']), int(state['y']), int(state['z']))
            targets[target] = max(progress, targets.get(target, 0.0))

        for (x, y, _z), progress in targets.items():
            stage = min(9, max(0, int(progress * 10)))
            texture = self.client.resources_manager.get_texture_img(
                f"blocks.destroy_stage_{stage}", gta=True
            )
            if texture is None:
                continue
            texture = pygame.transform.scale(texture, (self.block_size, self.block_size))
            sx = (x - self.camera.x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
            sy = self.SCREEN_HEIGHT - (
                ((y + 1) - self.camera.y + 0.5) * self.block_size
                + self.SCREEN_HEIGHT // 2
            )
            self.blit(texture, (round(sx), round(sy)))

    # ===================== 调试 =====================

    def debug_mode(self) -> None:
        """切换调试模式（显示方块光照值）。"""
        self.debug = not self.debug

    def draw_biome_debug_overlay(self) -> None:
        """Draw a translucent biome-color overlay and a hover tooltip in debug mode."""
        block_size = self.block_size
        if block_size <= 0:
            return

        x_blocks = _math.ceil(self.SCREEN_WIDTH / block_size)
        y_blocks = _math.ceil(self.SCREEN_HEIGHT / block_size)
        x_start = int(self.camera.x - x_blocks // 2 - 1)
        x_end = int(self.camera.x + x_blocks // 2 + 2)
        y_start = int(self.camera.y - y_blocks // 2 - 1)
        y_end = int(self.camera.y + y_blocks // 2 + 2)

        overlay = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)
        get_biome = self.client_world.get_biome
        for x in range(x_start, x_end + 1):
            for y in range(y_start, y_end + 1):
                biome_id = get_biome(x, y)
                if not biome_id or biome_id == "void":
                    continue
                color = self._biome_debug_color(biome_id)
                sx = (x - self.camera.x - 0.5) * block_size + self.SCREEN_WIDTH // 2
                sy = self.SCREEN_HEIGHT - (
                    ((y + 1) - self.camera.y + 0.5) * block_size + self.SCREEN_HEIGHT // 2
                )
                pygame.draw.rect(overlay, (*color, 58), (sx, sy, block_size, block_size))
                pygame.draw.rect(overlay, (*color, 105), (sx, sy, block_size, block_size), 1)

        self.screen.blit(overlay, (0, 0))
        self.draw_biome_hover_tooltip()

    def draw_biome_hover_tooltip(self) -> None:
        mouse_x, mouse_y = pygame.mouse.get_pos()
        world_x = (mouse_x - self.SCREEN_WIDTH // 2) / self.block_size + self.camera.x + 0.5
        world_y = -(mouse_y - self.SCREEN_HEIGHT // 2) / self.block_size + self.camera.y - 0.5
        block_x = _math.floor(world_x)
        block_y = _math.floor(world_y)
        biome_id = self.client_world.get_biome(block_x, block_y)
        if not biome_id:
            return

        biome = get_biome_by_id(biome_id)
        color = self._biome_debug_color(biome_id)
        text_lines = [
            f"Biome: {biome.name}",
            f"ID: {biome_id}",
            f"Block at {block_x}, {block_y}: {self.client_world.get_block(block_x, block_y, 0).block_id}",
            # f'{self.client_world.get_block(block_x, block_y, 1).location}'
        ]
        font_size = 18
        font = self.get_font(font_size)
        padding = 8
        line_gap = 2
        text_w = max(font.size(line)[0] for line in text_lines)
        text_h = len(text_lines) * font_size + (len(text_lines) - 1) * line_gap
        width = text_w + padding * 2 + 18
        height = text_h + padding * 2
        x = min(mouse_x + 14, self.SCREEN_WIDTH - width - 4)
        y = min(mouse_y + 14, self.SCREEN_HEIGHT - height - 4)
        rect = pygame.Rect(x, y, width, height)

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((18, 18, 18, 215))
        pygame.draw.rect(panel, (*color, 255), (0, 0, 6, rect.height))
        pygame.draw.rect(panel, (255, 255, 255, 90), panel.get_rect(), 1)
        self.screen.blit(panel, rect.topleft)
        for index, line in enumerate(text_lines):
            text = font.render(line, True, (245, 245, 245))
            self.screen.blit(text, (x + padding + 12, y + padding + index * (font_size + line_gap)))

    def _biome_debug_color(self, biome_id: str) -> tuple[int, int, int]:
        palette = {
            "plains": (105, 181, 75),
            "sunflower_plains": (232, 202, 72),
            "meadow": (142, 202, 97),
            "forest": (47, 130, 59),
            "flower_forest": (238, 91, 166),
            "birch_forest": (126, 184, 82),
            "old_growth_birch_forest": (104, 158, 72),
            "dark_forest": (30, 82, 46),
            "taiga": (58, 126, 99),
            "snowy_taiga": (145, 194, 198),
            "snowy_plains": (220, 236, 245),
            "ice_spikes": (175, 221, 244),
            "grove": (128, 177, 176),
            "river": (55, 121, 220),
            "frozen_river": (142, 205, 240),
            "ocean": (44, 91, 183),
            "deep_ocean": (28, 59, 139),
            "frozen_ocean": (104, 177, 226),
            "deep_frozen_ocean": (77, 145, 203),
            "desert": (226, 196, 100),
            "savanna": (179, 168, 74),
            "jungle": (32, 150, 55),
            "sparse_jungle": (69, 165, 73),
            "bamboo_jungle": (40, 184, 74),
            "swamp": (83, 112, 73),
            "mangrove_swamp": (68, 96, 74),
        }
        if biome_id in palette:
            return palette[biome_id]
        if biome_id in self.biome_debug_colors:
            return self.biome_debug_colors[biome_id]
        h = abs(hash(biome_id))
        color = (
            70 + h % 150,
            70 + (h // 151) % 150,
            70 + (h // 22801) % 150,
        )
        self.biome_debug_colors[biome_id] = color
        return color

    # ===================== 文本与字体 =====================

    def get_font(self, size: int, bold: bool = False) -> pygame.font.Font:
        """获取指定大小的字体（带缓存）。

        参数:
            size: 字体大小（像素）
            bold: 是否使用粗体

        返回:
            pygame.font.Font 实例
        """
        cache_key = (size, True) if bold else size
        if cache_key in self.font_cache:
            return self.font_cache[cache_key]
        font = pygame.font.Font(self.font_path, size)
        font.set_bold(bold)
        self.font_cache[cache_key] = font
        return font

    def render_text(
        self,
        text: str | Text,
        pos: tuple[float, float],
        color: tuple[int, int, int] = (255, 255, 255),
        font_size: int = 36,
        shadow: bool = False,
        shadow_strength = 0.4,
        glow: bool = False,
        clip_rect=None,
        bold: bool = False,
    ) -> None:
        """在屏幕上渲染文本。

        参数:
            text: 文本内容；传入 Text 时会逐段应用颜色和粗体样式
            pos: 位置 (x, y)
            color: 文本颜色 RGB
            font_size: 字体大小
            shadow: 是否绘制阴影
            shadow_strength: 阴影亮度
            glow: 是否添加发光效果
            bold: 普通字符串是否使用粗体；传入 Text 时作为全局粗体开关
        """
        old_clip = None
        if clip_rect is not None:
            old_clip = self.screen.get_clip()
            self.screen.set_clip(clip_rect)

        if isinstance(text, Text):
            segments = text.text
        else:
            segments = ({"text": str(text), "color": color, "bold": bold},)

        cursor_x = pos[0]
        for segment in segments:
            segment_text = str(segment.get("text", ""))
            segment_color = segment.get("color", color)
            if hasattr(segment_color, "value"):
                segment_color = segment_color.value
            if not isinstance(segment_color, (tuple, list)) or len(segment_color) < 3:
                segment_color = color
            segment_color = tuple(segment_color[:3])
            segment_bold = bold or bool(segment.get("bold", False))
            font = self.get_font(font_size, segment_bold)
            text_surface = font.render(segment_text, True, segment_color)

            if shadow:
                # 阴影：深色版本偏移绘制在文本下方
                shadow_color = tuple(int(x * shadow_strength) for x in segment_color)
                shadow_surface = font.render(segment_text, True, shadow_color)
                self.screen.blit(
                    shadow_surface,
                    (cursor_x + font_size / 8, pos[1] + font_size / 8),
                )
            self.screen.blit(text_surface, (cursor_x, pos[1]))
            cursor_x += text_surface.get_width()

        if old_clip is not None:
            self.screen.set_clip(old_clip)
