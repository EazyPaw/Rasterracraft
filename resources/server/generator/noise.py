"""
噪声原语 mixin 模块

提供 1D/2D Perlin 噪声封装和确定性哈希函数，
供地形生成器和装饰物生成器使用。
"""

import noise


class NoiseMixin:
    """噪声原语 mixin。

    提供底层的一维 / 二维 Perlin 噪声调用和确定性哈希函数。
    需要宿主类提供 ``self.seed`` 属性。
    """

    # ------------------------------------------------------------------
    # 噪声原语（底层 Perlin 噪声调用）
    # ------------------------------------------------------------------

    def _noise1(self, x: int, scale: float, octaves: int, salt: int) -> float:
        """一维 Perlin 噪声封装。

        用于只依赖 X 坐标的参数生成（生物群系判定、地表高度、装饰物噪声）。

        Parameters
        ----------
        x : int
            X 坐标。
        scale : float
            噪声缩放因子（值越小 → 地形越平缓）。
        octaves : int
            倍频数（越多层 → 细节越丰富）。
        salt : int
            噪声盐值（改变噪声图案的偏移量）。

        Returns
        -------
        float
            [-1, 1] 范围内的噪声值。
        """
        return noise.pnoise1(
            (x + self.seed * 17) * scale,
            octaves=octaves,
            persistence=0.5,
            lacunarity=2.0,
            repeat=1048576,
            base=self.seed + salt,
        )

    def _noise2(self, x: int, y: int, scale: float, octaves: int, salt: int) -> float:
        """二维 Perlin 噪声封装。

        用于依赖 (X, Y) 坐标的参数生成（矿石分布、洞穴、石头变种）。

        Parameters
        ----------
        x : int
            X 坐标。
        y : int
            Y 坐标。
        scale : float
            噪声缩放因子。
        octaves : int
            倍频数。
        salt : int
            噪声盐值。

        Returns
        -------
        float
            [-1, 1] 范围内的噪声值。
        """
        return noise.pnoise2(
            (x + self.seed * 17) * scale,
            (y - self.seed * 11) * scale,
            octaves=octaves,
            persistence=0.5,
            lacunarity=2.0,
            repeatx=1048576,
            repeaty=1048576,
            base=self.seed + salt,
        )

    def _rand01(self, x: int, y: int, salt: int) -> float:
        """生成 [0, 1) 范围内的确定性伪随机浮点数。

        基于稳定哈希，同样输入总是返回相同值。

        Parameters
        ----------
        x : int
            X 坐标。
        y : int
            Y 坐标。
        salt : int
            哈希盐值。

        Returns
        -------
        float
            [0, 1) 范围内的伪随机数。
        """
        return self._stable_hash(x, y, salt) / 0xFFFFFFFF

    def _stable_hash(self, x: int, y: int = 0, salt: int = 0) -> int:
        """确定性稳定哈希函数。

        使用乘法和异或运算将 (x, y, seed, salt) 映射为 32 位伪随机整数。
        保证跨平台、跨 Python 版本的一致性。

        Parameters
        ----------
        x : int
            X 坐标。
        y : int
            Y 坐标，默认为 0（用于 1D 噪声上下文）。
        salt : int
            哈希盐值，用于区分不同用途的随机序列。

        Returns
        -------
        int
            32 位无符号整数范围内的哈希值。
        """
        value = (x * 374761393 + y * 668265263
                 + (self.seed + salt) * 1442695041) & 0xFFFFFFFF
        value = (value ^ (value >> 13)) * 1274126177 & 0xFFFFFFFF
        return value ^ (value >> 16)
