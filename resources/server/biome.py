"""
生物群系模块 (Biome Module)

定义所有主世界生物群系类，每个类包含温度、降水、天空/雾气/草地/树叶颜色，
以及该群系对应的世界生成参数。
所有生物群系硬编码，不再从 JSON 文件侧载。
"""

import logging
from abc import ABC
from dataclasses import dataclass

from resources.server.utils import client_method, hex_to_rgb


@dataclass(frozen=True)
class BiomeProfile:
    """单个生物群系的生成参数（不可变数据类）。

    每个生物群系定义了该区域的地形起伏、地表方块构成、
    装饰物密度等属性，由噪声驱动的生物群系判定后用于实际方块放置。
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
    is_cold: bool = False
    is_arid: bool = False
    freezes_ocean_surface: bool = False
    mushroom_boost: float = 1.0
    double_plant_chance: float = 0.0
    double_plant_options: tuple[tuple[float, str, str], ...] = ()
    flower_options: tuple[tuple[float, str], ...] = ()


DEFAULT_DOUBLE_PLANT_OPTIONS = (
    (0.70, "tall_grass", "tall_grass_top"),
    (0.82, "rose_bush", "rose_bush_top"),
    (0.94, "peony", "peony_top"),
    (1.00, "lilac", "lilac_top"),
)

SUNFLOWER_PLAINS_DOUBLE_PLANTS = (
    (0.52, "sunflower", "sunflower_top"),
    (0.68, "tall_grass", "tall_grass_top"),
    (0.82, "peony", "peony_top"),
    (0.92, "lilac", "lilac_top"),
    (1.00, "rose_bush", "rose_bush_top"),
)

FLOWER_FOREST_DOUBLE_PLANTS = (
    (0.24, "rose_bush", "rose_bush_top"),
    (0.48, "peony", "peony_top"),
    (0.72, "lilac", "lilac_top"),
    (0.90, "tall_grass", "tall_grass_top"),
    (1.00, "sunflower", "sunflower_top"),
)

FOREST_DOUBLE_PLANTS = (
    (0.42, "tall_grass", "tall_grass_top"),
    (0.54, "large_fern", "large_fern_top"),
    (0.70, "rose_bush", "rose_bush_top"),
    (0.86, "peony", "peony_top"),
    (1.00, "lilac", "lilac_top"),
)

TAIGA_DOUBLE_PLANTS = (
    (0.48, "large_fern", "large_fern_top"),
    (0.82, "tall_grass", "tall_grass_top"),
    (0.91, "peony", "peony_top"),
    (1.00, "lilac", "lilac_top"),
)

SNOWY_DOUBLE_PLANTS = (
    (0.55, "tall_grass", "tall_grass_top"),
    (0.78, "peony", "peony_top"),
    (1.00, "lilac", "lilac_top"),
)

DEFAULT_FLOWERS = (
    (0.48, "poppy"),
    (1.00, "dandelion"),
)

FLOWER_FIELD_FLOWERS = (
    (0.22, "allium"),
    (0.44, "azure_bluet"),
    (0.66, "oxeye_daisy"),
    (0.83, "poppy"),
    (1.00, "dandelion"),
)

SWAMP_FLOWERS = (
    (1.00, "blue_orchid"),
)


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
    surface = "grass_block"
    subsurface = "dirt"
    filler = "stone"
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 0
    amplitude = 1.0
    is_cold = False
    is_arid = False
    freezes_ocean_surface = False
    mushroom_boost = 1.0
    double_plant_chance = 0.0
    double_plant_options = DEFAULT_DOUBLE_PLANT_OPTIONS
    flower_options = DEFAULT_FLOWERS

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
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.02
    grass_chance = 0.28
    flower_chance = 0.035
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.018
    elevation_bias = 0
    amplitude = 1.0
    double_plant_chance = 0.045


class SunflowerPlains(Biome):
    biome_id = "sunflower_plains"
    name = "sunflower plains"
    temperature = 0.8
    downfall = 0.4
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.4)
    foliage_color = _default_foliage_color(0.8, 0.4)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.02
    grass_chance = 0.32
    flower_chance = 0.08
    fern_chance = 0.0
    mushroom_chance = 0.002
    cactus_chance = 0.0
    sugar_cane_chance = 0.018
    elevation_bias = 0
    amplitude = 1.0
    double_plant_chance = 0.1
    double_plant_options = SUNFLOWER_PLAINS_DOUBLE_PLANTS
    flower_options = FLOWER_FIELD_FLOWERS


class Meadow(Biome):
    biome_id = "meadow"
    name = "meadow"
    temperature = 0.5
    downfall = 0.8
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.8)
    foliage_color = _default_foliage_color(0.5, 0.8)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.01
    grass_chance = 0.3
    flower_chance = 0.08
    fern_chance = 0.0
    mushroom_chance = 0.002
    cactus_chance = 0.0
    sugar_cane_chance = 0.01
    elevation_bias = 3
    amplitude = 1.1
    double_plant_chance = 0.1
    flower_options = FLOWER_FIELD_FLOWERS


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
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.24
    grass_chance = 0.42
    flower_chance = 0.045
    fern_chance = 0.03
    mushroom_chance = 0.018
    cactus_chance = 0.0
    sugar_cane_chance = 0.01
    elevation_bias = 2
    amplitude = 1.05
    double_plant_chance = 0.095
    double_plant_options = FOREST_DOUBLE_PLANTS


class FlowerForest(Biome):
    biome_id = "flower_forest"
    name = "flower forest"
    temperature = 0.7
    downfall = 0.8
    sky_color = hex_to_rgb("#79a6ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.7, 0.8)
    foliage_color = _default_foliage_color(0.7, 0.8)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.21
    grass_chance = 0.44
    flower_chance = 0.32
    fern_chance = 0.02
    mushroom_chance = 0.02
    cactus_chance = 0.0
    sugar_cane_chance = 0.008
    elevation_bias = 2
    amplitude = 1.0
    double_plant_chance = 0.18
    double_plant_options = FLOWER_FOREST_DOUBLE_PLANTS
    flower_options = FLOWER_FIELD_FLOWERS


class BirchForest(Biome):
    biome_id = "birch_forest"
    name = "birch forest"
    temperature = 0.6
    downfall = 0.6
    sky_color = hex_to_rgb("#7ba4ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.6)
    foliage_color = _default_foliage_color(0.6, 0.6)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'birch'
    tree_chance = 0.22
    grass_chance = 0.36
    flower_chance = 0.035
    fern_chance = 0.02
    mushroom_chance = 0.01
    cactus_chance = 0.0
    sugar_cane_chance = 0.01
    elevation_bias = 2
    amplitude = 1.0
    double_plant_chance = 0.095
    double_plant_options = FOREST_DOUBLE_PLANTS


class OldGrowthBirchForest(Biome):
    biome_id = "old_growth_birch_forest"
    name = "old growth birch forest"
    temperature = 0.6
    downfall = 0.6
    sky_color = hex_to_rgb("#7ba4ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.6)
    foliage_color = _default_foliage_color(0.6, 0.6)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'birch'
    tree_chance = 0.27
    grass_chance = 0.34
    flower_chance = 0.03
    fern_chance = 0.03
    mushroom_chance = 0.014
    cactus_chance = 0.0
    sugar_cane_chance = 0.008
    elevation_bias = 3
    amplitude = 1.05
    double_plant_chance = 0.095
    double_plant_options = FOREST_DOUBLE_PLANTS


class DarkForest(Biome):
    biome_id = "dark_forest"
    name = "dark forest"
    temperature = 0.7
    downfall = 0.8
    sky_color = hex_to_rgb("#79a6ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.7, 0.8)
    foliage_color = _default_foliage_color(0.7, 0.8)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'dark_oak'
    tree_chance = 0.3
    grass_chance = 0.28
    flower_chance = 0.02
    fern_chance = 0.04
    mushroom_chance = 0.04
    cactus_chance = 0.0
    sugar_cane_chance = 0.005
    elevation_bias = 1
    amplitude = 1.0
    mushroom_boost = 1.8


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
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.135
    grass_chance = 0.24
    flower_chance = 0.012
    fern_chance = 0.16
    mushroom_chance = 0.016
    cactus_chance = 0.0
    sugar_cane_chance = 0.004
    elevation_bias = 3
    amplitude = 1.05
    double_plant_chance = 0.075
    double_plant_options = TAIGA_DOUBLE_PLANTS


class SnowyTaiga(Biome):
    biome_id = "snowy_taiga"
    name = "snowy taiga"
    temperature = -0.5
    downfall = 0.4
    sky_color = hex_to_rgb("#8396ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.5, 0.4)
    foliage_color = _default_foliage_color(-0.5, 0.4)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.125
    grass_chance = 0.18
    flower_chance = 0.018
    fern_chance = 0.1
    mushroom_chance = 0.004
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 4
    amplitude = 1.05
    is_cold = True
    double_plant_chance = 0.075
    double_plant_options = TAIGA_DOUBLE_PLANTS


class OldGrowthPineTaiga(Biome):
    biome_id = "old_growth_pine_taiga"
    name = "old growth pine taiga"
    temperature = 0.25
    downfall = 0.8
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.25, 0.8)
    foliage_color = _default_foliage_color(0.25, 0.8)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.165
    grass_chance = 0.22
    flower_chance = 0.01
    fern_chance = 0.18
    mushroom_chance = 0.02
    cactus_chance = 0.0
    sugar_cane_chance = 0.003
    elevation_bias = 5
    amplitude = 1.1
    double_plant_chance = 0.075
    double_plant_options = TAIGA_DOUBLE_PLANTS


class OldGrowthSpruceTaiga(Biome):
    biome_id = "old_growth_spruce_taiga"
    name = "old growth spruce taiga"
    temperature = 0.25
    downfall = 0.8
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.25, 0.8)
    foliage_color = _default_foliage_color(0.25, 0.8)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.155
    grass_chance = 0.2
    flower_chance = 0.008
    fern_chance = 0.17
    mushroom_chance = 0.022
    cactus_chance = 0.0
    sugar_cane_chance = 0.003
    elevation_bias = 5
    amplitude = 1.1
    double_plant_chance = 0.075
    double_plant_options = TAIGA_DOUBLE_PLANTS


class SnowyPlains(Biome):
    biome_id = "snowy_plains"
    name = "snowy plains"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.16
    flower_chance = 0.035
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 2
    amplitude = 0.95
    is_cold = True
    double_plant_chance = 0.045
    double_plant_options = SNOWY_DOUBLE_PLANTS


class IceSpikes(Biome):
    biome_id = "ice_spikes"
    name = "ice spikes"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.05
    flower_chance = 0.01
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 3
    amplitude = 1.0
    is_cold = True


class Grove(Biome):
    biome_id = "grove"
    name = "grove"
    temperature = -0.2
    downfall = 0.8
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.2, 0.8)
    foliage_color = _default_foliage_color(-0.2, 0.8)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.11
    grass_chance = 0.2
    flower_chance = 0.02
    fern_chance = 0.12
    mushroom_chance = 0.008
    cactus_chance = 0.0
    sugar_cane_chance = 0.002
    elevation_bias = 18
    amplitude = 2.0
    is_cold = True
    double_plant_chance = 0.075
    double_plant_options = TAIGA_DOUBLE_PLANTS


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
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.03
    grass_chance = 0.1
    flower_chance = 0.008
    fern_chance = 0.04
    mushroom_chance = 0.004
    cactus_chance = 0.0
    sugar_cane_chance = 0.002
    elevation_bias = 18
    amplitude = 2.2


class WindsweptGravellyHills(Biome):
    biome_id = "windswept_gravelly_hills"
    name = "windswept gravelly hills"
    temperature = 0.2
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.2, 0.3)
    foliage_color = _default_foliage_color(0.2, 0.3)
    surface = 'grass_block'
    subsurface = 'gravel'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.02
    grass_chance = 0.06
    flower_chance = 0.004
    fern_chance = 0.02
    mushroom_chance = 0.002
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 20
    amplitude = 2.3


class WindsweptForest(Biome):
    biome_id = "windswept_forest"
    name = "windswept forest"
    temperature = 0.2
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.2, 0.3)
    foliage_color = _default_foliage_color(0.2, 0.3)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.055
    grass_chance = 0.14
    flower_chance = 0.012
    fern_chance = 0.04
    mushroom_chance = 0.006
    cactus_chance = 0.0
    sugar_cane_chance = 0.003
    elevation_bias = 14
    amplitude = 1.8


class JaggedPeaks(Biome):
    biome_id = "jagged_peaks"
    name = "jagged peaks"
    temperature = -0.7
    downfall = 0.9
    sky_color = hex_to_rgb("#8da3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.7, 0.9)
    foliage_color = _default_foliage_color(-0.7, 0.9)
    surface = 'stone'
    subsurface = 'stone'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 55
    amplitude = 3.5
    is_cold = True


class FrozenPeaks(Biome):
    biome_id = "frozen_peaks"
    name = "frozen peaks"
    temperature = -0.7
    downfall = 0.9
    sky_color = hex_to_rgb("#8da3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.7, 0.9)
    foliage_color = _default_foliage_color(-0.7, 0.9)
    surface = 'snow_block'
    subsurface = 'stone'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 52
    amplitude = 3.3
    is_cold = True


class StonyPeaks(Biome):
    biome_id = "stony_peaks"
    name = "stony peaks"
    temperature = 1.0
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.0, 0.3)
    foliage_color = _default_foliage_color(1.0, 0.3)
    surface = 'stone'
    subsurface = 'stone'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 46
    amplitude = 3.0


class SnowySlopes(Biome):
    biome_id = "snowy_slopes"
    name = "snowy slopes"
    temperature = -0.3
    downfall = 0.9
    sky_color = hex_to_rgb("#829aff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(-0.3, 0.9)
    foliage_color = _default_foliage_color(-0.3, 0.9)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'spruce'
    tree_chance = 0.02
    grass_chance = 0.08
    flower_chance = 0.004
    fern_chance = 0.06
    mushroom_chance = 0.002
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 24
    amplitude = 2.4
    is_cold = True


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
    surface = 'sand'
    subsurface = 'sand'
    filler = 'sandstone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.045
    sugar_cane_chance = 0.0
    elevation_bias = -2
    amplitude = 0.78
    is_arid = True


class Savanna(Biome):
    biome_id = "savanna"
    name = "savanna"
    temperature = 1.2
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.2, 0.0)
    foliage_color = _default_foliage_color(1.2, 0.0)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'acacia'
    tree_chance = 0.045
    grass_chance = 0.2
    flower_chance = 0.012
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.006
    elevation_bias = 2
    amplitude = 1.2


class SavannaPlateau(Biome):
    biome_id = "savanna_plateau"
    name = "savanna plateau"
    temperature = 1.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.0, 0.0)
    foliage_color = _default_foliage_color(1.0, 0.0)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'acacia'
    tree_chance = 0.038
    grass_chance = 0.16
    flower_chance = 0.01
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.004
    elevation_bias = 10
    amplitude = 1.6


class WindsweptSavanna(Biome):
    biome_id = "windswept_savanna"
    name = "windswept savanna"
    temperature = 1.1
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(1.1, 0.0)
    foliage_color = _default_foliage_color(1.1, 0.0)
    surface = 'grass_block'
    subsurface = 'coarse_dirt'
    filler = 'stone'
    tree = 'acacia'
    tree_chance = 0.035
    grass_chance = 0.12
    flower_chance = 0.006
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.002
    elevation_bias = 10
    amplitude = 2.0


class Badlands(Biome):
    biome_id = "badlands"
    name = "badlands"
    temperature = 2.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(2.0, 0.0)
    foliage_color = _default_foliage_color(2.0, 0.0)
    surface = 'red_sand'
    subsurface = 'hardened_clay'
    filler = 'red_sandstone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.02
    sugar_cane_chance = 0.0
    elevation_bias = 6
    amplitude = 1.4
    is_arid = True


class WoodedBadlands(Biome):
    biome_id = "wooded_badlands"
    name = "wooded badlands"
    temperature = 2.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(2.0, 0.0)
    foliage_color = _default_foliage_color(2.0, 0.0)
    surface = 'red_sand'
    subsurface = 'hardened_clay'
    filler = 'red_sandstone'
    tree = 'oak'
    tree_chance = 0.03
    grass_chance = 0.06
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.012
    sugar_cane_chance = 0.0
    elevation_bias = 8
    amplitude = 1.5
    is_arid = True


class ErodedBadlands(Biome):
    biome_id = "eroded_badlands"
    name = "eroded badlands"
    temperature = 2.0
    downfall = 0.0
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(2.0, 0.0)
    foliage_color = _default_foliage_color(2.0, 0.0)
    surface = 'red_sand'
    subsurface = 'hardened_clay'
    filler = 'red_sandstone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.016
    sugar_cane_chance = 0.0
    elevation_bias = 14
    amplitude = 1.8
    is_arid = True


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
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'jungle_tree'
    tree_chance = 0.16
    grass_chance = 0.44
    flower_chance = 0.025
    fern_chance = 0.2
    mushroom_chance = 0.014
    cactus_chance = 0.0
    sugar_cane_chance = 0.04
    elevation_bias = 1
    amplitude = 1.05
    double_plant_chance = 0.07


class SparseJungle(Biome):
    biome_id = "sparse_jungle"
    name = "sparse jungle"
    temperature = 0.95
    downfall = 0.8
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.95, 0.8)
    foliage_color = _default_foliage_color(0.95, 0.8)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'jungle_tree'
    tree_chance = 0.06
    grass_chance = 0.4
    flower_chance = 0.02
    fern_chance = 0.14
    mushroom_chance = 0.01
    cactus_chance = 0.0
    sugar_cane_chance = 0.035
    elevation_bias = 0
    amplitude = 1.0
    double_plant_chance = 0.07


class BambooJungle(Biome):
    biome_id = "bamboo_jungle"
    name = "bamboo jungle"
    temperature = 0.95
    downfall = 0.9
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.95, 0.9)
    foliage_color = _default_foliage_color(0.95, 0.9)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'jungle_tree'
    tree_chance = 0.14
    grass_chance = 0.42
    flower_chance = 0.022
    fern_chance = 0.18
    mushroom_chance = 0.012
    cactus_chance = 0.0
    sugar_cane_chance = 0.038
    elevation_bias = 1
    amplitude = 1.05
    double_plant_chance = 0.07


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
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.055
    grass_chance = 0.36
    flower_chance = 0.015
    fern_chance = 0.0
    mushroom_chance = 0.045
    cactus_chance = 0.0
    sugar_cane_chance = 0.07
    elevation_bias = -4
    amplitude = 0.6
    mushroom_boost = 1.8
    double_plant_chance = 0.055
    flower_options = SWAMP_FLOWERS


class MangroveSwamp(Biome):
    biome_id = "mangrove_swamp"
    name = "mangrove swamp"
    temperature = 0.8
    downfall = 0.9
    sky_color = hex_to_rgb("#7ba4ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.9)
    foliage_color = _default_foliage_color(0.8, 0.9)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.07
    grass_chance = 0.3
    flower_chance = 0.01
    fern_chance = 0.0
    mushroom_chance = 0.04
    cactus_chance = 0.0
    sugar_cane_chance = 0.055
    elevation_bias = -3
    amplitude = 0.58


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
    surface = 'sand'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -14
    amplitude = 0.45


class DeepOcean(Biome):
    biome_id = "deep_ocean"
    name = "deep ocean"
    temperature = 0.5
    downfall = 0.5
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.5)
    foliage_color = _default_foliage_color(0.5, 0.5)
    surface = 'gravel'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -26
    amplitude = 0.38


class WarmOcean(Biome):
    biome_id = "warm_ocean"
    name = "warm ocean"
    temperature = 0.8
    downfall = 0.5
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.8, 0.5)
    foliage_color = _default_foliage_color(0.8, 0.5)
    surface = 'sand'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -15
    amplitude = 0.42


class LukewarmOcean(Biome):
    biome_id = "lukewarm_ocean"
    name = "lukewarm ocean"
    temperature = 0.6
    downfall = 0.5
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.5)
    foliage_color = _default_foliage_color(0.6, 0.5)
    surface = 'sand'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -16
    amplitude = 0.4


class ColdOcean(Biome):
    biome_id = "cold_ocean"
    name = "cold ocean"
    temperature = 0.3
    downfall = 0.5
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.3, 0.5)
    foliage_color = _default_foliage_color(0.3, 0.5)
    surface = 'gravel'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -17
    amplitude = 0.4
    freezes_ocean_surface = True
    is_cold = True


class FrozenOcean(Biome):
    biome_id = "frozen_ocean"
    name = "frozen ocean"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)
    is_cold = True
    freezes_ocean_surface = True


class DeepColdOcean(Biome):
    biome_id = "deep_cold_ocean"
    name = "deep cold ocean"
    temperature = 0.3
    downfall = 0.5
    sky_color = hex_to_rgb("#7ca3ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.3, 0.5)
    foliage_color = _default_foliage_color(0.3, 0.5)
    surface = 'gravel'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -28
    amplitude = 0.36
    freezes_ocean_surface = True
    is_cold = True


class DeepFrozenOcean(Biome):
    biome_id = "deep_frozen_ocean"
    name = "deep frozen ocean"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)
    freezes_ocean_surface = True
    is_cold = True


class DeepLukewarmOcean(Biome):
    biome_id = "deep_lukewarm_ocean"
    name = "deep lukewarm ocean"
    temperature = 0.6
    downfall = 0.5
    sky_color = hex_to_rgb("#6eb1ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.6, 0.5)
    foliage_color = _default_foliage_color(0.6, 0.5)
    surface = 'sand'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -27
    amplitude = 0.37


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
    surface = 'sand'
    subsurface = 'sand'
    filler = 'sandstone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.025
    elevation_bias = -2
    amplitude = 0.55


class SnowyBeach(Biome):
    biome_id = "snowy_beach"
    name = "snowy beach"
    temperature = 0.05
    downfall = 0.3
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.05, 0.3)
    foliage_color = _default_foliage_color(0.05, 0.3)
    surface = 'sand'
    subsurface = 'sand'
    filler = 'sandstone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -1
    amplitude = 0.52
    is_cold = True
    freezes_ocean_surface = True


class StonyShore(Biome):
    biome_id = "stony_shore"
    name = "stony shore"
    temperature = 0.2
    downfall = 0.3
    sky_color = hex_to_rgb("#7da2ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.2, 0.3)
    foliage_color = _default_foliage_color(0.2, 0.3)
    surface = 'stone'
    subsurface = 'stone'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 0
    amplitude = 0.5


class River(Biome):
    biome_id = "river"
    name = "river"
    temperature = 0.5
    downfall = 0.5
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.5)
    foliage_color = _default_foliage_color(0.5, 0.5)
    surface = 'sand'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -6
    amplitude = 0.35


class FrozenRiver(Biome):
    biome_id = "frozen_river"
    name = "frozen river"
    temperature = 0.0
    downfall = 0.5
    sky_color = hex_to_rgb("#89a0ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.0, 0.5)
    foliage_color = _default_foliage_color(0.0, 0.5)
    surface = 'sand'
    subsurface = 'sand'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -5
    amplitude = 0.35
    is_cold = True


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
    surface = 'stone'
    subsurface = 'stone'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.0
    flower_chance = 0.0
    fern_chance = 0.0
    mushroom_chance = 0.0
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = -5
    amplitude = 0.7


class LushCaves(Biome):
    biome_id = "lush_caves"
    name = "lush caves"
    temperature = 0.5
    downfall = 0.5
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")
    grass_color = _default_grass_color(0.5, 0.5)
    foliage_color = _default_foliage_color(0.5, 0.5)
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = 'oak'
    tree_chance = 0.02
    grass_chance = 0.22
    flower_chance = 0.03
    fern_chance = 0.06
    mushroom_chance = 0.03
    cactus_chance = 0.0
    sugar_cane_chance = 0.01
    elevation_bias = -3
    amplitude = 0.8


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
    surface = 'grass_block'
    subsurface = 'dirt'
    filler = 'stone'
    tree = None
    tree_chance = 0.0
    grass_chance = 0.15
    flower_chance = 0.02
    fern_chance = 0.0
    mushroom_chance = 0.08
    cactus_chance = 0.0
    sugar_cane_chance = 0.0
    elevation_bias = 0
    amplitude = 0.9




# ---------------------------------------------------------------------------
# 生物群系世界生成属性
# ---------------------------------------------------------------------------

def _iter_biome_classes():
    """遍历 Biome 的所有子类。"""
    def collect(cls):
        for subclass in cls.__subclasses__():
            yield subclass
            yield from collect(subclass)

    yield from collect(Biome)


def _profile_from_biome_class(cls: type[Biome]) -> BiomeProfile:
    return BiomeProfile(
        biome_id=cls.biome_id,
        surface=cls.surface,
        subsurface=cls.subsurface,
        filler=cls.filler,
        tree=cls.tree,
        tree_chance=cls.tree_chance,
        grass_chance=cls.grass_chance,
        flower_chance=cls.flower_chance,
        fern_chance=cls.fern_chance,
        mushroom_chance=cls.mushroom_chance,
        cactus_chance=cls.cactus_chance,
        sugar_cane_chance=cls.sugar_cane_chance,
        elevation_bias=cls.elevation_bias,
        amplitude=cls.amplitude,
        is_cold=cls.is_cold,
        is_arid=cls.is_arid,
        freezes_ocean_surface=cls.freezes_ocean_surface,
        mushroom_boost=cls.mushroom_boost,
        double_plant_chance=cls.double_plant_chance,
        double_plant_options=cls.double_plant_options,
        flower_options=cls.flower_options,
    )


def _build_biome_profiles() -> dict[str, BiomeProfile]:
    profiles = {}
    for cls in _iter_biome_classes():
        bid = getattr(cls, "biome_id", None)
        if bid and bid != "null" and bid != Void.biome_id:
            profiles[bid] = _profile_from_biome_class(cls)
    profiles.setdefault("plains", _profile_from_biome_class(Plains))
    return profiles


BIOME_PROFILES: dict[str, BiomeProfile] = _build_biome_profiles()
COLD_BIOMES = frozenset(bid for bid, profile in BIOME_PROFILES.items() if profile.is_cold)
ARID_BIOMES = frozenset(bid for bid, profile in BIOME_PROFILES.items() if profile.is_arid)
ICE_OCEAN_BIOMES = frozenset(
    bid for bid, profile in BIOME_PROFILES.items() if profile.freezes_ocean_surface
)


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

    for subclass in _iter_biome_classes():
        bid = getattr(subclass, "biome_id", None)
        if bid is not None and bid != "null":
            cache[bid] = subclass
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


def get_effective_temperature(biome_id: str, y: int | float) -> float:
    """Return Minecraft-style local temperature, including altitude cooling."""
    global _BIOME_REGISTRY
    if _BIOME_REGISTRY is None:
        _BIOME_REGISTRY = _build_biome_id_cache()

    biome_cls = _BIOME_REGISTRY.get(_normalize_biome_id(biome_id), Plains)
    temperature = float(getattr(biome_cls, "temperature", Biome.temperature))
    height = float(y)
    if height > 80.0:
        temperature -= (height - 80.0) / 600.0
    return temperature


def get_precipitation_type(biome_id: str, y: int | float) -> str:
    """Return ``none``, ``rain`` or ``snow`` for a biome position."""
    global _BIOME_REGISTRY
    if _BIOME_REGISTRY is None:
        _BIOME_REGISTRY = _build_biome_id_cache()

    biome_cls = _BIOME_REGISTRY.get(_normalize_biome_id(biome_id), Plains)
    if float(getattr(biome_cls, "downfall", Biome.downfall)) <= 0.0:
        return "none"
    return "snow" if get_effective_temperature(biome_id, y) <= 0.15 else "rain"
