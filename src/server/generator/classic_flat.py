# Commented and arranged by ChatGPT
"""可配置的 Minecraft 风格超平坦世界生成器。"""

from bisect import bisect_right

from src.server.blocks import AIR, get_block_by_id
from src.server.generator.base import Generator
from src.server.generator.superflat import SuperflatSettings


class ClassicFlat(Generator):
    """按存档中的层列表从 Y=0 开始生成超平坦地形。"""

    def __init__(self, seed, settings=None):
        super().__init__(seed)
        self.settings = SuperflatSettings.from_dict(settings)
        total = 0
        self._layer_ends: list[int] = []
        for layer in self.settings.layers:
            total += layer.height
            self._layer_ends.append(total)
        self.total_height = total

    def get_original_biome(self, x, y):
        """返回超平坦预设指定的固定生物群系。

        :param x: int
            全局 X 坐标。
        :param y: int
            高度坐标。

        :return:
        :rtype: str
            预设中的生物群系 ID。

        """
        return self.settings.biome_id

    def get_original_block(self, x, y, z):
        """获取超平坦世界的原始方块。

        分层结构来自 ``SuperflatSettings``，层顺序为从下到上。

        :param x: int
            全局 X 坐标。
        :param y: int
            高度（Y 坐标）。
        :param z: int
            层索引。

        :return:
        :rtype: Block
            该坐标对应的方块。

        """
        y = int(y)
        if y < 0 or y >= self.total_height:
            return AIR()
        layer_index = bisect_right(self._layer_ends, y)
        return get_block_by_id(self.settings.layers[layer_index].block_id)

    def get_surface_height(self, x=0) -> int:
        """返回预设中最高的非空气方块高度。"""
        top = -1
        cursor = 0
        for layer in self.settings.layers:
            if layer.block_id != "air":
                top = cursor + layer.height - 1
            cursor += layer.height
        return top

    def get_spawn_height(self, x=0) -> float:
        """让新玩家出生在最上层之上；虚空预设保持旧的 Y=100 回退。"""
        surface = self.get_surface_height(x)
        return float(surface + 1.01) if surface >= 0 else 100.0

    def to_settings_dict(self) -> dict[str, object]:
        return self.settings.to_dict()
