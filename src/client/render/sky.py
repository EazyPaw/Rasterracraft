# Commented and arranged by ChatGPT
"""
天空渲染 Mixin
==============
提供天空背景、昼夜循环、天体（太阳/月亮）、星星等所有天空相关渲染功能。
作为 Mixin 混入 Render 类使用。
"""

import math as _math
import random as _random
from typing import Any

import numpy as np
import pygame

from .constants import (
    DAY_TICKS,
    DAY_LENGTH_SECONDS,
    MIN_SKY_LIGHT_WEIGHT,
    SKY_CACHE_TICK_STEP,
)
from .render_utils import clamp, cyclic_lerp_color, lerp, lerp_color, smoothstep


class SkyMixin:
    """天空渲染 Mixin，提供完整的昼夜循环渲染能力。

    需要宿主类提供以下属性：
        - SCREEN_WIDTH, SCREEN_HEIGHT: 屏幕尺寸
        - screen: pygame 主 Surface
        - day_time, total_day_ticks: 时间追踪
        - _last_daytime_update: 上次更新时间戳
        - sky_layer, sky_cache_key: 天空缓存
        - celestial_cache: 天体纹理缓存
    """

    # ===================== 天空颜色关键帧 =====================
    # 天空上层颜色：从深夜→日出→白昼→日落→深夜的循环
    SKY_UPPER_KEYFRAMES: list[tuple[float, tuple[int, int, int]]] = [
        (0, (124, 151, 214)),  # 午夜
        (1000, (120, 167, 255)),  # 日出前
        (6000, (120, 167, 255)),  # 正午
        (11000, (112, 151, 224)),  # 午后
        (12000, (73, 88, 136)),  # 日落
        (13000, (44, 42, 66)),  # 黄昏
        (18000, (23, 25, 48)),  # 深夜
        (22000, (45, 45, 78)),  # 黎明前
        (23000, (92, 116, 183)),  # 黎明
    ]

    # 天空下层颜色（地平线附近）：通常比上层更亮
    SKY_LOWER_KEYFRAMES: list[tuple[float, tuple[int, int, int]]] = [
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

    # ===================== 天体相关常量 =====================
    SUN_RISE_TICK: int = -1486
    MOON_RISE_TICK: int = SUN_RISE_TICK + DAY_TICKS // 2

    # 日出日落颜色
    SUNRISE_COLOR: tuple[int, int, int] = (255, 210, 102)
    SUNSET_COLOR: tuple[int, int, int] = (216, 65, 42)

    # 黎明/黄昏时间参数
    DAWN_COLOR_START: int = 22000
    DAWN_COLOR_END: int = 2600
    DAWN_YELLOW_CURVE: float = 2.25
    SUNSET_COLOR_START: int = 10500
    SUNSET_COLOR_RED: int = 13800

    # ---------- 天空主渲染 ----------

    def draw_sky(self) -> None:
        """绘制带动画的昼夜天空。

        每帧检查缓存：若屏幕尺寸或时间区间变化，则重新生成天空图层。
        天空图层包含：上下渐变背景 + 黄昏霞光 + 星星。
        """
        self.update_day_time()
        self.update_weather()
        sky_state = self.get_sky_state()
        self.current_sky_state = sky_state

        # 基于屏幕尺寸和离散化时间的缓存键
        cache_key = (
            self.SCREEN_WIDTH,
            self.SCREEN_HEIGHT,
            int(self.day_time // SKY_CACHE_TICK_STEP),
            int(self.weather_intensity * 4),
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
        self.draw_clouds(sky_state)

    # ---------- 时间更新 ----------

    def update_day_time(self) -> None:
        """更新游戏内时间（day_time 和 total_day_ticks）。

        基于现实时间流逝，按比例换算为游戏刻。
        同时与服务器时间同步（若可用），通过平滑插值避免时间跳跃。
        """
        now = pygame.time.get_ticks()
        elapsed = max(0, now - self._last_daytime_update) / 1000.0
        self._last_daytime_update = now

        # 现实时间 → 游戏刻转换
        tick_delta = elapsed * (DAY_TICKS / DAY_LENGTH_SECONDS)
        self.total_day_ticks += tick_delta
        self.day_time = (self.day_time + tick_delta) % DAY_TICKS

        # 与服务器时间同步
        server_time: float | None = getattr(self.client_world, "world_time", None)
        if server_time is not None:
            diff = (
                (server_time - self.day_time + DAY_TICKS / 2) % DAY_TICKS
            ) - DAY_TICKS / 2
            if abs(diff) > 200:
                # 偏差过大：直接跳转
                self.day_time = float(server_time)
            elif abs(diff) > 2:
                # 微小偏差：平滑逼近
                self.day_time = (self.day_time + diff * 0.15) % DAY_TICKS

    # ---------- 天空状态计算 ----------

    def get_sky_state(self) -> dict[str, Any]:
        """根据当前时间计算完整天空状态。

                包括：天空上下层颜色、黄昏霞光、日光/月光强度、天空光照权重。

        :return: 包含 upper, lower, twilight, twilight_color, daylight, night, sky_light_weight 的字典

        """
        time_value = self.day_time % DAY_TICKS

        # 天空上下层颜色（循环关键帧插值）
        upper = cyclic_lerp_color(self.SKY_UPPER_KEYFRAMES, time_value)
        lower = cyclic_lerp_color(self.SKY_LOWER_KEYFRAMES, time_value)

        weather = self.weather_intensity
        base_light = 0.25 + 0.75 * self.get_sky_light_weight(clear_only=True)
        rainy_upper = tuple(int(channel * base_light) for channel in (96, 101, 110))
        rainy_lower = tuple(int(channel * base_light) for channel in (126, 130, 137))
        upper = lerp_color(upper, rainy_upper, weather)
        lower = lerp_color(lower, rainy_lower, weather)

        # 太阳高度
        sun_lift = self.get_body_lift(time_value, self.SUN_RISE_TICK)

        # 日出霞光（跨午夜，使用两段 smoothstep 拼接）
        dawn_before_midnight = smoothstep(22000, 23500, time_value)
        dawn_after_midnight = 1.0 - smoothstep(0, 2600, time_value)
        sunrise = max(dawn_before_midnight, dawn_after_midnight)

        # 日落霞光（两段 smoothstep 形成峰形）
        sunset = smoothstep(10500, 12200, time_value) * (
            1.0 - smoothstep(13800, 15500, time_value)
        )

        # 霞光总强度
        twilight = clamp(max(sunrise, sunset)) * (1.0 - weather)

        # 霞光颜色（从日出色平滑过渡到日暮色）
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

        sunrise_color = lerp_color(
            self.SUNSET_COLOR, self.SUNRISE_COLOR, smoothstep(0.0, 1.0, dawn_progress)
        )
        sunset_color = lerp_color(
            self.SUNRISE_COLOR,
            self.SUNSET_COLOR,
            smoothstep(self.SUNSET_COLOR_START, self.SUNSET_COLOR_RED, time_value),
        )
        twilight_color = lerp_color(
            sunrise_color, sunset_color, smoothstep(0.0, 1.0, sunset)
        )

        # 日光/月光强度
        daylight = smoothstep(0.0, 0.55, sun_lift)
        night = smoothstep(
            0.02, 0.42, self.get_body_lift(time_value, self.MOON_RISE_TICK)
        ) * (1.0 - weather)

        return {
            "upper": upper,
            "lower": lower,
            "twilight": twilight,
            "twilight_color": twilight_color,
            "daylight": daylight,
            "night": night,
            "sky_light_weight": self.get_sky_light_weight(),
        }

    def get_sky_layer(
        self,
        upper_color: tuple[int, int, int],
        lower_color: tuple[int, int, int],
        twilight: float,
        twilight_color: tuple[int, int, int],
        night: float,
    ) -> pygame.Surface:
        """生成天空背景图层。

                依次绘制：
                1. 垂直渐变背景（上层→下层）
                2. 黄昏霞光叠加层
                3. 星星

        :param upper_color: 天空顶部颜色
        :param lower_color: 天空底部（地平线）颜色
        :param twilight: 霞光强度 [0, 1]
        :param twilight_color: 霞光颜色
        :param night: 夜间强度 [0, 1]

        :return: 生成的天空背景 Surface

        """
        sky_layer = pygame.Surface(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        height = self.SCREEN_HEIGHT
        width = self.SCREEN_WIDTH

        # 逐行绘制垂直渐变（从顶部颜色过渡到底部颜色）
        for y in range(height):
            progress = clamp(y / max(height - 1, 1))
            color = lerp_color(upper_color, lower_color, smoothstep(0.0, 1.0, progress))
            pygame.draw.line(sky_layer, color, (0, y), (width - 1, y))

        # 霞光叠加（水平渐变带，在地平线附近最亮）
        if twilight > 0:
            twilight_layer = pygame.Surface((width, height), pygame.SRCALPHA)
            for y in range(height):
                progress = y / max(height - 1, 1)
                alpha = int(190 * twilight * smoothstep(0.36, 0.62, progress))
                pygame.draw.line(
                    twilight_layer, (*twilight_color, alpha), (0, y), (width - 1, y)
                )
            sky_layer.blit(twilight_layer, (0, 0))

        # 星星（仅在夜间足够暗时可见）
        if night > 0.08:
            self.draw_stars_on_layer(sky_layer, int(145 * smoothstep(0.08, 0.8, night)))

        return sky_layer.convert()

    # ---------- 天体外层调度 ----------

    def draw_celestial_bodies(self, sky_state: dict[str, Any]) -> None:
        """绘制太阳和月亮天体。

                计算太阳和月亮的位置、可见度、前后遮挡关系，
                按正确顺序绘制（被遮挡的天体先画）。

        :param sky_state: 天空状态字典

        """
        sun_pos, sun_lift = self.get_celestial_position(
            self.day_time, self.SUN_RISE_TICK
        )
        moon_pos, moon_lift = self.get_celestial_position(
            self.day_time, self.MOON_RISE_TICK
        )
        body_size = max(72, int(min(self.SCREEN_WIDTH, self.SCREEN_HEIGHT) * 0.32))

        # 构建太阳绘制参数
        sun_body = {
            "kind": "sun",
            "pos": sun_pos,
            "lift": sun_lift,
            "rising": self.is_body_rising(self.day_time, self.SUN_RISE_TICK),
            "visibility": self.get_body_visibility(sun_lift)
            * (1.0 - self.weather_intensity),
            "texture": self.sun_texture,
            "tint": self.get_sun_color(sun_lift),
        }
        # 构建月亮绘制参数
        moon_body = {
            "kind": "moon",
            "pos": moon_pos,
            "lift": moon_lift,
            "rising": self.is_body_rising(self.day_time, self.MOON_RISE_TICK),
            "visibility": self.get_body_visibility(moon_lift)
            * 0.78
            * (1.0 - self.weather_intensity),
            "texture": self.moon_phase_textures[self.get_moon_phase()],
            "tint": None,
        }

        # 确定前后绘制顺序（距离近的天体在前）
        front_body, back_body = self.get_front_back_body(sun_body, moon_body)
        # 处理日月重合时的遮挡
        overlap = self.get_body_overlap(sun_pos, moon_pos, body_size)
        back_body["visibility"] *= 1.0 - overlap

        self.draw_celestial_body(back_body, body_size)
        self.draw_celestial_body(front_body, body_size)

    def draw_celestial_body(self, body: dict[str, Any], body_size: int) -> None:
        """绘制单个天体（太阳或月亮）。

        :param body: 天体参数字典（kind, pos, visibility, texture, tint）
        :param body_size: 天体渲染尺寸（像素）

        """
        if body["visibility"] <= 0.01:
            return
        texture = self.get_celestial_surface(body, body_size)
        self.screen.blit(
            texture,
            texture.get_rect(center=body["pos"]),
            special_flags=pygame.BLEND_RGB_ADD,
        )

    def get_celestial_surface(
        self, body: dict[str, Any], body_size: int
    ) -> pygame.Surface:
        """获取或生成带缓存的单个天体 Surface。

                缓存策略：基于天体类型、纹理 ID、尺寸、色调、可见度构建缓存键。

        :param body: 天体参数字典
        :param body_size: 渲染尺寸

        :return: 缩放并着色后的天体 Surface

        """
        visibility = round(clamp(body["visibility"]) * 32) / 32
        tint = body["tint"]
        tint_key = (
            None if tint is None else tuple((channel // 8) * 8 for channel in tint)
        )
        key = (body["kind"], id(body["texture"]), body_size, tint_key, visibility)

        cache = self.celestial_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]

        # 缩放纹理
        texture = pygame.transform.scale(body["texture"], (body_size, body_size))
        # 色调调整
        if tint_key is not None:
            texture = self.tint_surface(texture, tint_key)
        # 线性减淡混合（使天体发光）
        texture = self.to_linear_dodge_surface(texture, visibility)

        cache[key] = texture
        if len(cache) > self.MAX_CELESTIAL_CACHE:
            cache.popitem(last=False)
        return texture

    # ---------- 天体位置与可见度 ----------

    def get_front_back_body(
        self, sun_body: dict[str, Any], moon_body: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """确定日月的前后绘制顺序。

                规则：正在升起的天体在前；若都在升起或都在下落，则更亮者在前。

        :return: (前景天体, 背景天体)

        """
        if sun_body["rising"] != moon_body["rising"]:
            front = sun_body if sun_body["rising"] else moon_body
        else:
            front = (
                sun_body
                if sun_body["visibility"] >= moon_body["visibility"]
                else moon_body
            )
        back = moon_body if front is sun_body else sun_body
        return front, back

    def get_body_overlap(
        self, a: tuple[int, int], b: tuple[int, int], body_size: int
    ) -> float:
        """计算两天体之间的重叠程度。

                    a, b: 两天体的屏幕坐标
        :param body_size: 天体渲染尺寸

        :return: 重叠系数 [0, 1]（1 = 完全重叠，0 = 不重叠）

        """
        distance = _math.dist(a, b)
        return 1.0 - smoothstep(body_size * 0.18, body_size * 0.78, distance)

    def is_body_rising(self, time_value: float, rise_tick: int) -> bool:
        """判断天体当前是否处于上升阶段。

        :param time_value: 当前游戏时间（刻）
        :param rise_tick: 天体升起时间（刻）

        :return: True 表示天体正在上升

        """
        local_time = (time_value - rise_tick) % DAY_TICKS
        return local_time < DAY_TICKS / 4 or local_time > DAY_TICKS * 3 / 4

    def get_body_lift(self, time_value: float, rise_tick: int) -> float:
        """计算天体的相对高度 [-1, 1]。

                使用正弦曲线模拟天体的升起-落下运动：
                - 1.0 = 最高点（天顶）
                - 0.0 = 地平线
                - -1.0 = 最低点（地平线下方最远处）

        :param time_value: 当前游戏时间（刻）
        :param rise_tick: 天体升起时间（刻）

        :return: 天体高度 [-1, 1]

        """
        local_time = (time_value - rise_tick) % DAY_TICKS
        if local_time > DAY_TICKS / 2:
            # 下落阶段（下半周期）
            return -_math.sin(_math.pi * (local_time - DAY_TICKS / 2) / (DAY_TICKS / 2))
        # 上升阶段（上半周期）
        return _math.sin(_math.pi * local_time / (DAY_TICKS / 2))

    def get_celestial_position(
        self, time_value: float, rise_tick: int
    ) -> tuple[tuple[int, int], float]:
        """计算天体在屏幕上的渲染位置。

        :param time_value: 当前游戏时间（刻）
        :param rise_tick: 天体升起时间（刻）

        :return: ((screen_x, screen_y), lift) — 屏幕坐标和高度值

        """
        lift = self.get_body_lift(time_value, rise_tick)
        center_x = self.SCREEN_WIDTH * 0.5
        horizon_y = self.SCREEN_HEIGHT * 0.72  # 地平线 Y
        top_y = self.SCREEN_HEIGHT * 0.14  # 天顶 Y
        below_y = horizon_y + self.SCREEN_HEIGHT * 0.13  # 地平线以下 Y

        if lift >= 0:
            y = lerp(horizon_y, top_y, clamp(lift))
        else:
            y = lerp(horizon_y, below_y, clamp(-lift))

        return (int(center_x), int(y)), lift

    def get_body_visibility(self, lift: float) -> float:
        """根据天体高度计算可见度。

        :param lift: 天体高度 [-1, 1]

        :return: 可见度 [0, 1]

        """
        return clamp((lift + 0.08) / 0.22)

    def get_sun_color(self, lift: float) -> tuple[int, int, int]:
        """根据太阳高度计算太阳颜色（低角度偏暖红色，高角度偏白）。

        :param lift: 太阳高度 [-1, 1]

        :return: 太阳 RGB 颜色

        """
        noon = (255, 255, 245)  # 正午偏白
        warm = (255, 151, 84)  # 低角度暖橙
        return lerp_color(warm, noon, smoothstep(0.08, 0.85, lift))

    def get_moon_phase(self) -> int:
        """计算当前月相（0-7）。

        :return: 月相索引（0 = 满月，按材质表索引对应 8 种月相）

        """
        return int((self.total_day_ticks // DAY_TICKS) % 8)

    # ---------- 纹理加载 ----------

    @staticmethod
    def load_environment_texture(path: str) -> pygame.Surface:
        """加载环境纹理并提取亮度通道为 Alpha。

                处理逻辑：
                - 计算每个像素的亮度值 max(R, G, B)
                - 亮度 ≤ 2 的像素视为完全透明
                - 其他像素：亮度映射为 Alpha，保留原始 RGB

        :param path: 纹理文件路径

        :return: 处理后的带 Alpha 通道的 Surface

        """
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
        """从月相纹理表中加载 8 种月相纹理。

                纹理表为 4×2 布局，包含满月→新月的 8 个阶段。

        :return: 月相纹理列表（8 个 Surface）

        """
        sheet = self.load_environment_texture(
            "assets\\minecraft\\textures\\environment\\moon_phases.png"
        )
        phase_w = sheet.get_width() // 4
        phase_h = sheet.get_height() // 2
        phases = []
        for phase in range(8):
            x = (phase % 4) * phase_w
            y = (phase // 4) * phase_h
            phases.append(sheet.subsurface(pygame.Rect(x, y, phase_w, phase_h)).copy())
        return phases

    # ---------- Surface 辅助处理 ----------

    def tint_surface(
        self, surface: pygame.Surface, color: tuple[int, int, int]
    ) -> pygame.Surface:
        """对 Surface 进行颜色乘法混合（保留原始 Alpha）。

        :param surface: 原始 Surface
        :param color: 乘法混合颜色

        :return: 染色后的新 Surface

        """
        tinted = surface.copy()
        tinted.fill((*color, 255), special_flags=pygame.BLEND_RGBA_MULT)
        return tinted

    def to_linear_dodge_surface(
        self, surface: pygame.Surface, visibility: float
    ) -> pygame.Surface:
        """对 Surface 应用线性减淡（发光）效果。

                使用 numpy 向量化运算提升性能：
                - 提取 RGB 和 Alpha 通道
                - 基于 Alpha 和可见度计算减淡强度
                - 对 RGB 进行亮度提升

        :param surface: 原始 Surface
        :param visibility: 可见度/发光强度

        :return: 减淡处理后的 Surface

        """
        rgb = pygame.surfarray.array3d(surface).astype(np.float32)
        alpha = pygame.surfarray.array_alpha(surface).astype(np.float32) / 255.0
        dodge_strength = np.power(alpha, 0.42) * clamp(visibility)
        rgb *= (dodge_strength * 1.45)[..., None]
        return pygame.surfarray.make_surface(
            np.clip(rgb, 0, 255).astype(np.uint8)
        ).convert()

    # ---------- 光照权重 ----------

    def get_sky_light_weight(self, clear_only: bool = False) -> float:
        """计算当前天空光照权重（用于方块渲染时的环境光计算）。

                白天权重接近 1.0，夜晚降至 MIN_SKY_LIGHT_WEIGHT 以上。

        :return: 天空光照权重 [MIN_SKY_LIGHT_WEIGHT, 1.0]

        """
        sun_lift = self.get_body_lift(self.day_time, self.SUN_RISE_TICK)
        daylight = smoothstep(0.0, 0.7, sun_lift)
        horizon_floor = 0.62 * smoothstep(-0.08, 0.03, sun_lift)
        clear_weight = lerp(MIN_SKY_LIGHT_WEIGHT, 1.0, max(daylight, horizon_floor))
        if clear_only:
            return clear_weight

        rain_cap = lerp(1.0, 12.0 / 15.0, self.weather_intensity)
        return min(clear_weight, rain_cap)

    # ---------- 星星 ----------

    def generate_stars(self) -> list[tuple[int, int, int]]:
        """随机生成星星位置和大小。

                星星分布在上半部分屏幕（天空区域），采用多级大小分布：
                - 3% 为 3px 亮星
                - 12% 为 2px 中星
                - 85% 为 1px 小星

        :return: 星星列表 [(x, y, size), ...]

        """
        stars = []
        width = max(self.SCREEN_WIDTH, 1)
        height = max(int(self.SCREEN_HEIGHT * 0.62), 1)
        for _ in range(120):
            x = _random.randint(0, width - 1)
            y = _random.randint(0, height - 1)
            r = _random.random()
            if r < 0.03:
                size = 3  # 亮星
            elif r < 0.15:
                size = 2  # 中等星
            else:
                size = 1  # 小星
            stars.append((x, y, size))
        return stars

    def draw_stars_on_layer(self, layer: pygame.Surface, alpha: int) -> None:
        """在指定图层上绘制星星。

        :param layer: 目标 Surface
        :param alpha: 星星透明度 [0, 255]

        """
        star_layer = pygame.Surface(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA
        )
        for x, y, size in self.stars:
            pygame.draw.rect(star_layer, (210, 215, 235, alpha), (x, y, size, size))
        layer.blit(star_layer, (0, 0))
