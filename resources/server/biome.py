"""
生物群系模块 (Biome Module)

定义所有主世界生物群系类，每个类包含温度、降水、天空/雾气/草地/树叶颜色。
所有生物群系硬编码，不再从 JSON 文件侧载。
"""

import logging
from abc import ABC

from resources.server.utils import client_method, hex_to_rgb


class Biome(ABC):
    """生物群系抽象基类。"""
    biome_id = "null"
    name = "null"
    temperature = 0.5
    downfall = 0.5
    grass_color = (0, 0, 0)
    foliage_color = (0, 0, 0)
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")

    def __init__(self):
        cls = type(self)
        if getattr(cls, "grass_color", Biome.grass_color) != Biome.grass_color:
            self.grass_color = cls.grass_color
        else:
            try:
                self.grass_color = self._get_color_from_colormap("colormap.grass")
            except RuntimeError:
                self.grass_color = _default_grass_color(self.temperature, self.downfall)
        if getattr(cls, "foliage_color", Biome.foliage_color) != Biome.foliage_color:
            self.foliage_color = cls.foliage_color
        else:
            try:
                self.foliage_color = self._get_color_from_colormap("colormap.foliage")
            except RuntimeError:
                self.foliage_color = _default_foliage_color(self.temperature, self.downfall)

    @client_method
    def _get_color_from_colormap(self, colormap_name: str, client=None) -> tuple[int, int, int]:
        colormap_surface = client.resources_manager.get_texture_img(colormap_name)
        if colormap_surface is None:
            logging.error(f"Failed to get colormap {colormap_name}")
            return 0, 0, 0
        adj_temperature = max(0.0, min(1.0, self.temperature))
        adj_downfall = max(0.0, min(1.0, self.downfall))
        adj_downfall *= adj_temperature
        x = int((1.0 - adj_temperature) * 255)
        y = int((1.0 - adj_downfall) * 255)
        x = max(0, min(x, colormap_surface.get_width() - 1))
        y = max(0, min(y, colormap_surface.get_height() - 1))
        color = colormap_surface.get_at((x, y))
        return color.r, color.g, color.b


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _default_grass_color(temperature: float, downfall: float) -> tuple[int, int, int]:
    """根据温度和降水计算默认草色。"""
    cold = max(0.0, min(1.0, 1.0 - temperature))
    dry = max(0.0, min(1.0, 1.0 - downfall))
    return (
        int(96 + dry * 44 - cold * 20),
        int(148 + downfall * 58 - cold * 14),
        int(64 + downfall * 34 + cold * 28),
    )


def _default_foliage_color(temperature: float, downfall: float) -> tuple[int, int, int]:
    """根据温度和降水计算默认树叶色。"""
    cold = max(0.0, min(1.0, 1.0 - temperature))
    dry = max(0.0, min(1.0, 1.0 - downfall))
    return (
        int(78 + dry * 30 - cold * 16),
        int(132 + downfall * 54 - cold * 10),
        int(54 + downfall * 28 + cold * 24),
    )


# ---------------------------------------------------------------------------
# 特殊生物群系
# ---------------------------------------------------------------------------

class Void(Biome):
    biome_id = "void"
    name = "void"
    temperature = 0.8
    downfall = 0.4


# ---------------------------------------------------------------------------
# 平原 / 草甸类
# ---------------------------------------------------------------------------

class Plains(Biome):
    biome_id = "plains"
    name = "plains"
    temperature = 0.8
    downfall = 0.4
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.4)
    foliage_color = _default_foliage_color(0.8, 0.4)


class SunflowerPlains(Biome):
    biome_id = "sunflower_plains"
    name = "sunflower plains"
    temperature = 0.8
    downfall = 0.4
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.4)
    foliage_color = _default_foliage_color(0.8, 0.4)


class Meadow(Biome):
    biome_id = "meadow"
    name = "meadow"
    temperature = 0.5
    downfall = 0.8
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.8)
    foliage_color = _default_foliage_color(0.5, 0.8)


# ---------------------------------------------------------------------------
# 森林类
# ---------------------------------------------------------------------------

