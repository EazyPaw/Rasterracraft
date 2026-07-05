"""
经典超平坦世界生成器模块

生成预设的平坦地形用于调试、测试或超平坦生存模式。
"""

import noise

import resources.server.biome as biome
from resources.server.blocks import *
from resources.server.generator.base import Generator


class ClassicFlat(Generator):
    """经典超平坦世界生成器。

    生成预设的平坦地形：

    - Y=0 → 基岩
    - Y=1-60 → 石头
    - Y=61-69 → 泥土
    - Y=70 → 草方块（地表）
    - Y=71 → 装饰物层（草丛、花，由噪声驱动）
    - Y>71 → 空气

    适用于调试、测试或超平坦生存模式。
    """

    def get_original_biome(self, x, y):
        """超平坦世界固定为平原生物群系。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。

        Returns
        -------
        str
            始终返回 ``biome.PLAIN.biome_id``。
        """
        return biome.PLAIN.biome_id

    def get_original_block(self, x, y, z):
        """获取超平坦世界的原始方块。

        分层结构（从下到上）：
        - 基岩 → 石头 → 泥土 → 草方块 → 装饰物 → 空气

        Y=71 的装饰物使用多层 2D Perlin 噪声判定：
        植被斑块 → 草丛 / 花（虞美人或蒲公英）。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度（Y 坐标）。
        z : int
            层索引。

        Returns
        -------
        Block
            该坐标对应的方块。
        """
        # 泥土层
        if 60 < y < 70:
            return DIRT()
        # 草方块（地表）
        elif y == 70:
            return GRASS_BLOCK()
        # 基岩
        elif y == 0:
            return BEDROCK()
        # 石头层
        elif y <= 60:
            return STONE()
        # 装饰物层
        elif y == 71:
            # 植被斑块判定（低频噪声）
            veg_patch = noise.pnoise2(
                x * 0.02, z * 0.02,
                octaves=2, persistence=0.5, lacunarity=2.0,
                base=self.seed
            )
            if veg_patch > -0.15:
                # 草丛密度噪声
                grass_detail1 = noise.pnoise2(
                    x * 0.25, z * 0.25, base=self.seed + 10
                )
                grass_detail2 = noise.pnoise2(
                    x * 0.4, z * 0.4, base=self.seed + 11
                )
                if (grass_detail1 + grass_detail2) / 2 > -0.3:
                    # 花斑块判定（低频噪声）
                    flower_patch = noise.pnoise2(
                        x * 0.03, z * 0.03,
                        octaves=1,
                        base=self.seed + 100
                    )
                    flower_local = noise.pnoise2(
                        x * 0.15, z * 0.15,
                        base=self.seed + 150
                    )
                    if flower_patch > 0.55 and flower_local > 0.5:
                        # 随机选择虞美人或蒲公英
                        if noise.pnoise2(x * 0.7, z * 0.7,
                                         base=self.seed + 200) > 0:
                            return POPPY()
                        else:
                            return DANDELION()
                    else:
                        return SHORT_GRASS()

            return AIR()

        else:
            return AIR()
