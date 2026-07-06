import logging
import math
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
import pygame

from resources.client.GUI.gui import GUI
from resources.client.camera import Camera

DAY_TICKS = 24000
DAY_LENGTH_SECONDS = 20 * 60
SKY_CACHE_TICK_STEP = 60
MIN_SKY_LIGHT_WEIGHT = 0.22
BLOCK_LIGHT_TINT = (255, 200, 120)
BLOCK_TINT_COLOR_STEP = 8
BLOCK_LIGHT_LEVELS = 63
BLOCK_RATIO_LEVELS = 15


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = clamp(t)
    return (
        int(lerp(a[0], b[0], t)),
        int(lerp(a[1], b[1], t)),
        int(lerp(a[2], b[2], t)),
    )


def quantize_unit(value: float, levels: int) -> tuple[int, float]:
    q = int(round(clamp(value) * levels))
    return q, q / levels


def quantize_color(color: tuple[int, int, int], step: int) -> tuple[int, int, int]:
    return tuple(min(255, max(0, int(round(channel / step) * step))) for channel in color)


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return 1.0 if value >= edge1 else 0.0
    x = clamp((value - edge0) / (edge1 - edge0))
    return x * x * (3.0 - 2.0 * x)


def cyclic_lerp_color(keyframes: list[tuple[float, tuple[int, int, int]]], time_value: float) -> tuple[int, int, int]:
    time_value %= DAY_TICKS
    frames = sorted(keyframes, key=lambda item: item[0])
    for index, (tick, color) in enumerate(frames):
        next_tick, next_color = frames[(index + 1) % len(frames)]
        end_tick = next_tick if next_tick > tick else next_tick + DAY_TICKS
        test_time = time_value if time_value >= tick else time_value + DAY_TICKS
        if tick <= test_time <= end_tick:
            progress = (test_time - tick) / max(end_tick - tick, 1)
            return lerp_color(color, next_color, smoothstep(0.0, 1.0, progress))
    return frames[0][1]

if TYPE_CHECKING:
    from resources.client.client_main import Client
    from resources.server.block_class import Block


# ===================== 保留原有模块级接口 =====================
def get_light_level(light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]], x: int, y: int):
    """
    获取某个世界坐标的亮度。
    """
    rx = x // 16
    chunk_light_map = light_map.get(rx)

    if chunk_light_map is None:
        return 0

    local_x = x % 16
    if y < 0:
        return 0

    if y >= chunk_light_map.shape[1]:
        return 15

    try:
        light = chunk_light_map[local_x, y]
        return light / 15.0
    except IndexError:
        return 0


def get_light_levels_at(light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]], x: int, y: int):
    """
    返回方块四个角落的光照值（左上、右上、左下、右下）。
    采用"边-角-边-中心"四点平均算法。
    """
    center = get_light_level(light_map, x, y)
    tl = (get_light_level(light_map, x - 1, y) +
          get_light_level(light_map, x - 1, y + 1) +
          get_light_level(light_map, x, y + 1) +
          center) / 4.0
    tr = (get_light_level(light_map, x, y + 1) +
          get_light_level(light_map, x + 1, y + 1) +
          get_light_level(light_map, x + 1, y) +
          center) / 4.0
    bl = (get_light_level(light_map, x - 1, y) +
          get_light_level(light_map, x - 1, y - 1) +
          get_light_level(light_map, x, y - 1) +
          center) / 4.0
    br = (get_light_level(light_map, x, y - 1) +
          get_light_level(light_map, x + 1, y - 1) +
          get_light_level(light_map, x + 1, y) +
          center) / 4.0
    return tl, tr, bl, br


