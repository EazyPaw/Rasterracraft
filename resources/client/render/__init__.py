"""
PyCraft2D 渲染包
================
该包负责游戏的所有 2D 渲染，包括：
  - 天空背景与昼夜循环
  - 方块绘制与光照/AO 计算
  - GUI 管理
  - 文本与字体渲染

模块结构:
  constants.py   - 渲染常量
  math_utils.py  - 数学工具函数
  lighting.py    - 光照工具函数
  sky.py         - 天空渲染 Mixin
  block.py       - 方块渲染 Mixin
  renderer.py    - 主渲染器类

外部使用（向后兼容）：
  from resources.client import render
  renderer = render.Render(client)
"""

# ---- 主渲染器类 ----
from .renderer import Render

# ---- 数学工具函数（模块级导出，向后兼容） ----
from .math_utils import (
    clamp,
    cyclic_lerp_color,
    lerp,
    lerp_color,
    quantize_color,
    quantize_unit,
    smoothstep,
)

# ---- 光照工具函数 ----
from .lighting import (
    color_tint,
    get_light_level,
    get_light_levels_at,
)

# ---- 常量 ----
from .constants import (
    BLOCK_LIGHT_LEVELS,
    BLOCK_LIGHT_TINT,
    BLOCK_RATIO_LEVELS,
    BLOCK_TINT_COLOR_STEP,
    DAY_LENGTH_SECONDS,
    DAY_TICKS,
    MIN_SKY_LIGHT_WEIGHT,
    SKY_CACHE_TICK_STEP,
)

# ---- Mixin 类（供内部使用） ----
from .block import BlockRenderMixin
from .sky import SkyMixin
from .weather import WeatherMixin

__all__ = [
    # 主类
    "Render",
    # Mixin
    "SkyMixin",
    "BlockRenderMixin",
    "WeatherMixin",
    # 数学工具
    "clamp",
    "lerp",
    "lerp_color",
    "quantize_unit",
    "quantize_color",
    "smoothstep",
    "cyclic_lerp_color",
    # 光照工具
    "get_light_level",
    "get_light_levels_at",
    "color_tint",
    # 常量
    "DAY_TICKS",
    "DAY_LENGTH_SECONDS",
    "SKY_CACHE_TICK_STEP",
    "MIN_SKY_LIGHT_WEIGHT",
    "BLOCK_LIGHT_TINT",
    "BLOCK_TINT_COLOR_STEP",
    "BLOCK_LIGHT_LEVELS",
    "BLOCK_RATIO_LEVELS",
]
