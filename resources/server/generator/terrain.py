"""
地形生成 mixin 模块

提供生物群系判定、地形高度计算、地下方块放置、
矿石分布、石头变种和洞穴系统的生成逻辑。
"""

from resources.server.blocks import *
from resources.server.generator.config import BiomeProfile
from resources.server.generator.noise import NoiseMixin


class TerrainMixin(NoiseMixin):
    """地形生成 mixin。

    提供生物群系判定、地表高度、地下分层方块、矿石、
    石头变种以及洞穴系统的生成方法。
    需要宿主类提供 ``self.sea_level`` 属性。
    """

    # ---- 生物群系配置表 ----
    # fmt: off
    biome_profiles = {
        "plains":                  BiomeProfile("plains",                  "grass_block", "dirt",      "stone",          "oak",         0.018, 0.28,  0.035, 0.0,  0.002, 0.0,   0.018,  0,  1.0),
        "sunflower_plains":        BiomeProfile("sunflower_plains",        "grass_block", "dirt",      "stone",          "oak",         0.018, 0.32,  0.08,  0.0,  0.002, 0.0,   0.018,  0,  1.0),
        "forest":                  BiomeProfile("forest",                  "grass_block", "dirt",      "stone",          "oak",         0.095, 0.34,  0.035, 0.02, 0.018, 0.0,   0.01,   2,  1.05),
        "birch_forest":            BiomeProfile("birch_forest",            "grass_block", "dirt",      "stone",          "birch",       0.08,  0.30,  0.03,  0.015,0.01,  0.0,   0.01,   2,  1.0),
        "old_growth_birch_forest": BiomeProfile("old_growth_birch_forest", "grass_block", "dirt",      "stone",          "birch",       0.11,  0.28,  0.025, 0.02, 0.014, 0.0,   0.008,  3,  1.05),
        "dark_forest":             BiomeProfile("dark_forest",             "grass_block", "dirt",      "stone",          "dark_oak",    0.13,  0.22,  0.02,  0.025,0.035, 0.0,   0.005,  1,  1.0),
        "taiga":                   BiomeProfile("taiga",                   "grass_block", "dirt",      "stone",          "spruce",      0.075, 0.22,  0.01,  0.13, 0.016, 0.0,   0.004,  3,  1.05),
        "snowy_taiga":             BiomeProfile("snowy_taiga",             "snow",        "dirt",      "stone",          "spruce",      0.07,  0.12,  0.0,   0.08, 0.004, 0.0,   0.0,    4,  1.05),
        "snowy_plains":            BiomeProfile("snowy_plains",            "snow",        "dirt",      "stone",          None,          0.0,   0.08,  0.0,   0.0,  0.0,   0.0,   0.0,    2,  0.95),
        "desert":                  BiomeProfile("desert",                  "sand",        "sand",      "sandstone",      None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.035, 0.0,   -2,  0.78),
        "savanna":                 BiomeProfile("savanna",                 "grass_block", "dirt",      "stone",          "acacia",      0.04,  0.18,  0.01,  0.0,  0.0,   0.0,   0.006,  1,  1.2),
        "windswept_savanna":       BiomeProfile("windswept_savanna",       "grass_block", "coarse_dirt","stone",         "acacia",      0.035, 0.12,  0.005, 0.0,  0.0,   0.0,   0.002,  8,  1.8),
        "jungle":                  BiomeProfile("jungle",                  "grass_block", "dirt",      "stone",          "jungle_tree", 0.12,  0.42,  0.02,  0.18, 0.012, 0.0,   0.035,  1,  1.05),
        "sparse_jungle":           BiomeProfile("sparse_jungle",           "grass_block", "dirt",      "stone",          "jungle_tree", 0.045, 0.38,  0.018, 0.12, 0.008, 0.0,   0.03,   0,  1.0),
        "badlands":                BiomeProfile("badlands",                "red_sand",    "hardened_clay","red_sandstone",None,         0.0,   0.0,   0.0,   0.0,  0.0,   0.018, 0.0,    5,  1.35),
        "wooded_badlands":         BiomeProfile("wooded_badlands",         "red_sand",    "hardened_clay","red_sandstone","oak",        0.025, 0.05,  0.0,   0.0,  0.0,   0.01,  0.0,    7,  1.45),
        "swamp":                   BiomeProfile("swamp",                   "grass_block", "dirt",      "stone",          "oak",         0.045, 0.35,  0.015, 0.0,  0.035, 0.0,   0.06,  -4,  0.62),
        "beach":                   BiomeProfile("beach",                   "sand",        "sand",      "sandstone",      None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.025, -2,  0.55),
        "ocean":                   BiomeProfile("ocean",                   "sand",        "sand",      "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,  -13,  0.45),
        "deep_ocean":              BiomeProfile("deep_ocean",              "gravel",      "sand",      "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,  -24,  0.4),
        "frozen_ocean":            BiomeProfile("frozen_ocean",            "gravel",      "sand",      "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,  -15,  0.4),
        "mountains":               BiomeProfile("windswept_hills",         "grass_block", "dirt",      "stone",          "spruce",      0.026, 0.08,  0.0,   0.04, 0.0,   0.0,   0.0,   17,  2.1),
    }
    # fmt: on

    # ---- 矿石生成规则 ----
    # 每个元组: (block_id, 阈值, 最小Y, 最大Y, 噪声盐值)
    # 阈值越高矿石越稀有；噪声值 > 1.0 - 阈值*6 时生成该矿石
    ore_rules: tuple[tuple[str, float, int, int, int], ...] = (
        ("coal_ore",    0.078,  34, 128, 301),
        ("iron_ore",    0.052,   8,  88, 302),
        ("gold_ore",    0.018,   4,  42, 303),
        ("redstone_ore", 0.019,  4,  28, 304),
        ("lapis_ore",   0.014,  10,  40, 305),
        ("diamond_ore", 0.010,   3,  22, 306),
        ("emerald_ore", 0.006,  18,  80, 307),
    )

    # ------------------------------------------------------------------
    # 生物群系判定
    # ------------------------------------------------------------------

    def get_profile(self, biome_id: str) -> BiomeProfile:
        """根据生物群系 ID 获取对应的 BiomeProfile 配置。

        支持 "old_growth_" 前缀的回退（如 ``old_growth_birch_forest``
        → ``birch_forest``），回退失败则返回 plains。

        Parameters
        ----------
        biome_id : str
            生物群系标识名。

        Returns
        -------
        BiomeProfile
            对应的生物群系配置。
        """
        if biome_id in self.biome_profiles:
            return self.biome_profiles[biome_id]
        # 尝试去掉 "old_growth_" 前缀回退
        return self.biome_profiles.get(
            biome_id.replace("old_growth_", ""),
            self.biome_profiles["plains"]
        )

    def get_column_biome(self, x: int) -> str:
        """通过五维噪声参数判定指定列的生物群系。

        使用五组独立的 1D Perlin 噪声生成参数：

        - **大陆性** (continentalness)：决定海洋 / 陆地 / 深海
        - **温度** (temperature)：决定热带 / 寒带
        - **湿度** (humidity)：决定湿润 / 干旱
        - **奇异度** (weirdness)：决定特殊地形（山地）
        - **侵蚀度** (erosion)：决定地形侵蚀程度

        这五个参数通过优先级决策树映射为生物群系 ID。

        Parameters
        ----------
        x : int
            全局 X 坐标。

        Returns
        -------
        str
            生物群系标识名。
        """
        # 五维噪声参数（每层使用不同 scale / octaves / salt 确保独立性）
        continentalness = self._noise1(x, 0.0025, 4, 10)
        temperature     = self._noise1(x, 0.0032, 3, 20)
        humidity        = self._noise1(x, 0.0030, 3, 30)
        weirdness       = self._noise1(x, 0.0042, 2, 40)
        erosion         = self._noise1(x, 0.005,  2, 50)

        # 优先级决策树（从上到下匹配，先匹配先生效）
        # 1. 海洋判定
        if continentalness < -0.58:
            return "deep_ocean" if continentalness < -0.78 else (
                "frozen_ocean" if temperature < -0.45 else "ocean"
            )
        # 2. 沙滩判定
        if continentalness < -0.43:
            return "beach"
        # 3. 山地判定
        if weirdness > 0.68 and continentalness > 0.08:
            return "mountains"
        # 4. 寒冷气候判定
        if temperature < -0.48:
            return "snowy_taiga" if humidity > -0.2 else "snowy_plains"
        # 5. 炎热干旱气候判定
        if temperature > 0.55 and humidity < -0.35:
            return "badlands" if weirdness > 0.35 else "desert"
        # 6. 温暖半干旱气候判定
        if temperature > 0.45 and humidity < 0.05:
            return "windswept_savanna" if erosion < -0.45 else "savanna"
        # 7. 热带湿润气候判定
        if temperature > 0.35 and humidity > 0.45:
            return "jungle" if humidity > 0.62 else "sparse_jungle"
        # 8. 沼泽判定
        if humidity > 0.55 and continentalness < 0.15:
            return "swamp"
        # 9. 湿润气候（森林类）
        if humidity > 0.28:
            if weirdness > 0.42:
                return "dark_forest"
            return "birch_forest" if temperature > 0.12 else "taiga"
        # 10. 奇异地形判定
        if weirdness > 0.58:
            return "sunflower_plains"
        # 11. 默认：森林或平原
        return "forest" if humidity > 0.0 else "plains"

    # ------------------------------------------------------------------
    # 地形高度
    # ------------------------------------------------------------------

    def get_surface_height(self, x: int) -> int:
        """计算指定列的地表高度。

        高度由四层噪声叠加而成：

        - **broad**（大尺度）: 低频高振幅 → 大陆架起伏
        - **hills**（中尺度）: 中频 × 群系振幅 → 丘陵
        - **detail**（小尺度）: 高频低振幅 → 微观细节
        - **elevation_bias**: 群系海拔偏移

        最终高度限制在 [8, 230] 范围内。

        Parameters
        ----------
        x : int
            全局 X 坐标。

        Returns
        -------
        int
            该列的地表高度（Y 坐标），取整并钳制。
        """
        profile = self.get_profile(self.get_column_biome(x))
        broad  = self._noise1(x, 0.004, 5, 80) * 10           # 大陆架起伏
        hills  = self._noise1(x, 0.018, 4, 90) * 6 * profile.amplitude  # 丘陵
        detail = self._noise1(x, 0.065, 2, 100) * 2            # 微观细节
        height = self.sea_level + profile.elevation_bias + broad + hills + detail
        return max(8, min(230, int(round(height))))

    # ------------------------------------------------------------------
    # 地下方块
    # ------------------------------------------------------------------

    def get_underground_block(self, x: int, y: int, surface_y: int, profile: BiomeProfile):
        """获取地表以下的方块（按深度分层）。

        分层规则（从地表往下）：
        - depth 0 → 表层方块 (surface)
        - depth 1-4 → 亚层方块 (subsurface)
        - depth 5-8 → 填充层（仅砂岩 / 红砂岩群系）
        - 更深处 → 优先矿脉，无矿脉则放石头变种

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。
        surface_y : int
            该列的地表高度。
        profile : BiomeProfile
            该列的生物群系配置。

        Returns
        -------
        Block
            对应的地下方块。
        """
        depth = surface_y - y
        # 表层（地表方块）
        if depth == 0:
            return self._block(profile.surface)
        # 亚层（地表下 1-4 格）
        if depth <= 4:
            return self._block(profile.subsurface)
        # 砂岩 / 红砂岩的额外填充层（地表下 5-8 格）
        if profile.filler in {"sandstone", "red_sandstone"} and depth <= 8:
            return self._block(profile.filler)

        # 矿石检查
        ore = self.get_ore_block_id(x, y)
        if ore:
            return self._block(ore)

        # 默认：石头变种
        stone_variant = self.get_stone_variant(x, y)
        return self._block(stone_variant)

    def get_stone_variant(self, x: int, y: int) -> str:
        """获取石头变种（花岗岩 / 闪长岩 / 安山岩 / 普通石头）。

        使用 2D 噪声决定该位置的石材类型，模拟 MC 的石头变种分布。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。

        Returns
        -------
        str
            石头变种的 block_id。
        """
        value = self._noise2(x, y, 0.055, 2, 220)
        if value > 0.52:
            return "granite"
        if value < -0.54:
            return "diorite"
        if self._noise2(x, y, 0.047, 2, 221) > 0.56:
            return "andesite"
        return "stone"

    def get_ore_block_id(self, x: int, y: int) -> str | None:
        """尝试获取该位置的矿石 block_id。

        对每条矿石规则依次检查：高度范围 → 丰富度噪声 → 矿团噪声，
        满足条件则返回矿石 ID。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。

        Returns
        -------
        str | None
            矿石 block_id，若无矿石则返回 None。
        """
        for block_id, threshold, min_y, max_y, salt in self.ore_rules:
            if min_y <= y <= max_y:
                richness = self._noise2(x, y, 0.087, 2, salt)
                pocket   = self._noise2(x, y, 0.22,  1, salt + 90)
                # 丰富度超过阈值且处于矿团范围内
                if richness > 1.0 - threshold * 6 and pocket > 0.08:
                    return block_id
        return None

    # ------------------------------------------------------------------
    # 洞穴系统
    # ------------------------------------------------------------------

    def is_cave_air(self, x: int, y: int, z: int, surface_y: int) -> bool:
        """判断指定位置是否为洞穴空气（应放置空气）。

        使用三层噪声混合生成洞穴：

        - **large**（大洞穴）: 低频 3-octave → 大型开放空间
        - **tunnels**（隧道）: 中频 2-octave → 连接通道
        - **worms**（虫洞）: 高频 1-octave → 细小的蜿蜒洞穴

        深度因子随着接近地表递减，保证地表附近不被挖空。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。
        z : int
            层索引（目前仅 z==0 生成洞穴）。
        surface_y : int
            该列的地表高度。

        Returns
        -------
        bool
            True 表示该位置应为空气（洞穴）。
        """
        # 洞穴仅在前景层生成，且排除极端高度
        if z != 0 or y <= 2 or y >= surface_y - 3:
            return False
        # 三层洞穴噪声
        large   = self._noise2(x, y, 0.035, 3, 400)
        tunnels = self._noise2(x, y, 0.09,  2, 410)
        worms   = abs(self._noise2(x, y, 0.022, 1, 420))
        # 深度因子：越接近地表，洞穴越稀少
        depth_factor = min(1.0, max(0.0, (surface_y - y) / 32))
        # 大洞穴 / 隧道混合判定 或 虫洞判定
        return (
            large + tunnels * 0.55 + depth_factor * 0.18 > 0.47
        ) or (
            worms < 0.045 and tunnels > -0.18
        )

    # 注：
    # _block(block_id) 方法由 DecorationMixin 提供。
    # TerrainMixin 中的 get_underground_block 通过 self._block(...) 调用，
    # 在 MinecraftLike2D 的 MRO 中会正确解析到 DecorationMixin._block。
