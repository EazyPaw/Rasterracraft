"""
生成器配置数据类模块

定义树木配置 ``TreeConfig`` 和生物群系配置 ``BiomeProfile`` 两个不可变数据类，
以及世界生成数据目录路径常量。
"""

from dataclasses import dataclass
from pathlib import Path

# 世界生成数据目录：存放树木等自定义特征的 JSON 配置文件
WORLDGEN_DIR = Path(__file__).resolve().parents[2] / "data" / "minecraft" / "worldgen"


# ---------------------------------------------------------------------------
# 数据类：树木配置 & 生物群系配置
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TreeConfig:
    """单个树木种类的配置（不可变数据类）。

    Parameters
    ----------
    trunk : str
        树干方块的 block_id，如 ``"oak_log"``。
    leaves : str
        树叶方块的 block_id，如 ``"oak_leaves"``。
    base_height : int
        树干基础高度（不含随机增量）。
    height_rand_a : int
        随机高度增量 A 的最大值。
    height_rand_b : int
        随机高度增量 B 的最大值。
    radius : int
        树冠半径。
    shape : str
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


@dataclass(frozen=True)
class BiomeProfile:
    """单个生物群系的生成参数（不可变数据类）。

    每个生物群系定义了该区域的地形起伏、地表方块构成、
    装饰物密度等属性，由噪声驱动的生物群系判定后用于实际方块放置。

    Parameters
    ----------
    biome_id : str
        生物群系标识名（如 ``"plains"``、``"desert"``）。
    surface : str
        表层方块 block_id（地表最上层）。
    subsurface : str
        亚层方块 block_id（表层下方 1-4 格）。
    filler : str
        填充层方块 block_id（更深处的默认方块）。
    tree : str | None
        该群系的树木种类名，None 表示无树木。
    tree_chance : float
        每棵候选树的生成概率（0~1）。
    grass_chance : float
        每格生成草丛的概率。
    flower_chance : float
        每格生成花的概率。
    fern_chance : float
        每格生成蕨类的概率。
    mushroom_chance : float
        每格生成蘑菇的概率。
    cactus_chance : float
        每格生成仙人掌的概率。
    sugar_cane_chance : float
        每格生成甘蔗的概率。
    elevation_bias : int
        海拔偏移（相对海平面的基础高度加成）。
    amplitude : float
        地形振幅系数（控制丘陵起伏程度）。
    """
    biome_id: str
    surface: str
    subsurface: str
    filler: str
    tree: str | None
    tree_chance: float
    grass_chance: float
    flower_chance: float
    fern_chance: float
    mushroom_chance: float
    cactus_chance: float
    sugar_cane_chance: float
    elevation_bias: int
    amplitude: float