def color_tint(image, new_color):
    """使用混合模式对图像进行染色"""
    # 创建一个图像的副本，避免修改原始图像
    tinted_image = image.copy()
    # 第一步：用 BLEND_RGBA_MULT 将RGB通道归零，保留原始Alpha通道
    tinted_image.fill((0, 0, 0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # 第二步：用 BLEND_RGBA_ADD 将新的RGB颜色加上
    # 注意：要忽略alpha通道，所以用 (new_color[0], new_color[1], new_color[2], 0)
    tinted_image.fill((*new_color, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tinted_image


# ===================== 渲染器 =====================
class Render:
    SUN_RISE_TICK = -1486
    MOON_RISE_TICK = SUN_RISE_TICK + DAY_TICKS // 2

    SKY_UPPER_KEYFRAMES = [
        (0, (124, 151, 214)),
        (1000, (120, 167, 255)),
        (6000, (120, 167, 255)),
        (11000, (112, 151, 224)),
        (12000, (73, 88, 136)),
        (13000, (44, 42, 66)),
        (18000, (23, 25, 48)),
        (22000, (45, 45, 78)),
        (23000, (92, 116, 183)),
    ]
    SKY_LOWER_KEYFRAMES = [
        (0, (180, 206, 255)),
        (1000, (192, 216, 255)),
        (6000, (192, 216, 255)),
        (11000, (175, 199, 239)),
        (12000, (93, 104, 148)),
        (13000, (54, 55, 86)),
        (18000, (31, 35, 64)),
        (22000, (53, 58, 96)),
        (23000, (143, 170, 229)),
    ]
    SUNRISE_COLOR = (255, 210, 102)
    SUNSET_COLOR = (216, 65, 42)
    DAWN_COLOR_START = 22000
    DAWN_COLOR_END = 2600
    DAWN_YELLOW_CURVE = 2.25
    SUNSET_COLOR_START = 10500
    SUNSET_COLOR_RED = 13800

    def __init__(self, client: 'Client'):
        self.sky_base = None
        pygame.init()
        pygame.mixer.init()
        self.debug = False
        self.client = client
        self.client_world = client.client_world
        self.SCREEN_WIDTH = 800
        self.SCREEN_HEIGHT = 600
        self.screen = pygame.display.set_mode(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT),
            pygame.RESIZABLE
        )
        pygame.display.set_caption("PyCraft 2D - 0.0.1 SNAPSHOT")
        self.icon = pygame.image.load("icon.png").convert_alpha()
        pygame.display.set_icon(self.icon)
        self.block_size = 64
        self.trans_scale = self.block_size / 16
        self.gui_scale = 3.5
        self.running = False
        self.camera = Camera()
        self.mouse_x = 0
        self.mouse_y = 0
        self.choosing_position = (0, 0)
        self.font_path = "assets\\minecraft\\font\\Minecraft_AE.ttf"
        self.default_font = pygame.font.Font("assets\\minecraft\\font\\Minecraft_AE.ttf", 36)
        self.font_cache = {}
        self.events = []
        self.day_time = 0.0
        self.total_day_ticks = 0.0
        self._last_daytime_update = pygame.time.get_ticks()
        self.sky_layer = None
        self.sky_cache_key = None
        self.current_sky_state = None
        self.stars = self.generate_stars()
        self.sun_texture = self.load_environment_texture("assets\\minecraft\\textures\\environment\\sun.png")
        self.moon_phase_textures = self.load_moon_phase_textures()
        self.ig_gui_layer = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)
        self.ig_gui_layer.fill((0, 0, 0, 128))

        # 光照与阴影相关缓存
        self.gradient_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_GRADIENT_CACHE = 256  # 渐变纹理缓存上限
        self.lit_tex_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_LIT_CACHE = 768  # 最终光照纹理缓存上限
        self.corner_color_cache: OrderedDict[tuple, tuple[int, int, int]] = OrderedDict()
        self.MAX_CORNER_COLOR_CACHE = 4096
        self.celestial_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_CELESTIAL_CACHE = 128
        self.ao_multiple = 0.05

        self.drawing_GUIs: list[GUI] = []  # 需要绘制的 GUI

        self.blit = self.screen.blit  # 供外部使用的绘制方法，便于在必要情况下更换渲染器

    def transform_pos(self, pos: tuple[float, float]) -> tuple[float, float]:
        """
        将相对屏幕的坐标转换为绝对坐标，用于handle屏幕大小的改变
        :param pos: 相对坐标 （0~100之间）
        :return: 绝对坐标
        """
        x = pos[0] / 100 * self.SCREEN_WIDTH
        y = pos[1] / 100 * self.SCREEN_HEIGHT
        return x, y

    def trans_world_location(self, pos: tuple[float, float]) -> tuple[float, float]:
        """
        将世界坐标转换为屏幕坐标
        :param pos: 世界坐标 (world_x, world_y)
        :return: 屏幕坐标 (screen_x, screen_y)
        """
        world_x, world_y = pos
        screen_x = (world_x - self.camera.x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
        screen_y = self.SCREEN_HEIGHT - ((world_y - self.camera.y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2)
        return screen_x, screen_y

    # ---------- 主循环 ----------
    def start(self):
        self.running = True
        self.sky_base = (120, 167, 255)
        clock = pygame.time.Clock()

        while self.running:
            self.events = pygame.event.get()
            for event in self.events:
                if event.type == pygame.QUIT:
                    self.running = False
                    self.client.shutdown()
                elif event.type == pygame.VIDEORESIZE:
                    self.SCREEN_WIDTH, self.SCREEN_HEIGHT = event.size
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                    self.sky_cache_key = None
                    self.stars = self.generate_stars()
                    self.celestial_cache.clear()
                    self.ig_gui_layer = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)
                    self.ig_gui_layer.fill((0, 0, 0, 128))
                else:
                    # 把键盘、鼠标等游戏事件转发给 GameManager
                    self.client.game_manager.event_queue.append(event)

            if not self.running or self.client.is_shutting_down:
                break

            try:
                self.draw_sky()
                self.camera.update()
                self.draw_block()
                self.draw_hovered_block_outline()
                self.client.client_player.skeleton.update()
                self.draw_player()
                self.draw_gui()

                fps = clock.get_fps()
                # fps_text = self.default_font.render(f"FPS: {int(fps)}", True, (255, 255, 255))
                # self.screen.blit(fps_text, (10, 10))
                self.render_text(f"FPS: {int(fps)}", (10, 10), (255, 255, 255), 36, True)

                pygame.display.flip()
                clock.tick(250)

            except pygame.error as e:
                logging.debug(f"Pygame error during shutdown: {e}")
                break

    def draw_sky(self):
        """Draw the animated day-night sky."""
        self.update_day_time()
        sky_state = self.get_sky_state()
        self.current_sky_state = sky_state
        cache_key = (
            self.SCREEN_WIDTH,
            self.SCREEN_HEIGHT,
            int(self.day_time // SKY_CACHE_TICK_STEP),
        )
        if cache_key != self.sky_cache_key or self.sky_layer is None:
            self.sky_layer = self.get_sky_layer(
                sky_state["upper"],
                sky_state["lower"],
                sky_state["twilight"],
                sky_state["twilight_color"],
                sky_state["night"],
            )
            self.sky_cache_key = cache_key

        self.screen.blit(self.sky_layer, (0, 0))
        self.draw_celestial_bodies(sky_state)

    def update_day_time(self):
        now = pygame.time.get_ticks()
        elapsed = max(0, now - self._last_daytime_update) / 1000.0
        self._last_daytime_update = now
        tick_delta = elapsed * (DAY_TICKS / DAY_LENGTH_SECONDS)
        self.total_day_ticks += tick_delta
        self.day_time = (self.day_time + tick_delta) % DAY_TICKS
        server_time = getattr(self.client_world, "world_time", None)
        if server_time is not None:
            diff = ((server_time - self.day_time + DAY_TICKS / 2) % DAY_TICKS) - DAY_TICKS / 2
            if abs(diff) > 200:
                self.day_time = float(server_time)
            elif abs(diff) > 2:
                self.day_time = (self.day_time + diff * 0.15) % DAY_TICKS

    def load_environment_texture(self, path: str) -> pygame.Surface:
        texture = pygame.image.load(path).convert_alpha()
        result = pygame.Surface(texture.get_size(), pygame.SRCALPHA)
        for x in range(texture.get_width()):
            for y in range(texture.get_height()):
                r, g, b, _ = texture.get_at((x, y))
                brightness = max(r, g, b)
                if brightness <= 2:
                    result.set_at((x, y), (0, 0, 0, 0))
                    continue
                alpha = int(clamp((brightness - 2) / 253) * 255)
                result.set_at((x, y), (r, g, b, alpha))
        return result

    def load_moon_phase_textures(self) -> list[pygame.Surface]:
        sheet = self.load_environment_texture("assets\\minecraft\\textures\\environment\\moon_phases.png")
        phase_w = sheet.get_width() // 4
        phase_h = sheet.get_height() // 2
        phases = []
        for phase in range(8):
            x = (phase % 4) * phase_w
            y = (phase // 4) * phase_h
            phases.append(sheet.subsurface(pygame.Rect(x, y, phase_w, phase_h)).copy())
        return phases

    def get_sky_state(self) -> dict[str, Any]:
        time_value = self.day_time % DAY_TICKS
        upper = cyclic_lerp_color(self.SKY_UPPER_KEYFRAMES, time_value)
        lower = cyclic_lerp_color(self.SKY_LOWER_KEYFRAMES, time_value)

        sun_lift = self.get_body_lift(time_value, self.SUN_RISE_TICK)
        dawn_before_midnight = smoothstep(22000, 23500, time_value)
        dawn_after_midnight = 1.0 - smoothstep(0, 2600, time_value)
        sunrise = max(dawn_before_midnight, dawn_after_midnight)
        sunset = smoothstep(10500, 12200, time_value) * (1.0 - smoothstep(13800, 15500, time_value))
        twilight = clamp(max(sunrise, sunset))
        if time_value >= self.DAWN_COLOR_START:
            dawn_progress = (time_value - self.DAWN_COLOR_START) / (
                DAY_TICKS - self.DAWN_COLOR_START + self.DAWN_COLOR_END
            )
        elif time_value <= self.DAWN_COLOR_END:
            dawn_progress = (time_value + DAY_TICKS - self.DAWN_COLOR_START) / (
                DAY_TICKS - self.DAWN_COLOR_START + self.DAWN_COLOR_END
            )
        else:
            dawn_progress = 1.0
        dawn_progress = 1.0 - (1.0 - clamp(dawn_progress)) ** self.DAWN_YELLOW_CURVE
        sunrise_color = lerp_color(self.SUNSET_COLOR, self.SUNRISE_COLOR, smoothstep(0.0, 1.0, dawn_progress))
        sunset_color = lerp_color(
            self.SUNRISE_COLOR,
            self.SUNSET_COLOR,
            smoothstep(self.SUNSET_COLOR_START, self.SUNSET_COLOR_RED, time_value),
        )
        twilight_color = lerp_color(sunrise_color, sunset_color, smoothstep(0.0, 1.0, sunset))

        daylight = smoothstep(0.0, 0.55, sun_lift)
        night = smoothstep(0.02, 0.42, self.get_body_lift(time_value, self.MOON_RISE_TICK))
        return {
            "upper": upper,
            "lower": lower,
            "twilight": twilight,
            "twilight_color": twilight_color,
            "daylight": daylight,
            "night": night,
            "sky_light_weight": self.get_sky_light_weight(),
        }

    def get_sky_layer(self, upper_color: tuple[int, int, int],
                      lower_color: tuple[int, int, int], twilight: float,
                      twilight_color: tuple[int, int, int], night: float) -> pygame.Surface:
        sky_layer = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)
        height = self.SCREEN_HEIGHT
        width = self.SCREEN_WIDTH

        for y in range(height):
            progress = clamp(y / max(height - 1, 1))
            color = lerp_color(upper_color, lower_color, smoothstep(0.0, 1.0, progress))
            pygame.draw.line(sky_layer, color, (0, y), (width - 1, y))

        if twilight > 0:
            twilight_layer = pygame.Surface((width, height), pygame.SRCALPHA)
            for y in range(height):
                progress = y / max(height - 1, 1)
                alpha = int(190 * twilight * smoothstep(0.36, 0.62, progress))
                pygame.draw.line(twilight_layer, (*twilight_color, alpha), (0, y), (width - 1, y))
            sky_layer.blit(twilight_layer, (0, 0))

        if night > 0.08:
            self.draw_stars_on_layer(sky_layer, int(145 * smoothstep(0.08, 0.8, night)))

        return sky_layer.convert()

    def draw_celestial_bodies(self, sky_state: dict[str, Any]):
        sun_pos, sun_lift = self.get_celestial_position(self.day_time, self.SUN_RISE_TICK)
        moon_pos, moon_lift = self.get_celestial_position(self.day_time, self.MOON_RISE_TICK)
        body_size = max(72, int(min(self.SCREEN_WIDTH, self.SCREEN_HEIGHT) * 0.32))

        sun_body = {
            "kind": "sun",
            "pos": sun_pos,
            "lift": sun_lift,
            "rising": self.is_body_rising(self.day_time, self.SUN_RISE_TICK),
            "visibility": self.get_body_visibility(sun_lift),
            "texture": self.sun_texture,
            "tint": self.get_sun_color(sun_lift),
        }
        moon_body = {
            "kind": "moon",
            "pos": moon_pos,
            "lift": moon_lift,
            "rising": self.is_body_rising(self.day_time, self.MOON_RISE_TICK),
            "visibility": self.get_body_visibility(moon_lift) * 0.78,
            "texture": self.moon_phase_textures[self.get_moon_phase()],
            "tint": None,
        }

        front_body, back_body = self.get_front_back_body(sun_body, moon_body)
        overlap = self.get_body_overlap(sun_pos, moon_pos, body_size)
        back_body["visibility"] *= 1.0 - overlap

        self.draw_celestial_body(back_body, body_size)
        self.draw_celestial_body(front_body, body_size)

    def draw_celestial_body(self, body: dict[str, Any], body_size: int):
        if body["visibility"] <= 0.01:
            return
        texture = self.get_celestial_surface(body, body_size)
        self.screen.blit(texture, texture.get_rect(center=body["pos"]), special_flags=pygame.BLEND_RGB_ADD)

    def get_celestial_surface(self, body: dict[str, Any], body_size: int) -> pygame.Surface:
        visibility = round(clamp(body["visibility"]) * 32) / 32
        tint = body["tint"]
        tint_key = None if tint is None else tuple((channel // 8) * 8 for channel in tint)
        key = (body["kind"], id(body["texture"]), body_size, tint_key, visibility)
        cache = self.celestial_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]

        texture = pygame.transform.scale(body["texture"], (body_size, body_size))
        if tint_key is not None:
            texture = self.tint_surface(texture, tint_key)
        texture = self.to_linear_dodge_surface(texture, visibility)
        cache[key] = texture
        if len(cache) > self.MAX_CELESTIAL_CACHE:
            cache.popitem(last=False)
        return texture

    def get_front_back_body(self, sun_body: dict[str, Any], moon_body: dict[str, Any]):
        if sun_body["rising"] != moon_body["rising"]:
            front = sun_body if sun_body["rising"] else moon_body
        else:
            front = sun_body if sun_body["visibility"] >= moon_body["visibility"] else moon_body
        back = moon_body if front is sun_body else sun_body
        return front, back

    def get_body_overlap(self, a: tuple[int, int], b: tuple[int, int], body_size: int) -> float:
        distance = math.dist(a, b)
        return 1.0 - smoothstep(body_size * 0.18, body_size * 0.78, distance)

    def is_body_rising(self, time_value: float, rise_tick: int) -> bool:
        local_time = (time_value - rise_tick) % DAY_TICKS
        return local_time < DAY_TICKS / 4 or local_time > DAY_TICKS * 3 / 4

    def get_body_lift(self, time_value: float, rise_tick: int) -> float:
        local_time = (time_value - rise_tick) % DAY_TICKS
        if local_time > DAY_TICKS / 2:
            return -math.sin(math.pi * (local_time - DAY_TICKS / 2) / (DAY_TICKS / 2))
        return math.sin(math.pi * local_time / (DAY_TICKS / 2))

    def get_celestial_position(self, time_value: float, rise_tick: int) -> tuple[tuple[int, int], float]:
        lift = self.get_body_lift(time_value, rise_tick)
        center_x = self.SCREEN_WIDTH * 0.5
        horizon_y = self.SCREEN_HEIGHT * 0.72
        top_y = self.SCREEN_HEIGHT * 0.14
        below_y = horizon_y + self.SCREEN_HEIGHT * 0.13
        y = lerp(horizon_y, top_y, clamp(lift)) if lift >= 0 else lerp(horizon_y, below_y, clamp(-lift))
        return (int(center_x), int(y)), lift

    def get_body_visibility(self, lift: float) -> float:
        return clamp((lift + 0.08) / 0.22)

    def get_sun_color(self, lift: float) -> tuple[int, int, int]:
        noon = (255, 255, 245)
        warm = (255, 151, 84)
        return lerp_color(warm, noon, smoothstep(0.08, 0.85, lift))

    def get_moon_phase(self) -> int:
        return int((self.total_day_ticks // DAY_TICKS) % 8)

    def tint_surface(self, surface: pygame.Surface, color: tuple[int, int, int]) -> pygame.Surface:
        tinted = surface.copy()
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        return tinted

    def to_linear_dodge_surface(self, surface: pygame.Surface, visibility: float) -> pygame.Surface:
        rgb = pygame.surfarray.array3d(surface).astype(np.float32)
        alpha = pygame.surfarray.array_alpha(surface).astype(np.float32) / 255.0
        dodge_strength = np.power(alpha, 0.42) * clamp(visibility)
        rgb *= (dodge_strength * 1.45)[..., None]
        return pygame.surfarray.make_surface(np.clip(rgb, 0, 255).astype(np.uint8)).convert()

    def get_sky_light_weight(self) -> float:
        sun_lift = self.get_body_lift(self.day_time, self.SUN_RISE_TICK)
        daylight = smoothstep(0.0, 0.7, sun_lift)
        horizon_floor = 0.62 * smoothstep(-0.08, 0.03, sun_lift)
        return lerp(MIN_SKY_LIGHT_WEIGHT, 1.0, max(daylight, horizon_floor))

    def generate_stars(self) -> list[tuple[int, int, int]]:
        import random
        stars = []
        width = max(self.SCREEN_WIDTH, 1)
        height = max(int(self.SCREEN_HEIGHT * 0.62), 1)
        for _ in range(120):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            # 更多样的大小分布：大部分1px小星，少数2px和极少数3px亮星
            r = random.random()
            if r < 0.03:
                size = 3
            elif r < 0.15:
                size = 2
            else:
                size = 1
            stars.append((x, y, size))
        return stars

    def draw_stars_on_layer(self, layer: pygame.Surface, alpha: int):
        star_layer = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)
        for x, y, size in self.stars:
            pygame.draw.rect(star_layer, (210, 215, 235, alpha), (x, y, size, size))
        layer.blit(star_layer, (0, 0))

    def render_text(self, text: str, pos: tuple[float, float], color: tuple[int, int, int] = (255, 255, 255)
                    , font_size: int = 36, shadow: bool = False, glow: bool = False):
        text_surface = self.get_font(font_size).render(text, True, color)
        if shadow:
            shadow_text = self.get_font(font_size).render(text, True, tuple(int(x * 0.4) for x in color))
            self.screen.blit(shadow_text, (pos[0] + font_size / 8, pos[1] + font_size / 8))
        self.screen.blit(text_surface, pos)

    def _compute_corner_color(self, brightness: float, sky_ratio: float,
                               sky_color: tuple[int, int, int]) -> tuple[int, int, int]:
        """根据亮度和光源比例计算角落光照颜色。
        brightness=0 → (0,0,0), brightness=1 → (255,255,255)
        中间亮度时混入天空/方块光源的色调。"""
        b_key, b = quantize_unit(brightness, BLOCK_LIGHT_LEVELS)
        r_key, sky_ratio = quantize_unit(sky_ratio, BLOCK_RATIO_LEVELS)
        key = (b_key, r_key, sky_color)
        cache = self.corner_color_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]

        base = int(b * 255)
        # 色调强度：亮度 0 和 1 时为 0，亮度 0.5 时最大
        tint_amount = b * (1.0 - b) * 4.0
        if tint_amount < 0.005:
            result = (base, base, base)
            cache[key] = result
            if len(cache) > self.MAX_CORNER_COLOR_CACHE:
                cache.popitem(last=False)
            return result
        tint = lerp_color(BLOCK_LIGHT_TINT, sky_color, sky_ratio)
        # 保持亮度不变，只改变色相
        tint_lum = tint[0] * 0.299 + tint[1] * 0.587 + tint[2] * 0.114
        if tint_lum > 0:
            scale = base / tint_lum
            scaled = (min(255, int(tint[0] * scale)),
                      min(255, int(tint[1] * scale)),
                      min(255, int(tint[2] * scale)))
        else:
            scaled = (base, base, base)
        result = lerp_color((base, base, base), scaled, tint_amount)
        cache[key] = result
        if len(cache) > self.MAX_CORNER_COLOR_CACHE:
            cache.popitem(last=False)
        return result

    def draw_block(self):
        """绘制所有可见方块，应用光照+AO，使用批量预取与缓存策略"""
        # ---- 局部变量绑定，消除属性查找开销 ----
        screen = self.screen
        block_size = self.block_size
        cam_x = self.camera.x
        cam_y = self.camera.y
        cw = self.client_world
        light_map = cw.light_map
        sky_light_map = getattr(cw, "sky_light_map", {})
        block_light_map = getattr(cw, "block_light_map", {})
        NIGHT_TINT = (36, 48, 128)
        sky_state = self.current_sky_state or self.get_sky_state()
        sky_light_weight = sky_state["sky_light_weight"]
        sky_color = lerp_color(
            cyclic_lerp_color(self.SKY_LOWER_KEYFRAMES, self.day_time),
            sky_state["twilight_color"],
            sky_state["twilight"],
        )
        sky_color = lerp_color(sky_color, NIGHT_TINT, sky_state["night"] * 0.85)
        sky_color = quantize_color(sky_color, BLOCK_TINT_COLOR_STEP)
        get_block = cw.get_block
        width = self.SCREEN_WIDTH
        height = self.SCREEN_HEIGHT
        ao_mul = self.ao_multiple
        debug = self.debug
        font = self.default_font

        # ---- 可见范围 ----
        x_blocks = math.ceil(width / block_size)
        y_blocks = math.ceil(height / block_size)
        x_start = int(cam_x - x_blocks // 2 - 1)
        x_end = int(cam_x + x_blocks // 2 + 2)
        y_start = int(cam_y - y_blocks // 2 - 1)
        y_end = int(cam_y + y_blocks // 2 + 2)

        # 扩展一圈用于 AO / 光照邻域
        x_min = x_start - 1
        x_max = x_end + 1
        y_min = y_start - 1
        y_max = y_end + 1

        x_len = x_max - x_min + 1
        y_len = y_max - y_min + 1

        # ---- 预取区块信息 ----
        # block_info:   bit0 = z0固体, bit1 = z1固体
        # blocks0/1:    方块对象
        # light_levels: 归一化总光照 0.0-1.0
        # sky_levels:   归一化天空光照贡献 0.0-1.0
        # block_light_levels: 归一化方块光照贡献 0.0-1.0
        block_info = [[0] * y_len for _ in range(x_len)]
        blocks0: list[list[Optional['Block']]] = [[None] * y_len for _ in range(x_len)]
        blocks1: list[list[Optional['Block']]] = [[None] * y_len for _ in range(x_len)]
        light_levels = [[0.0] * y_len for _ in range(x_len)]
        sky_levels = [[0.0] * y_len for _ in range(x_len)]
        block_light_levels = [[0.0] * y_len for _ in range(x_len)]

        for i in range(x_len):
            x = x_min + i
            chunk_light = light_map.get(x // 16)  # 一次取区块
            chunk_sky_light = sky_light_map.get(x // 16)
            chunk_block_light = block_light_map.get(x // 16)
            local_x = x % 16
            for j in range(y_len):
                y = y_min + j
                b0 = get_block(x, y, 0)
                b1 = get_block(x, y, 1)
                solid0 = 1 if (b0 and b0.solid) else 0
                solid1 = 1 if (b1 and b1.solid) else 0
                block_info[i][j] = solid0 | (solid1 << 1)
                blocks0[i][j] = b0
                blocks1[i][j] = b1

                # 光照
                if chunk_sky_light is not None and chunk_block_light is not None:
                    if y >= chunk_sky_light.shape[1]:
                        sky_light = 15.0
                        block_light = 0.0
                    elif y >= 0:
                        sky_light = float(chunk_sky_light[local_x, y])
                        block_light = float(chunk_block_light[local_x, y])
                    else:
                        sky_light = 0.0
                        block_light = 0.0
                    sky_levels[i][j] = sky_light / 15.0 * sky_light_weight
                    block_light_levels[i][j] = block_light / 15.0
                    light_levels[i][j] = min(1.0, sky_levels[i][j] + block_light_levels[i][j])
                elif chunk_light is not None and 0 <= y < chunk_light.shape[1]:
                    light_levels[i][j] = chunk_light[local_x, y] * sky_light_weight / 15.0
                    sky_levels[i][j] = light_levels[i][j]
                    block_light_levels[i][j] = 0.0

        # ---- 内联辅助函数 ----
        def is_solid(x, y, z):
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return True  # 边界视为固体
            i = x - x_min
            j = y - y_min
            return (block_info[i][j] & (1 << z)) != 0

        def get_light(x, y):
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return 0.0
            return light_levels[x - x_min][y - y_min]

        def get_sky(x, y):
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return 0.0
            return sky_levels[x - x_min][y - y_min]

        def get_block_l(x, y):
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return 0.0
            return block_light_levels[x - x_min][y - y_min]

        # ---- 绘制循环 ----
        for x in range(x_start, x_end + 1):
            i = x - x_min
            for y in range(y_start, y_end + 1):
                j = y - y_min
                b0 = blocks0[i][j]
                b1 = blocks1[i][j]

                if b1 is not None and b1.block_id != 'air' and not (b0 and b0.has_transparent_pixels):
                    self._draw_block_optimized(
                        screen, block_size, cam_x, cam_y, width, height,
                        x, y, 1, b1,
                        light_levels, block_info, is_solid, get_light,
                        get_sky, get_block_l, sky_color,
                        x_min, y_min, ao_mul, debug, font
                    )

                # ---- z = 0 层 ----
                if b0 is not None and b0.block_id != 'air':
                    self._draw_block_optimized(
                        screen, block_size, cam_x, cam_y, width, height,
                        x, y, 0, b0,
                        light_levels, block_info, is_solid, get_light,
                        get_sky, get_block_l, sky_color,
                        x_min, y_min, ao_mul, debug, font
                    )

    def _draw_block_optimized(self, screen, bs, cam_x, cam_y, sw, sh,
                              x, y, z, block,
                              light_levels, block_info, is_solid, get_light,
                              get_sky, get_block_l, sky_color,
                              x_min, y_min, ao_mul, debug, font):
        """绘制单个方块，所有计算内联，使用两级缓存"""
        # ---- 1. 四角总光照 ----
        center = get_light(x, y)
        tl = (get_light(x - 1, y) + get_light(x - 1, y + 1) + get_light(x, y + 1) + center) * 0.25
        tr = (get_light(x, y + 1) + get_light(x + 1, y + 1) + get_light(x + 1, y) + center) * 0.25
        bl = (get_light(x - 1, y) + get_light(x - 1, y - 1) + get_light(x, y - 1) + center) * 0.25
        br = (get_light(x, y - 1) + get_light(x + 1, y - 1) + get_light(x + 1, y) + center) * 0.25

        # ---- 1b. 四角天空/方块光照分离 ----
        center_sky = get_sky(x, y)
        tl_sky = (get_sky(x - 1, y) + get_sky(x - 1, y + 1) + get_sky(x, y + 1) + center_sky) * 0.25
        tr_sky = (get_sky(x, y + 1) + get_sky(x + 1, y + 1) + get_sky(x + 1, y) + center_sky) * 0.25
        bl_sky = (get_sky(x - 1, y) + get_sky(x - 1, y - 1) + get_sky(x, y - 1) + center_sky) * 0.25
        br_sky = (get_sky(x, y - 1) + get_sky(x + 1, y - 1) + get_sky(x + 1, y) + center_sky) * 0.25

        center_bl = get_block_l(x, y)
        tl_bl = (get_block_l(x - 1, y) + get_block_l(x - 1, y + 1) + get_block_l(x, y + 1) + center_bl) * 0.25
        tr_bl = (get_block_l(x, y + 1) + get_block_l(x + 1, y + 1) + get_block_l(x + 1, y) + center_bl) * 0.25
        bl_bl = (get_block_l(x - 1, y) + get_block_l(x - 1, y - 1) + get_block_l(x, y - 1) + center_bl) * 0.25
        br_bl = (get_block_l(x, y - 1) + get_block_l(x + 1, y - 1) + get_block_l(x + 1, y) + center_bl) * 0.25

        # ---- 1c. 计算各角天空光照占比 ----
        def _sr(sky_v: float, block_v: float) -> float:
            total = sky_v + block_v
            return sky_v / total if total > 0.001 else 0.5

        sr_tl = _sr(tl_sky, tl_bl)
        sr_tr = _sr(tr_sky, tr_bl)
        sr_bl = _sr(bl_sky, bl_bl)
        sr_br = _sr(br_sky, br_bl)

        # ---- 2. AO ----
        if z == 0:
            ao_tl = ao_tr = ao_bl = ao_br = 1.0
        else:
            s_tl = (is_solid(x - 1, y, 1) + is_solid(x, y + 1, 1) + is_solid(x - 1, y + 1, 1) +
                    is_solid(x - 1, y, 0) + is_solid(x, y + 1, 0) + is_solid(x - 1, y + 1, 0))
            ao_tl = max(0.2, 1.0 - s_tl * ao_mul)

            s_tr = (is_solid(x + 1, y, 1) + is_solid(x, y + 1, 1) + is_solid(x + 1, y + 1, 1) +
                    is_solid(x + 1, y, 0) + is_solid(x, y + 1, 0) + is_solid(x + 1, y + 1, 0))
            ao_tr = max(0.2, 1.0 - s_tr * ao_mul)

            s_bl = (is_solid(x - 1, y, 1) + is_solid(x, y - 1, 1) + is_solid(x - 1, y - 1, 1) +
                    is_solid(x - 1, y, 0) + is_solid(x, y - 1, 0) + is_solid(x - 1, y - 1, 0))
            ao_bl = max(0.2, 1.0 - s_bl * ao_mul)

            s_br = (is_solid(x + 1, y, 1) + is_solid(x, y - 1, 1) + is_solid(x + 1, y - 1, 1) +
                    is_solid(x + 1, y, 0) + is_solid(x, y - 1, 0) + is_solid(x + 1, y - 1, 0))
            ao_br = max(0.2, 1.0 - s_br * ao_mul)

        # ---- 3. 最终角亮度 ----
        ftl = tl * ao_tl
        ftr = tr * ao_tr
        fbl = bl * ao_bl
        fbr = br * ao_br

        q_ftl, ftl_q = quantize_unit(ftl, BLOCK_LIGHT_LEVELS)
        q_ftr, ftr_q = quantize_unit(ftr, BLOCK_LIGHT_LEVELS)
        q_fbl, fbl_q = quantize_unit(fbl, BLOCK_LIGHT_LEVELS)
        q_fbr, fbr_q = quantize_unit(fbr, BLOCK_LIGHT_LEVELS)
        q_sr_tl, sr_tl_q = quantize_unit(sr_tl, BLOCK_RATIO_LEVELS)
        q_sr_tr, sr_tr_q = quantize_unit(sr_tr, BLOCK_RATIO_LEVELS)
        q_sr_bl, sr_bl_q = quantize_unit(sr_bl, BLOCK_RATIO_LEVELS)
        q_sr_br, sr_br_q = quantize_unit(sr_br, BLOCK_RATIO_LEVELS)

        # ---- 3b. 计算着色后的角落RGB ----
        color_tl = self._compute_corner_color(ftl_q, sr_tl_q, sky_color)
        color_tr = self._compute_corner_color(ftr_q, sr_tr_q, sky_color)
        color_bl = self._compute_corner_color(fbl_q, sr_bl_q, sky_color)
        color_br = self._compute_corner_color(fbr_q, sr_br_q, sky_color)

        # ---- 4. 屏幕坐标 ----
        # 方块占据世界坐标 [y, y+1]，此处用 y+1（方块顶部）定位，
        # 纹理从顶部向下绘制，保证与 trans_world_location 一致。
        sx = (x - cam_x - 0.5) * bs + sw // 2
        sy = sh - (((y + 1) - cam_y + 0.5) * bs + sh // 2)

        # ---- 5. 全黑快速路径 ----
        if ftl == 0.0 and ftr == 0.0 and fbl == 0.0 and fbr == 0.0 and not block.has_transparent_pixels:
            pygame.draw.rect(screen, (0, 0, 0), (sx, sy, bs, bs))
            # 调试文本
            if debug:
                light_val = int(get_light(x, y) * 15)
                text = font.render(str(light_val), True, (255, 255, 255))
                text_rect = text.get_rect(center=(sx + bs // 2, sy + bs // 2))
                screen.blit(text, text_rect)
            return

        # ---- 6. 获取纹理 ----
        tex = block.get_texture(bs)
        if tex is None:
            return

        tex_h = tex.get_height()

        # ---- 7. 光照纹理缓存 ----
        # 键使用 block_id + 纹理帧标识(id(tex)) + 离散化亮度/色调。
        sky_key = (sky_color[0] // BLOCK_TINT_COLOR_STEP,
                   sky_color[1] // BLOCK_TINT_COLOR_STEP,
                   sky_color[2] // BLOCK_TINT_COLOR_STEP)
        key = (block.block_id, id(tex), q_ftl, q_ftr, q_fbl, q_fbr,
               q_sr_tl, q_sr_tr, q_sr_bl, q_sr_br, sky_key)
        cache = self.lit_tex_cache
        if key in cache:
            lit_tex = cache[key]
            cache.move_to_end(key)
        elif tex_h < bs:
            # ---- 非完整高度方块（如雪层） ----
            # 为纹理实际高度创建独立渐变图，避免与下方方块光照叠加造成视觉断层
            ratio = tex_h / bs
            color_tl_p = lerp_color(color_bl, color_tl, ratio)
            color_tr_p = lerp_color(color_br, color_tr, ratio)
            small = pygame.Surface((2, 2), pygame.SRCALPHA)
            small.fill(color_tl_p, (0, 0, 1, 1))
            small.fill(color_tr_p, (1, 0, 1, 1))
            small.fill(color_bl, (0, 1, 1, 1))
            small.fill(color_br, (1, 1, 1, 1))
            grad = pygame.transform.smoothscale(small, (bs, tex_h)).convert_alpha()

            lit_tex = tex.copy()
            lit_tex.blit(grad, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            cache[key] = lit_tex
            if len(cache) > self.MAX_LIT_CACHE:
                cache.popitem(last=False)
        else:
            # ---- 完整高度方块（走缓存） ----
            # 7a. 获取/生成渐变纹理（带天空色缓存键以兼容日夜变化）
            _q = lambda c: (c[0] >> 3, c[1] >> 3, c[2] >> 3)
            grad_key = (_q(color_tl), _q(color_tr), _q(color_bl), _q(color_br))
            grad_cache = self.gradient_cache
            if grad_key in grad_cache:
                grad = grad_cache[grad_key]
                grad_cache.move_to_end(grad_key)
            else:
                small = pygame.Surface((2, 2), pygame.SRCALPHA)
                small.fill(color_tl, (0, 0, 1, 1))
                small.fill(color_tr, (1, 0, 1, 1))
                small.fill(color_bl, (0, 1, 1, 1))
                small.fill(color_br, (1, 1, 1, 1))
                grad = pygame.transform.smoothscale(small, (bs, bs)).convert_alpha()
                grad_cache[grad_key] = grad
                if len(grad_cache) > self.MAX_GRADIENT_CACHE:
                    grad_cache.popitem(last=False)

            # 7b. 生成最终光照纹理
            lit_tex = tex.copy()
            lit_tex.blit(grad, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            cache[key] = lit_tex
            if len(cache) > self.MAX_LIT_CACHE:
                cache.popitem(last=False)

        # ---- 8. 绘制到屏幕（非满高方块底部对齐） ----
        screen.blit(lit_tex, (sx, sy + bs - tex_h))

        # ---- 9. 调试文本（仅在 debug=True 时） ----
        if debug:
            light_val = int(get_light(x, y) * 15)
            text = font.render(str(light_val), True, (255, 255, 255))
            text_rect = text.get_rect(center=(sx + bs // 2, sy + bs // 2))
            screen.blit(text, text_rect)

    def draw_gui(self):
        for gui in self.drawing_GUIs:
            gui.draw()

    def draw_player(self):
        self.client.client_player.skeleton.draw()
        # pygame.draw.rect(
        #     self.screen, (0, 0, 255),
        #     ((self.SCREEN_WIDTH - 2) / 2, (self.SCREEN_HEIGHT - 2) / 2, 2, 2)
        # )

    def get_hovered_block_position(self):
        self.mouse_x, self.mouse_y = pygame.mouse.get_pos()
        camera_x = self.camera.x
        camera_y = self.camera.y
        world_x = (self.mouse_x - self.SCREEN_WIDTH // 2) / self.block_size + camera_x + 0.5
        world_y = -(self.mouse_y - self.SCREEN_HEIGHT // 2) / self.block_size + camera_y - 0.5
        block_x = math.floor(world_x)
        block_y = math.floor(world_y)
        distance = math.sqrt(
            (self.mouse_x - self.SCREEN_WIDTH / 2) ** 2 +
            (self.mouse_y - self.SCREEN_HEIGHT / 2) ** 2
        ) / self.block_size
        if distance > self.client.client_player.interact_range:
            return None, None
        self.choosing_position = (block_x, block_y)
        return block_x, block_y

    def draw_hovered_block_outline(self):
        block_x, block_y = self.get_hovered_block_position()
        if block_x is None or block_y is None:
            return
        camera_x = self.camera.x
        camera_y = self.camera.y
        screen_x = (block_x - camera_x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
        # 方块占据世界坐标 [block_y, block_y+1]，用 block_y+1 定位顶部，与 _draw_block_optimized 一致
        screen_y = self.SCREEN_HEIGHT - (((block_y + 1) - camera_y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2)
        outline_rect = pygame.Rect(screen_x, screen_y, self.block_size, self.block_size)
        pygame.draw.rect(self.screen, (0, 0, 0), outline_rect, 1)

    def debug_mode(self):
        self.debug = not self.debug

    def get_font(self, size) -> pygame.font.Font:
        if self.font_cache.get(size) is not None:
            return self.font_cache.get(size)
        font = pygame.font.Font(self.font_path, size)
        if self.font_cache.get(size) is None:
            self.font_cache[size] = font
        return font

    def show_gui(self, gui: GUI):
        self.drawing_GUIs.append(gui)
        self.drawing_GUIs.sort(key=lambda gui_: gui_.priority)
        gui.on_open()

    def close_gui(self, gui: GUI):
        self.drawing_GUIs.remove(gui)
        gui.on_close()



