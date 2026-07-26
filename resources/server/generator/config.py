# Commented and arranged by ChatGPT
"""
生成器配置数据类模块

定义树木配置 ``TreeConfig``、兼容导出的生物群系配置 ``BiomeProfile``，
以及世界生成数据目录路径常量。
"""

from dataclasses import dataclass
from pathlib import Path

from resources.server.biome import BiomeProfile

# 世界生成数据目录：存放树木等自定义特征的 JSON 配置文件
WORLDGEN_DIR = Path(__file__).resolve().parents[2] / "data" / "minecraft" / "worldgen"


# ---------------------------------------------------------------------------
# 数据类：树木配置
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TreeConfig:
    """单个树木种类的配置（不可变数据类）。

    :param trunk: str
        树干方块的 block_id，如 ``"oak_log"``。
    :param leaves: str
        树叶方块的 block_id，如 ``"oak_leaves"``。
    :param base_height: int
        树干基础高度（不含随机增量）。
    :param height_rand_a: int
        随机高度增量 A 的最大值。
    :param height_rand_b: int
        随机高度增量 B 的最大值。
    :param radius: int
        树冠半径。
    :param shape: str
        树冠形状标识：
        - ``"blob"`` — 球形 / 椭圆形树冠（橡树、桦树等）
        - ``"spruce"`` — 层叠尖顶形（云杉）
        - ``"flat"`` — 扁平形（金合欢）

    """

    trunk: str
    leaves: str
    base_height: int
    height_rand_a: int
    height_rand_b: int
    radius: int
    shape: str = "blob"
