"""
世界生成器基类模块

定义所有世界生成器的抽象基类 ``Generator``。
"""

from abc import ABC

import resources.server.biome as biome
from resources.server.blocks import *


class Generator(ABC):
    """世界生成器抽象基类。

    所有世界生成器都必须继承此类并实现 ``get_original_block``
    和 ``get_original_biome`` 方法。

    Parameters
    ----------
    seed : int | str
        世界种子，用于确定性生成。传入字符串也会被转为 int。
    """

    def __init__(self, seed):
        self.seed = int(seed)

    def get_original_block(self, x, y, z):
        """获取指定坐标的原始方块。

        Parameters
        ----------
        x : int
            全局 X 坐标（列索引）。
        y : int
            高度（Y 坐标），0 为基岩层，255 为建筑上限。
        z : int
            层索引（0 = 前景墙层，1 = 背景墙层）。

        Returns
        -------
        Block
            该坐标应放置的方块实例。默认返回 AIR()。
        """
        return AIR()

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
            生物群系 ID 字符串。默认返回 ``Void.biome_id``。
        """
        return biome.Void.biome_id