class Forest(Biome):
    biome_id = "forest"
    name = "forest"
    temperature = 0.7
    downfall = 0.8
    sky_color = hex_to_rgb("#79a6ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.7, 0.8)
    foliage_color = _default_foliage_color(0.7, 0.8)


class FlowerForest(Biome):
    biome_id = "flower_forest"
    name = "flower forest"
    temperature = 0.7
    downfall = 0.8
    sky_color = hex_to_rgb("#79a6ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.7, 0.8)
    foliage_color = _default_foliage_color(0.7, 0.8)


class BirchForest(Biome):
    biome_id = "birch_forest"
    name = "birch forest"
    temperature = 0.6
    downfall = 0.6
    sky_color = hex_to_rgb("#7ba4ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.6)
    foliage_color = _default_foliage_color(0.6, 0.6)


class OldGrowthBirchForest(Biome):
    biome_id = "old_growth_birch_forest"
    name = "old growth birch forest"
    temperature = 0.6
    downfall = 0.6
    sky_color = hex_to_rgb("#7ba4ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.6)
    foliage_color = _default_foliage_color(0.6, 0.6)


class DarkForest(Biome):
    biome_id = "dark_forest"
    name = "dark forest"
    temperature = 0.7
    downfall = 0.8
    sky_color = hex_to_rgb("#79a6ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.7, 0.8)
    foliage_color = _default_foliage_color(0.7, 0.8)


# ---------------------------------------------------------------------------
# 针叶林 / 积雪类
# ---------------------------------------------------------------------------

class Taiga(Biome):
    biome_id = "taiga"
    name = "taiga"
    temperature = 0.25
    downfall = 0.8
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.25, 0.8)
    foliage_color = _default_foliage_color(0.25, 0.8)


class SnowyTaiga(Biome):
    biome_id = "snowy_taiga"
    name = "snowy taiga"
    temperature = -0.5
    downfall = 0.4
    sky_color = hex_to_rgb("#8396ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.5, 0.4)
    foliage_color = _default_foliage_color(-0.5, 0.4)


class OldGrowthPineTaiga(Biome):
    biome_id = "old_growth_pine_taiga"
    name = "old growth pine taiga"
    temperature = 0.25
    downfall = 0.8
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.25, 0.8)
    foliage_color = _default_foliage_color(0.25, 0.8)


class OldGrowthSpruceTaiga(Biome):
    biome_id = "old_growth_spruce_taiga"
    name = "old growth spruce taiga"
    temperature = 0.25
    downfall = 0.8
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.25, 0.8)
    foliage_color = _default_foliage_color(0.25, 0.8)


class SnowyPlains(Biome):
    biome_id = "snowy_plains"
    name = "snowy plains"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)


class IceSpikes(Biome):
    biome_id = "ice_spikes"
    name = "ice spikes"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)


class Grove(Biome):
    biome_id = "grove"
    name = "grove"
    temperature = -0.2
    downfall = 0.8
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.2, 0.8)
    foliage_color = _default_foliage_color(-0.2, 0.8)


# ---------------------------------------------------------------------------
# 山地类
# ---------------------------------------------------------------------------

class WindsweptHills(Biome):
    biome_id = "windswept_hills"
    name = "windswept hills"
    temperature = 0.2
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.2, 0.3)
    foliage_color = _default_foliage_color(0.2, 0.3)


class WindsweptGravellyHills(Biome):
    biome_id = "windswept_gravelly_hills"
    name = "windswept gravelly hills"
    temperature = 0.2
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.2, 0.3)
    foliage_color = _default_foliage_color(0.2, 0.3)


class WindsweptForest(Biome):
    biome_id = "windswept_forest"
    name = "windswept forest"
    temperature = 0.2
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.2, 0.3)
    foliage_color = _default_foliage_color(0.2, 0.3)


class JaggedPeaks(Biome):
    biome_id = "jagged_peaks"
    name = "jagged peaks"
    temperature = -0.7
    downfall = 0.9
    sky_color = hex_to_rgb("#8da3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.7, 0.9)
    foliage_color = _default_foliage_color(-0.7, 0.9)


class FrozenPeaks(Biome):
    biome_id = "frozen_peaks"
    name = "frozen peaks"
    temperature = -0.7
    downfall = 0.9
    sky_color = hex_to_rgb("#8da3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.7, 0.9)
    foliage_color = _default_foliage_color(-0.7, 0.9)


class StonyPeaks(Biome):
    biome_id = "stony_peaks"
    name = "stony peaks"
    temperature = 1.0
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.0, 0.3)
    foliage_color = _default_foliage_color(1.0, 0.3)


class SnowySlopes(Biome):
    biome_id = "snowy_slopes"
    name = "snowy slopes"
    temperature = -0.3
    downfall = 0.9
    sky_color = hex_to_rgb("#829aff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.3, 0.9)
    foliage_color = _default_foliage_color(-0.3, 0.9)


# ---------------------------------------------------------------------------
# 沙漠 / 热带草原类
# ---------------------------------------------------------------------------

class Desert(Biome):
    biome_id = "desert"
    name = "desert"
    temperature = 2.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(2.0, 0.0)
    foliage_color = _default_foliage_color(2.0, 0.0)


class Savanna(Biome):
    biome_id = "savanna"
    name = "savanna"
    temperature = 1.2
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.2, 0.0)
    foliage_color = _default_foliage_color(1.2, 0.0)


class SavannaPlateau(Biome):
    biome_id = "savanna_plateau"
    name = "savanna plateau"
    temperature = 1.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.0, 0.0)
    foliage_color = _default_foliage_color(1.0, 0.0)


