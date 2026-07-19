"""
仿 Minecraft 主世界生成器模块

使用多层 Perlin 噪声实现确定性的地形、生物群系、
洞穴、矿石和地表装饰物生成。
"""

from resources.server.blocks import *
from resources.server.generator.base import Generator
from resources.server.generator.terrain import TerrainMixin
from resources.server.generator.decorations import DecorationMixin


class MinecraftLike2D(TerrainMixin, DecorationMixin, Generator):
    """仿 Minecraft 主世界生成器。

    使用多层 Perlin 噪声实现确定性的地形、生物群系、
    洞穴、矿石和地表装饰物生成。核心流程：

    1. 通过五维噪声参数判定生物群系
    2. 依生物群系配置计算地表高度
    3. 按深度放置地表 / 亚层 / 填充层方块
    4. 在岩石层中分布矿石
    5. 在地表上方生成树木、花草等装饰物

    Parameters
    ----------
    seed : int
        世界种子。
    """

    # ---- 世界常量 ----
    sea_level = 68       # 海平面高度（Y 坐标）
    stone_level = 52     # 石材起始深度（当前未直接使用，保留）
    max_tree_lookup = 14  # 树木查找范围（横向 ±14 格，原 9）
    background_surface_offset = 1

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------

    def __init__(self, seed):
        super().__init__(seed)
        self._biome_cache = {}
        self._surface_height_cache = {}
        self._tree_presence_cache = {}
        self._tree_column_cache = {}
        # 加载树木配置（合并 JSON 自定义和默认值）
        self.tree_configs = self._load_tree_configs()
        # 构建 block_id → Block 子类的工厂映射表
        self.block_factories = self._build_block_factories()

    # ------------------------------------------------------------------
    # 顶层 API：原始方块 & 生物群系获取
    # ------------------------------------------------------------------

    def get_original_biome(self, x, y):
        """获取指定坐标的原始生物群系 ID。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。

        Returns
        -------
        str
            该列对应的生物群系 ID。
        """
        return self.get_profile(self.get_column_biome(x)).biome_id

    def get_original_block(self, x, y, z):
        """获取指定坐标的原始方块（世界生成的主入口）。

        生成逻辑依次为：

        1. y = 0 → 基岩；Y=1..4 按递减概率生成基岩
        2. y ≥ 250 → 空气
        3. 结构方块判定（树木、装饰物、积雪层）
        4. y > 地表高度 → 水（低于海平面且 z==0）或空气
        5. 洞穴空气判定 → 空气（z==0）或地下方块（z==1）
        6. 否则 → 地下方块（依深度放置表层 / 亚层 / 填充层 / 矿石）

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度（Y 坐标）。
        z : int
            层索引（0 = 前景墙，1 = 背景墙）。

        Returns
        -------
        Block
            该坐标对应的方块实例。
        """
        # 边界条件：基岩层以下 & 建筑高度以上
        if y <= 0:
            return BEDROCK()
        if 0 < y < 5 and self._bedrock_at(x, y, z):
            return BEDROCK()
        if y >= 250:
            return AIR()

        # 获取该列的生物群系和地表高度
        column_biome = self.get_column_biome(x)
        profile = self.get_profile(column_biome)
        foreground_surface_y = self.get_surface_height(x)
        surface_y = self.get_layer_surface_height(x, z)

        # 优先检查结构方块（树木、积雪、花草等）
        structure_block = self.get_structure_block(
            x, y, z, surface_y, profile, foreground_surface_y
        )
        if structure_block is not None:
            return structure_block

        if y > surface_y and y <= self.sea_level:
            if profile.freezes_ocean_surface and y == self.sea_level:
                return ICE()
            return WATER()

        # 地表以上：水或空气
        if y > surface_y:
            return AIR()

        # 洞穴空气：前景层挖空，背景层保留岩壁
        if self.is_cave_air(x, y, z, surface_y):
            return AIR() if z == 0 else self.get_underground_block(x, y, surface_y, profile, z)

        # 地表以下：按深度放置方块
        return self.get_underground_block(x, y, surface_y, profile, z)

    def _bedrock_at(self, x: int, y: int, z: int = 0) -> bool:
        """Taper bedrock upward instead of creating a flat layer."""
        chance = max(0.0, 1.0 - (y / 5.0))
        return self._rand01(x, y, 901 + z * 37) < chance
