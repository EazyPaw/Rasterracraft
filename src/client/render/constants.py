# Commented and arranged by ChatGPT
"""
渲染相关常量定义
==================
包含昼夜循环、光照计算、天空颜色等所有渲染相关的常量。
"""

# ===================== 昼夜循环常量 =====================
# 一天的刻数（Minecraft 风格：24000 刻 = 20 分钟）
DAY_TICKS: int = 24000

# 一天的实际时长（秒）
DAY_LENGTH_SECONDS: float = 20 * 60

# 天空缓存刷新间隔（刻），60 刻 ≈ 每 3 秒刷新一次天空颜色
SKY_CACHE_TICK_STEP: int = 60

# ===================== 光照常量 =====================
# 天空光照最小权重，保证夜晚也不会完全黑暗
MIN_SKY_LIGHT_WEIGHT: float = 0.18

# 方块光源色调（暖黄色）
BLOCK_LIGHT_TINT: tuple[int, int, int] = (255, 200, 120)

# 天空色调离散化步长（减少缓存键数量，提高命中率）
BLOCK_TINT_COLOR_STEP: int = 8

# 亮度离散化级别数（0-63 共 64 级）
BLOCK_LIGHT_LEVELS: int = 63

# 天空/方块光源比例离散化级别数（0-15 共 16 级）
BLOCK_RATIO_LEVELS: int = 15

# 分区缓存使用更粗的环境光档位。分区 Surface 远大于单方块纹理，若把连续
# 变化的昼夜权重直接放进缓存键，会在日出/日落期间几乎每帧重建整屏分区。
BLOCK_SECTION_LIGHT_LEVELS: int = 31
BLOCK_SECTION_TINT_COLOR_STEP: int = 16