class WindsweptSavanna(Biome):
    biome_id = "windswept_savanna"
    name = "windswept savanna"
    temperature = 1.1
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.1, 0.0)
    foliage_color = _default_foliage_color(1.1, 0.0)


class Badlands(Biome):
    biome_id = "badlands"
    name = "badlands"
    temperature = 2.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(2.0, 0.0)
    foliage_color = _default_foliage_color(2.0, 0.0)


class WoodedBadlands(Biome):
    biome_id = "wooded_badlands"
    name = "wooded badlands"
    temperature = 2.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(2.0, 0.0)
    foliage_color = _default_foliage_color(2.0, 0.0)


class ErodedBadlands(Biome):
    biome_id = "eroded_badlands"
    name = "eroded badlands"
    temperature = 2.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(2.0, 0.0)
    foliage_color = _default_foliage_color(2.0, 0.0)


# ---------------------------------------------------------------------------
# 丛林类
# ---------------------------------------------------------------------------

class Jungle(Biome):
    biome_id = "jungle"
    name = "jungle"
    temperature = 0.95
    downfall = 0.9
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.95, 0.9)
    foliage_color = _default_foliage_color(0.95, 0.9)


class SparseJungle(Biome):
    biome_id = "sparse_jungle"
    name = "sparse jungle"
    temperature = 0.95
    downfall = 0.8
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.95, 0.8)
    foliage_color = _default_foliage_color(0.95, 0.8)


class BambooJungle(Biome):
    biome_id = "bamboo_jungle"
    name = "bamboo jungle"
    temperature = 0.95
    downfall = 0.9
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.95, 0.9)
    foliage_color = _default_foliage_color(0.95, 0.9)


# ---------------------------------------------------------------------------
# 沼泽类
# ---------------------------------------------------------------------------

class Swamp(Biome):
    biome_id = "swamp"
    name = "swamp"
    temperature = 0.8
    downfall = 0.9
    sky_color = hex_to_rgb("#7ba4ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.9)
    foliage_color = _default_foliage_color(0.8, 0.9)


class MangroveSwamp(Biome):
    biome_id = "mangrove_swamp"
    name = "mangrove swamp"
    temperature = 0.8
    downfall = 0.9
    sky_color = hex_to_rgb("#7ba4ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.9)
    foliage_color = _default_foliage_color(0.8, 0.9)


# ---------------------------------------------------------------------------
# 海洋类
# ---------------------------------------------------------------------------

class Ocean(Biome):
    biome_id = "ocean"
    name = "ocean"
    temperature = 0.5
    downfall = 0.5
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.5)
    foliage_color = _default_foliage_color(0.5, 0.5)


class DeepOcean(Biome):
    biome_id = "deep_ocean"
    name = "deep ocean"
    temperature = 0.5
    downfall = 0.5
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.5)
    foliage_color = _default_foliage_color(0.5, 0.5)


class WarmOcean(Biome):
    biome_id = "warm_ocean"
    name = "warm ocean"
    temperature = 0.8
    downfall = 0.5
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.5)
    foliage_color = _default_foliage_color(0.8, 0.5)


class LukewarmOcean(Biome):
    biome_id = "lukewarm_ocean"
    name = "lukewarm ocean"
    temperature = 0.6
    downfall = 0.5
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.5)
    foliage_color = _default_foliage_color(0.6, 0.5)


class ColdOcean(Biome):
    biome_id = "cold_ocean"
    name = "cold ocean"
    temperature = 0.3
    downfall = 0.5
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.3, 0.5)
    foliage_color = _default_foliage_color(0.3, 0.5)


