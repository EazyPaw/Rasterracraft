# Commented and arranged by ChatGPT
"""Minecraft 风格天气的客户端渲染与音效模块。

本模块定义 WeatherMixin 类，为 Render 主渲染器提供：
  - 雨天/雪天降水粒子渲染（雨滴、雪花下落动画）
  - 多层视差云层渲染（晴天白云 → 阴天乌云渐变）
  - 雨滴溅落粒子特效与立体环境音效

WeatherMixin 需要混入到提供以下属性的类中（如 Render）：
  - client, client_world, camera, screen, block_size
  - SCREEN_WIDTH, SCREEN_HEIGHT, day_time
  - trans_world_location(), get_world_light_tint(), get_tinted_surface()
"""

from __future__ import annotations

import math
import random
from collections import OrderedDict
from typing import TYPE_CHECKING

import pygame

from .render_utils import cyclic_lerp_color, lerp_color, quantize_color

if TYPE_CHECKING:
    from src.client.camera import Camera
    from src.client.client_main import Client
    from src.client.client_world import ClientWorld


class WeatherMixin:
    """天气渲染 Mixin 类。

    为 Render 类提供降水（雨/雪）粒子渲染、多层云渲染和天气音效功能。
    通过 init_weather_rendering() 初始化天气相关资源，
    每帧调用 update_weather() 和 draw_precipitation() 更新并绘制天气效果。

    类常量:
        WEATHER_FADE_SECONDS: 天气强度过渡时间（秒），控制晴雨切换的平滑速度。
    """

    # =========================================================================
    # 类常量
    # =========================================================================

    WEATHER_FADE_SECONDS: float = 1.5
    WEATHER_TINT_COLOR_STEP: int = 16
    MAX_WEATHER_LIT_CACHE: int = 96
    MAX_WEATHER_LIT_CACHE_BYTES: int = 8 * 1024 * 1024
    CLOUD_TINT_COLOR_STEP: int = 16
    MAX_CLOUD_TINT_CACHE: int = 12
    MAX_CLOUD_TINT_CACHE_BYTES: int = 12 * 1024 * 1024

    # =========================================================================
    # 实例属性类型声明
    #
    # 以下属性在 init_weather_rendering() 中完成初始化。
    # 在类体中进行类型注解可以消除 IDE/类型检查器对
    # "实例特性在 __init__ 外部定义" 的警告。
    # =========================================================================

    # 当前天气强度（0.0 = 晴天，1.0 = 完全下雨）
    _weather_intensity: float
    # 上次天气更新时的 pygame 毫秒时间戳
    _weather_last_update: int
    # 天气纹理缓存：键 = (种类, 尺寸, 是否翻转)，值 = 缩放后的纹理 Surface
    _weather_texture_cache: dict[tuple[str, int, bool], pygame.Surface]
    # 天气带光照纹理缓存：键 = (种类, 尺寸, 翻转, 染色, 透明度)，值 = 处理后的 Surface
    _weather_lit_cache: dict[
        tuple[str, int, bool, tuple[int, int, int], int], pygame.Surface
    ]
    # 云层几何 Surface 缓存：键 = (屏幕宽, 屏幕高, 缩放, 层级, 透明度)
    _cloud_surface_cache: dict[tuple, pygame.Surface]
    # 云层颜色缓存：在保留几何缓存的同时支持逐帧平滑染色
    _cloud_tint_cache: dict[tuple, pygame.Surface]
    # 上一帧的相机 Y 坐标，用于累计云层的垂直视差位移
    _cloud_last_camera_y: float | None
    # 相机在垂直方向累计移动的屏幕像素数
    _cloud_vertical_scroll: float
    # 上次生成雨滴溅落粒子的 tick 编号（防止同一 tick 重复生成）
    _last_impact_tick: int
    # 每层（z=0 前景, z=1 后景）上次播放雨声的 tick 编号
    _last_rain_sound_tick: dict[int, int]
    # 上次播放水面溅落音效的 tick 编号
    _last_water_splash_sound_tick: int
    # 天气纹理图集：{"rain": 雨纹理, "snow": 雪纹理}
    _weather_atlases: dict[str, pygame.Surface]

    # =========================================================================
    # 期望父类（Render）提供的属性与方法
    #
    # 在 TYPE_CHECKING 块中声明，仅供类型检查器（mypy / Pyright / PyCharm）
    # 进行静态分析使用，运行时不会执行，避免循环导入。
    # 这可以消除 IDE 中 "未解析的特性引用" 警告。
    # =========================================================================

    if TYPE_CHECKING:
        client: Client
        client_world: ClientWorld
        block_size: int
        SCREEN_WIDTH: int
        SCREEN_HEIGHT: int
        camera: Camera
        screen: pygame.Surface
        day_time: float

        def trans_world_location(self, pos: tuple[float, float]) -> tuple[float, float]:
            """将世界坐标转换为屏幕坐标（由 Render 提供）。"""
            ...

        def get_world_light_tint(
            self, world_x: float, world_y: float
        ) -> tuple[int, int, int]:
            """获取指定世界位置的光照染色颜色（由 Render 提供）。"""
            ...

        def get_tinted_surface(
            self, surface: pygame.Surface, tint: tuple[int, int, int]
        ) -> pygame.Surface:
            """对 Surface 应用颜色染色（由 Render 提供）。"""
            ...

    # =========================================================================
    # 初始化
    # =========================================================================

    def init_weather_rendering(self) -> None:
        """初始化天气渲染子系统。

        加载天气纹理图集（雨/雪），初始化缓存字典和状态变量。
        此方法应在 Render.__init__() 中调用，确保所有天气相关属性
        在使用前完成初始化。
        """
        # 天气强度：0.0（晴天）→ 1.0（完全下雨），带平滑过渡
        self._weather_intensity = 0.0
        # 上次更新时的毫秒时间戳，用于计算 delta time
        self._weather_last_update = pygame.time.get_ticks()
        # 原始天气纹理缓存（缩放 + 翻转）
        self._weather_texture_cache = {}
        # 带光照染色的天气纹理缓存
        self._weather_lit_cache = OrderedDict()
        # 云层 Surface 缓存
        self._cloud_surface_cache = {}
        self._cloud_tint_cache = OrderedDict()
        # 云层视差状态。相机位移使用帧间增量，避免镜头缩放时绝对坐标
        # 乘以新比例造成整条云带瞬移。
        self._cloud_last_camera_x = None
        self._cloud_last_camera_y = None
        self._cloud_last_draw_time = None
        self._cloud_horizontal_phases = {}
        self._cloud_vertical_scroll = 0.0
        # 溅落粒子防重复标记
        self._last_impact_tick = -1
        # 雨声音效节流：{z_layer: last_tick}，防止同一层频繁播放
        self._last_rain_sound_tick = {0: -10_000, 1: -10_000}
        self._last_water_splash_sound_tick = -10_000
        # 加载天气纹理图集
        self._weather_atlases = {
            "rain": pygame.image.load(
                "assets\\minecraft\\textures\\environment\\rain.png"
            ).convert_alpha(),
            "snow": pygame.image.load(
                "assets\\minecraft\\textures\\environment\\snow.png"
            ).convert_alpha(),
        }

    # =========================================================================
    # 天气强度属性
    # =========================================================================

    @property
    def weather_intensity(self) -> float:
        """当前天气强度（只读属性）。

        取值范围 0.0 ~ 1.0：
          - 0.0：晴天
          - 0.5：小雨/小雪
          - 1.0：暴雨/暴雪

        使用 getattr 安全访问，允许在 init_weather_rendering() 调用前
        访问此属性（默认返回 0.0）。
        """
        return float(getattr(self, "_weather_intensity", 0.0))

    # =========================================================================
    # 天气更新
    # =========================================================================

    def update_weather(self) -> None:
        """每帧更新天气强度。

        根据服务端下发的天气状态（client_world.weather）计算目标强度：
          - "rain" → 目标强度 1.0
          - 其他   → 目标强度 0.0（晴天）

        使用 WEATHER_FADE_SECONDS 控制过渡速度，实现平滑的晴雨切换。
        帧间隔限制在 0.25 秒以内，防止卡顿后强度跳变。
        """
        now = pygame.time.get_ticks()
        # 计算帧间隔（秒），上限 0.25 防止跳变
        elapsed = max(0.0, min(0.25, (now - self._weather_last_update) / 1000.0))
        self._weather_last_update = now

        # 根据服务端天气状态确定目标强度
        target = (
            1.0 if getattr(self.client_world, "weather", "clear") == "rain" else 0.0
        )

        # 按过渡时间平滑逼近目标值
        step = elapsed / self.WEATHER_FADE_SECONDS
        if self._weather_intensity < target:
            self._weather_intensity = min(target, self._weather_intensity + step)
        else:
            self._weather_intensity = max(target, self._weather_intensity - step)

    # =========================================================================
    # 降水绘制
    # =========================================================================

    def draw_precipitation(self) -> None:
        """绘制降水粒子（雨/雪）。

        根据当前天气强度、视角范围和世界降水数据，在屏幕可见区域内
        绘制多层雨滴或雪花纹理。核心流程：
          1. 计算屏幕可见的世界 X 范围
          2. 对每个 X 列判断降水类型（雨/雪/无）
          3. 按世界 Y 轴从顶部向下绘制层叠的天气纹理
          4. 每层纹理根据世界位置获取光照染色
          5. 生成雨滴溅落粒子和环境音效

        性能优化：
          - 使用纹理缓存（_weather_texture_cache, _weather_lit_cache）
          - 使用 pygame 裁剪区域 (set_clip) 只绘制可见部分
          - 缓存键按 8 像素步长量化，减少缓存条目数
        """
        intensity = self.weather_intensity
        # 强度太低或缩放为 0 时跳过渲染
        if intensity <= 0.01 or self.block_size <= 0:
            return

        block_size = max(1, int(self.block_size))
        half_width = self.SCREEN_WIDTH / (2.0 * block_size)

        # 计算屏幕可见的世界 X 坐标范围
        x_min = math.floor(self.camera.x - half_width) - 1
        x_max = math.ceil(self.camera.x + half_width) + 1

        # 用于判断降水类型的采样 Y 坐标
        sample_y = max(0, min(self.client_world.y_max - 1, math.floor(self.camera.y)))

        ticks = int(self.client.client_ticks)

        # 屏幕顶部对应的世界 Y 坐标（向上偏移半个 tile 确保覆盖顶部边缘）
        top_world_y = self.camera.y + self.SCREEN_HEIGHT / (2.0 * block_size) - 0.5
        # 每层天气纹理在世界空间中的高度
        tile_height_world = 4.0

        # 保存旧裁剪区域，绘制完成后恢复
        old_clip = self.screen.get_clip()

        for world_x in range(x_min, x_max + 1):
            # 获取当前列在采样高度的降水类型
            precipitation = self.client_world.get_precipitation_type(world_x, sample_y)
            if precipitation == "none":
                continue

            # z=0 是 PyCraft2D 的前景层，z=1 是后景层
            # （仅透过透明前景方块可见）
            precipitation_height = self.client_world.get_precipitation_height(
                world_x, 0
            )
            if precipitation_height is None:
                continue

            # 世界坐标 → 屏幕 X 坐标
            screen_x = int(
                (world_x - self.camera.x - 0.5) * block_size + self.SCREEN_WIDTH / 2
            )
            # 降水屋顶的屏幕 Y 坐标（雨滴到达此高度后停止下落）
            roof_screen_y = int(
                self.trans_world_location((world_x, precipitation_height))[1]
            )
            # 可见区域底部：屋顶之上、屏幕范围之内
            visible_bottom = max(0, min(self.SCREEN_HEIGHT, roof_screen_y))
            if (
                visible_bottom <= 0
                or screen_x >= self.SCREEN_WIDTH
                or screen_x + block_size <= 0
            ):
                continue

            # 交替列翻转纹理，增加视觉多样性
            flipped = (world_x & 1) != 0

            # 裁剪区域：当前列的屏幕矩形 ∩ 屏幕边界
            clip = pygame.Rect(screen_x, 0, block_size, visible_bottom).clip(
                pygame.Rect(0, 0, self.SCREEN_WIDTH, self.SCREEN_HEIGHT)
            )
            if clip.width <= 0 or clip.height <= 0:
                continue
            self.screen.set_clip(clip)

            # UV 滚动锚定在世界 Y 坐标上。
            # 相机垂直移动时，显示的是同一降水场的不同部分，
            # 而不是屏幕空间覆盖层的平移。
            fall_speed = 0.25 if precipitation == "rain" else 0.055
            scroll = (
                self.day_time * fall_speed + abs(world_x * 17) * 0.07
            ) % tile_height_world

            # 世界 Y 向上增长。从 tile 锚点减去滚动量使得纹理在屏幕上
            # 向下移动（而非向上飞），同时保持场域锚定在绝对高度。
            tile_top_world = (
                math.floor((top_world_y + scroll) / tile_height_world)
                * tile_height_world
                - scroll
            )

            # 从屏幕顶部向下逐层绘制天气纹理，直到到达屋顶
            while True:
                tile_y = int(self.trans_world_location((world_x, tile_top_world))[1])
                if tile_y >= visible_bottom:
                    break
                # 获取当前世界位置的光照染色
                light_tint = self.get_world_light_tint(
                    world_x, tile_top_world - tile_height_world * 0.5
                )
                # 获取（或从缓存创建）带光照的天气纹理
                texture = self._get_weather_surface(
                    precipitation,
                    block_size,
                    flipped,
                    light_tint,
                    int((225 if precipitation == "rain" else 205) * intensity),
                )
                self.screen.blit(texture, (screen_x, tile_y))
                tile_top_world -= tile_height_world

        # 恢复原始裁剪区域
        self.screen.set_clip(old_clip)

        # 生成雨滴溅落粒子
        self._spawn_rain_impacts(x_min, x_max, ticks)

    # =========================================================================
    # 天气纹理管理
    # =========================================================================

    def _get_weather_texture(
        self, kind: str, size: int, flipped: bool
    ) -> pygame.Surface:
        """获取缩放并翻转后的天气纹理（带缓存）。

        :param kind: 降水类型（"rain" 或 "snow"）
        :param size: 目标宽度（像素）
        :param flipped: 是否水平翻转

        :return: 处理后的纹理 Surface

        :return: 缓存策略：
            以 (kind, size, flipped) 为键缓存纹理，避免每帧重复缩放。

        """
        key = (kind, size, flipped)
        cached = self._weather_texture_cache.get(key)
        if cached is not None:
            return cached

        # 从图集中按宽高比缩放
        atlas = self._weather_atlases[kind]
        aspect_height = max(1, round(size * atlas.get_height() / atlas.get_width()))
        surface = pygame.transform.scale(atlas, (size, aspect_height)).convert_alpha()
        if flipped:
            surface = pygame.transform.flip(surface, True, False)

        self._weather_texture_cache[key] = surface
        return surface

    def _get_weather_surface(
        self,
        kind: str,
        size: int,
        flipped: bool,
        tint: tuple[int, int, int],
        alpha: int,
    ) -> pygame.Surface:
        """获取带光照染色和透明度处理的天气纹理（带缓存）。

        :param kind: 降水类型（"rain" 或 "snow"）
        :param size: 目标宽度（像素）
        :param flipped: 是否水平翻转
        :param tint: RGB 染色颜色
        :param alpha: 透明度（0-255）

        :return: 处理后的纹理 Surface

        :return: 缓存策略：
            以 (kind, size, flipped, tint, alpha) 为键。
            颜色和透明度按有限档位量化，并同时受条目数和像素字节预算约束。

        """
        # 昼夜与天气强度连续变化；较粗档位能避免每帧制造一套降水纹理。
        tint = quantize_color(tint, self.WEATHER_TINT_COLOR_STEP)
        alpha = max(0, min(255, int(round(alpha / 16) * 16)))

        key = (kind, size, flipped, tint, alpha)
        cached = self._weather_lit_cache.get(key)
        if cached is not None:
            if hasattr(self._weather_lit_cache, "move_to_end"):
                self._weather_lit_cache.move_to_end(key)
            return cached

        # 获取基础纹理 → 染色 → 设置透明度
        base = self._get_weather_texture(kind, size, flipped)
        # 此缓存本身已经按 tint/alpha 管理，直接染色可避免在全局 tint 缓存
        # 中再留一份同尺寸 Surface。
        tinted = base.copy()
        tinted.fill((*tint, 255), special_flags=pygame.BLEND_RGBA_MULT)
        tinted.set_alpha(alpha)

        self._weather_lit_cache[key] = tinted

        total_bytes = sum(
            surface.get_width() * surface.get_height() * surface.get_bytesize()
            for surface in self._weather_lit_cache.values()
        )
        while self._weather_lit_cache and (
            len(self._weather_lit_cache) > self.MAX_WEATHER_LIT_CACHE
            or total_bytes > self.MAX_WEATHER_LIT_CACHE_BYTES
        ):
            if hasattr(self._weather_lit_cache, "popitem"):
                try:
                    _, old = self._weather_lit_cache.popitem(last=False)
                except TypeError:
                    _, old = self._weather_lit_cache.popitem()
            total_bytes -= old.get_width() * old.get_height() * old.get_bytesize()

        return tinted

    # =========================================================================
    # 雨滴溅落效果
    # =========================================================================

    def _spawn_rain_impacts(self, x_min: int, x_max: int, ticks: int) -> None:
        """生成稀疏的雨滴溅落粒子和位置相关的环境音效。

                仅在降雨天气（weather == "rain"）且强度 > 0.05 时生效。
                每 3 ticks 执行一次（降低性能开销）。

                对每个可见世界列和每个渲染层（z=0, z=1）：
                  - 在降水到达高度处生成 "minecraft:splash" 粒子
                  - 选取最近的可闻溅落点播放立体衰减雨声

        :param x_min: 屏幕可见世界 X 范围下限
        :param x_max: 屏幕可见世界 X 范围上限
        :param ticks: 当前客户端 tick 计数

        """
        # 仅在雨天且有一定强度时生效
        if (
            self.weather_intensity <= 0.05
            or getattr(self.client_world, "weather", "clear") != "rain"
        ):
            return
        # 每 3 ticks 执行一次，且同 tick 不重复
        if ticks == self._last_impact_tick or ticks % 3:
            return
        self._last_impact_tick = ticks

        # 获取粒子管理器
        manager = getattr(self.client, "particle_manager", None)
        if manager is None:
            return

        player = getattr(self.client, "client_player", None)

        # 只保留一个最近落点，避免 z=0/1 同时播放造成音量忽大忽小。
        sound_candidate: tuple[float, float, float, int] | None = None
        water_sound_candidate: tuple[float, float, float, int] | None = None

        for world_x in range(x_min, x_max + 1):
            for z in (0, 1):
                surface = self.client_world.get_precipitation_surface(world_x, z)
                if surface is None:
                    continue
                height, is_water = surface
                if height <= 0:
                    continue
                if self.client_world.get_precipitation_type(world_x, height) != "rain":
                    continue

                # 检查溅落点是否在屏幕范围内
                screen_y = self.trans_world_location((world_x, height))[1]
                if (
                    screen_y < -self.block_size
                    or screen_y > self.SCREEN_HEIGHT + self.block_size
                ):
                    continue

                # 生成溅落粒子
                # 粒子以中心点绘制；将中心抬到“半个粒子高度”后，底边才会
                # 贴在水面/方块表面，而不是陷入方块内部。横向位置也在
                # 方块范围内随机取样，避免所有水花排成整齐的中心线。
                splash_height = random.uniform(0.14, 0.24)
                if random.random() > min(0.75, 0.24 + self.weather_intensity * 0.20):
                    continue
                # 从向上的扇形范围内随机选择发射方向和速度。相比独立随机
                # X/Y 分量，这样能保持自然的弹起力度，同时仍会向左右散开。
                launch_angle = math.radians(random.uniform(60.0, 120.0))
                launch_speed = random.uniform(0.075, 0.12)
                splash_motion = (
                    math.cos(launch_angle) * launch_speed,
                    math.sin(launch_angle) * launch_speed,
                )
                spawned = manager.spawn(
                    "minecraft:splash",
                    world_x + random.uniform(0.12, 0.88),
                    height + splash_height * 0.5,
                    z=z,
                    motion=splash_motion,
                    # size_ 是相对于原始贴图的视觉倍率，而不是世界坐标
                    # 的方块占比。水花贴图本身的非透明区域很窄，需保持
                    # 接近原尺寸乘 trans_scale 的绘制大小。
                    size_=random.uniform(0.6, 0.7),
                    lifetime=random.randint(10, 18),
                )
                if spawned is None:
                    continue

                # 计算溅落点到玩家/相机的距离（用于最近点选取）
                distance = math.hypot(
                    (player.x if player is not None else self.camera.x)
                    - (world_x + 0.5),
                    (player.y if player is not None else self.camera.y) - height,
                )
                if sound_candidate is None or distance < sound_candidate[0]:
                    sound_candidate = (distance, world_x + 0.5, height, z)
                if is_water and (
                    water_sound_candidate is None or distance < water_sound_candidate[0]
                ):
                    water_sound_candidate = (distance, world_x + 0.5, height, z)

        # 播放一个最近溅落点对应的环境雨声。
        # 不使用全局循环声道，而是通过 client_world.play_sound
        # 进行距离衰减和立体声平移，营造空间感。
        # 至少间隔 30 ticks，防止频繁播放。
        if sound_candidate is not None:
            _, x, y, z = sound_candidate
            last_sound_tick = max(self._last_rain_sound_tick.values())
            if ticks - last_sound_tick >= 30:
                self._last_rain_sound_tick[0] = ticks
                self._last_rain_sound_tick[1] = ticks
                # 以玩家位置为声源，避免最近落点变化带来的距离衰减抖动；
                # 雨声本身保持低且稳定的环境音量。
                if player is not None:
                    x, y, z = player.x, player.y, getattr(player, "z", 0)
                self.client_world.play_sound(
                    "ambient.weather.rain",
                    x,
                    y,
                    z,
                    volume=min(0.22, self.weather_intensity * 0.22),
                )

    # =========================================================================
    # 云层渲染
    # =========================================================================

    def draw_clouds(self, sky_state: dict) -> None:
        """绘制多层缓存云层，带相机相对视差效果。

                三层云分别以不同的水平/垂直视差因子和速度移动，
                产生深度感。垂直位移使用相机的帧间位移累计，不受世界绝对高度影响。

                晴天云以天空下半部颜色为基础，日出/日落时跟階sky.py的暖色过渡，
                正午略微提亮向白色靠拢，阴天则向灰色过渡。

        :param sky_state: 天空状态字典，包含 "sky_light_weight" 等键

        """
        intensity = max(0.0, min(1.0, self.weather_intensity))
        # 天空亮度权重（日夜过渡），下限 0.25 防止云完全变黑
        daylight = max(0.25, float(sky_state.get("sky_light_weight", 1.0)))

        # 晴天云色以 SKY_LOWER_KEYFRAMES 的循环平滑插值为基础。
        lower_keyframes = getattr(self, "SKY_LOWER_KEYFRAMES", None)
        if lower_keyframes:
            clear_color = cyclic_lerp_color(lower_keyframes, float(self.day_time))
        else:
            # 兼容单独测试 WeatherMixin 的调用者。
            clear_color = tuple(
                int(channel) for channel in sky_state.get("lower", (242, 246, 255))
            )

        # sky.py 的 twilight_color 就是日出/日落的暖色关键帧。
        # 用同一强度染入云色，使云与天空在日出日落时保持一致。
        twilight = max(0.0, min(1.0, float(sky_state.get("twilight", 0.0))))
        twilight_color = tuple(
            int(channel) for channel in sky_state.get("twilight_color", clear_color)
        )
        clear_color = lerp_color(clear_color, twilight_color, twilight)

        # 正午在没有黄昏色的影响时略微向白色提亮，但不让日出日落的暖色被洗掉。
        sunlight = max(0.0, min(1.0, float(sky_state.get("daylight", daylight))))
        noon_whiten = 0.28 * sunlight * (1.0 - twilight)
        clear_color = lerp_color(clear_color, (255, 255, 255), noon_whiten)
        # 雨云仍根据天空光照调整明度。
        rain_color = tuple(int(channel * daylight) for channel in (112, 118, 126))
        # 根据天气强度在两种颜色间插值
        color = lerp_color(clear_color, rain_color, intensity)

        # 窗口只决定基础密度；实际云形像素尺寸与方块尺寸同比例缩放。
        viewport_scale = float(
            max(2, int(min(self.SCREEN_WIDTH, self.SCREEN_HEIGHT) / 240))
        )
        scale = max(0.5, viewport_scale * float(self.block_size) / 64.0)
        # 云条带总长度（屏幕宽度 + 安全边距）
        travel = self.SCREEN_WIDTH + max(1, round(180 * scale))
        cloud_height = max(1, round(64 * scale))
        # 云带 Surface 很大，完整 RGB 会在昼夜变化时每帧生成三张新图。
        color_key = quantize_color(color, self.CLOUD_TINT_COLOR_STEP)

        now = pygame.time.get_ticks() / 1000.0
        last_draw_time = self._cloud_last_draw_time
        frame_time = 0.0 if last_draw_time is None else max(0.0, now - last_draw_time)
        frame_time = min(frame_time, 0.1)
        self._cloud_last_draw_time = now

        # 累计相机位移。跨越超过一屏的差值视为出生/传送，不让背景云
        # 被一次性推出屏幕；缩放本身造成的相机补偿会由 Render 提前同步。
        camera_x = float(self.camera.x)
        camera_y = float(self.camera.y)
        last_camera_x = self._cloud_last_camera_x
        last_camera_y = self._cloud_last_camera_y
        camera_delta_x = 0.0 if last_camera_x is None else camera_x - last_camera_x
        camera_delta_y = 0.0 if last_camera_y is None else camera_y - last_camera_y
        visible_world_width = self.SCREEN_WIDTH / max(float(self.block_size), 1.0)
        visible_world_height = self.SCREEN_HEIGHT / max(float(self.block_size), 1.0)
        if abs(camera_delta_x) > visible_world_width:
            camera_delta_x = 0.0
        if abs(camera_delta_y) > visible_world_height:
            camera_delta_y = 0.0
        self._cloud_vertical_scroll += camera_delta_y * self.block_size
        self._cloud_last_camera_x = camera_x
        self._cloud_last_camera_y = camera_y

        # 三层云的定义：(水平视差, 垂直视差, 移动速度, 透明度, Y位置比例)
        for index, (parallax_x, parallax_y, speed, alpha, y_ratio) in enumerate(
            (
                (0.22, 0.08, 0.30, 62, 0.11),
                (0.52, 0.16, 0.50, 112, 0.17),
                (0.92, 0.28, 0.80, 178, 0.24),
            )
        ):
            # 方块尺寸是几何缓存键的一部分，防止缩放后继续复用旧尺寸云形。
            shape_key = (
                self.SCREEN_WIDTH,
                self.SCREEN_HEIGHT,
                self.block_size,
                round(scale, 4),
                index,
                alpha,
            )
            shape = self._cloud_surface_cache.get(shape_key)
            if shape is None:
                shape = self._build_cloud_surface(
                    travel, scale, (255, 255, 255), alpha, index
                )
                self._cloud_surface_cache[shape_key] = shape

            tint_key = (*shape_key, color_key)
            cloud = self._cloud_tint_cache.get(tint_key)
            if cloud is None:
                # 形状 Surface 是白色且带 alpha 的遮罩，RGBA 乘法染色不改变透明度。
                cloud = shape.copy()
                cloud.fill((*color_key, 255), special_flags=pygame.BLEND_RGBA_MULT)
                self._cloud_tint_cache[tint_key] = cloud
                total_bytes = sum(
                    surface.get_width()
                    * surface.get_height()
                    * surface.get_bytesize()
                    for surface in self._cloud_tint_cache.values()
                )
                while self._cloud_tint_cache and (
                    len(self._cloud_tint_cache) > self.MAX_CLOUD_TINT_CACHE
                    or total_bytes > self.MAX_CLOUD_TINT_CACHE_BYTES
                ):
                    if hasattr(self._cloud_tint_cache, "popitem"):
                        try:
                            _, old = self._cloud_tint_cache.popitem(last=False)
                        except TypeError:
                            _, old = self._cloud_tint_cache.popitem()
                    total_bytes -= (
                        old.get_width() * old.get_height() * old.get_bytesize()
                    )
            elif hasattr(self._cloud_tint_cache, "move_to_end"):
                self._cloud_tint_cache.move_to_end(tint_key)

            # 增量更新相位，而不是用绝对世界坐标乘当前缩放重新计算。
            # travel 改变时保留当前像素相位，因此调焦不会横向跳动。
            offset = self._cloud_horizontal_phases.get(index)
            if offset is None:
                offset = (camera_x * self.block_size * parallax_x) % travel
            offset = (
                offset
                + camera_delta_x * self.block_size * parallax_x
                - frame_time * speed
            ) % travel
            self._cloud_horizontal_phases[index] = offset
            # 相机向上移动时，世界屏幕坐标向下移动；云层同向位移，
            # 但各层按不同比例滚动，从而产生垂直深度感。
            raw_y = (
                self.SCREEN_HEIGHT * y_ratio + self._cloud_vertical_scroll * parallax_y
            )
            # 在整个云面离开屏幕后无缝回到另一侧，避免长距离攀爬时云层永久消失。
            vertical_travel = self.SCREEN_HEIGHT + cloud_height
            y = int((raw_y + cloud_height) % vertical_travel - cloud_height)

            # 双缓冲绘制：两块相同的云条带首尾相接，实现无缝循环滚动
            self.screen.blit(cloud, (-int(offset), y))
            self.screen.blit(cloud, (-int(offset) + travel, y))

    # =========================================================================
    # 云层 Surface 构建
    # =========================================================================

    @staticmethod
    def _build_cloud_surface(
        travel: int,
        scale: float,
        color: tuple[int, int, int],
        alpha: int,
        layer: int,
    ) -> pygame.Surface:
        """构建单层云的 Surface（静态方法）。

                使用确定性的六云布局（与原版天气通道一致）。
                三层分布确保总体云密度不变，仅每层的视差/透明度不同，
                因此云的轮廓保持一致，而非随机的噪声团块。

        :param travel: 云条带总长度（像素）
        :param scale: 缩放因子
        :param color: RGB 颜色
        :param alpha: 透明度（0-255）
        :param layer: 当前层级（0/1/2），决定分配哪些云块到此层

        :return: 带透明通道的云 Surface

        """
        surface = pygame.Surface(
            (max(1, int(travel)), max(1, round(64 * scale))), pygame.SRCALPHA
        )

        # 六块确定性的云布局（相对偏移和大小）
        # 格式：(x偏移, y偏移, 宽度, 高度)，单位为缩放前的格数
        patterns = (
            (0, 0, 38, 8),
            (8, -6, 17, 6),
            (23, -3, 11, 3),
            (0, 0, 28, 7),
            (5, -5, 12, 5),
            (17, -8, 7, 8),
        )

        for index in range(6):
            # 将六块云按 index % 3 分配到三层深度平面，
            # 每层获得两块云（而非简单地将六块云复制三份导致密度翻三倍）
            if index % 3 != layer:
                continue

            # 云块在条带上的基准位置
            base_x = round(index * travel / 5 - 90 * scale)
            base_y = round((0.18 + (index % 3) * 0.16) * 64 * scale)

            # 每块云使用前三或后三个矩形组合形成不规则轮廓
            start = 0 if index % 2 == 0 else 3
            for px, py, pw, ph in patterns[start : start + 3]:
                pygame.draw.rect(
                    surface,
                    (*color, alpha),
                    (
                        round(base_x + px * scale),
                        round(base_y + py * scale),
                        max(1, round(pw * scale)),
                        max(1, round(ph * scale)),
                    ),
                )

        return surface

    # =========================================================================
    # 音效控制
    # =========================================================================

    def stop_weather_audio(self) -> None:
        """停止天气相关音效。

        当前实现为空操作。保留此方法作为未来扩展天气音效控制的入口点
        （例如停止循环雨声通道）。
        """
        return
