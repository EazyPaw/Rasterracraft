"""
仅基岩的调试用生成器模块

最简单的世界生成器，用于快速验证核心机制。
"""

from resources.server.blocks import *
from resources.server.generator.base import Generator


class bedrock_flat_generator(Generator):
    """仅基岩的调试世界生成器。

    最简单的世界生成器：Y=0 放置基岩，其余全部为空气。
    用于快速验证方块交互、光照系统等核心机制。

    Parameters
    ----------
    seed : int
        世界种子（实际未使用，仅为接口兼容）。
    """

    def get_original_block(self, x, y, z):
        """Y=0 返回基岩，其余全部为空气。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。
        z : int
            层索引。

        Returns
        -------
        Block
            BEDROCK() 或 AIR()。
        """
        return BEDROCK() if y == 0 else AIR()