class FrozenOcean(Biome):
    biome_id = "frozen_ocean"
    name = "frozen ocean"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)


class DeepColdOcean(Biome):
    biome_id = "deep_cold_ocean"
    name = "deep cold ocean"
    temperature = 0.3
    downfall = 0.5
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.3, 0.5)
    foliage_color = _default_foliage_color(0.3, 0.5)


class DeepFrozenOcean(Biome):
    biome_id = "deep_frozen_ocean"
    name = "deep frozen ocean"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)


class DeepLukewarmOcean(Biome):
    biome_id = "deep_lukewarm_ocean"
    name = "deep lukewarm ocean"
    temperature = 0.6
    downfall = 0.5
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.5)
    foliage_color = _default_foliage_color(0.6, 0.5)


# ---------------------------------------------------------------------------
# 沙滩 / 河流类
# ---------------------------------------------------------------------------

class Beach(Biome):
    biome_id = "beach"
    name = "beach"
    temperature = 0.8
    downfall = 0.4
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.4)
    foliage_color = _default_foliage_color(0.8, 0.4)


class SnowyBeach(Biome):
    biome_id = "snowy_beach"
    name = "snowy beach"
    temperature = 0.05
    downfall = 0.3
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.05, 0.3)
    foliage_color = _default_foliage_color(0.05, 0.3)


class StonyShore(Biome):
    biome_id = "stony_shore"
    name = "stony shore"
    temperature = 0.2
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.2, 0.3)
    foliage_color = _default_foliage_color(0.2, 0.3)


class River(Biome):
    biome_id = "river"
    name = "river"
    temperature = 0.5
    downfall = 0.5
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.5)
    foliage_color = _default_foliage_color(0.5, 0.5)


class FrozenRiver(Biome):
    biome_id = "frozen_river"
    name = "frozen river"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)


# ---------------------------------------------------------------------------
# 洞穴类
# ---------------------------------------------------------------------------

class DripstoneCaves(Biome):
    biome_id = "dripstone_caves"
    name = "dripstone caves"
    temperature = 0.8
    downfall = 0.4
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.4)
    foliage_color = _default_foliage_color(0.8, 0.4)


class LushCaves(Biome):
    biome_id = "lush_caves"
    name = "lush caves"
    temperature = 0.5
    downfall = 0.5
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.5)
    foliage_color = _default_foliage_color(0.5, 0.5)


# ---------------------------------------------------------------------------
# 特殊
# ---------------------------------------------------------------------------

class MushroomFields(Biome):
    biome_id = "mushroom_fields"
    name = "mushroom fields"
    temperature = 0.9
    downfall = 1.0
    sky_color = hex_to_rgb("#77a8ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.9, 1.0)
    foliage_color = _default_foliage_color(0.9, 1.0)


# ---------------------------------------------------------------------------
# 向后兼容别名
# ---------------------------------------------------------------------------

# 旧代码可能使用 PLAIN 大写名称
PLAIN = Plains


# ---------------------------------------------------------------------------
# 生物群系注册表
# ---------------------------------------------------------------------------

_BIOME_REGISTRY: dict[str, type] = None


def _normalize_biome_id(biome_id: str | None) -> str:
    """标准化生物群系 ID，去掉命名空间前缀。"""
    if not biome_id:
        return Void.biome_id
    return biome_id.split(":", 1)[-1]


def _build_biome_id_cache() -> dict[str, type]:
    """遍历 Biome 的所有子类，构建 biome_id → 子类 的映射（仅执行一次）。"""
    cache: dict[str, type] = {}

    def collect(cls):
        for subclass in cls.__subclasses__():
            bid = getattr(subclass, "biome_id", None)
            if bid is not None and bid != "null":
                cache[bid] = subclass
            collect(subclass)

    collect(Biome)
    # 确保 plains 存在
    cache.setdefault("plains", Plains)
    return cache


def get_biome_by_id(biome_id: str) -> Biome:
    """根据 biome_id 获取群系实例（首次调用自动构建缓存）。"""
    global _BIOME_REGISTRY
    if _BIOME_REGISTRY is None:
        _BIOME_REGISTRY = _build_biome_id_cache()

    normalized_id = _normalize_biome_id(biome_id)
    cls = _BIOME_REGISTRY.get(normalized_id)
    if cls is not None:
        return cls()

    logging.warning(f"Unknown biome ID: {biome_id}, using plains.")
    return Plains()
