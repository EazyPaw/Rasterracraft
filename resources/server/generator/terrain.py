"""
地形生成 mixin 模块

提供生物群系判定、地形高度计算、地下方块放置、
矿石分布、石头变种和洞穴系统的生成逻辑。
"""

from functools import lru_cache

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
        # ── 平原 / 草甸 ──
        "plains":                  BiomeProfile("plains",                  "grass_block", "dirt",        "stone",          "oak",         0.020, 0.28, 0.035, 0.0,  0.002, 0.0,   0.018,   0,  1.0),
        "sunflower_plains":        BiomeProfile("sunflower_plains",        "grass_block", "dirt",        "stone",          "oak",         0.020, 0.32, 0.080, 0.0,  0.002, 0.0,   0.018,   0,  1.0),
        "meadow":                  BiomeProfile("meadow",                  "grass_block", "dirt",        "stone",          "oak",         0.010, 0.30, 0.080, 0.0,  0.002, 0.0,   0.010,   3,  1.1),

        # ── 森林 ──
        "forest":                  BiomeProfile("forest",                  "grass_block", "dirt",        "stone",          "oak",         0.100, 0.34, 0.035, 0.02, 0.018, 0.0,   0.010,   2,  1.05),
        "flower_forest":           BiomeProfile("flower_forest",           "grass_block", "dirt",        "stone",          "oak",         0.070, 0.38, 0.120, 0.02, 0.020, 0.0,   0.008,   2,  1.0),
        "birch_forest":            BiomeProfile("birch_forest",            "grass_block", "dirt",        "stone",          "birch",       0.090, 0.30, 0.030, 0.015,0.010, 0.0,   0.010,   2,  1.0),
        "old_growth_birch_forest": BiomeProfile("old_growth_birch_forest", "grass_block", "dirt",        "stone",          "birch",       0.120, 0.28, 0.025, 0.02, 0.014, 0.0,   0.008,   3,  1.05),
        "dark_forest":             BiomeProfile("dark_forest",             "grass_block", "dirt",        "stone",          "dark_oak",    0.140, 0.22, 0.020, 0.03, 0.040, 0.0,   0.005,   1,  1.0),

        # ── 针叶林 / 雪 ──
        "taiga":                   BiomeProfile("taiga",                   "grass_block", "dirt",        "stone",          "spruce",      0.090, 0.22, 0.010, 0.14, 0.016, 0.0,   0.004,   3,  1.05),
        "snowy_taiga":             BiomeProfile("snowy_taiga",             "grass_block", "dirt",        "stone",          "spruce",      0.070, 0.12, 0.000, 0.08, 0.004, 0.0,   0.000,   4,  1.05),
        "old_growth_pine_taiga":   BiomeProfile("old_growth_pine_taiga",   "grass_block", "dirt",        "stone",          "spruce",      0.110, 0.20, 0.008, 0.16, 0.020, 0.0,   0.003,   5,  1.1),
        "old_growth_spruce_taiga": BiomeProfile("old_growth_spruce_taiga", "grass_block", "dirt",        "stone",          "spruce",      0.100, 0.18, 0.006, 0.15, 0.022, 0.0,   0.003,   5,  1.1),
        "snowy_plains":            BiomeProfile("snowy_plains",            "grass_block", "dirt",        "stone",          None,          0.000, 0.08, 0.000, 0.0,  0.000, 0.0,   0.000,   2,  0.95),
        "ice_spikes":              BiomeProfile("ice_spikes",              "grass_block", "dirt",        "stone",          None,          0.000, 0.02, 0.000, 0.0,  0.000, 0.0,   0.000,   3,  1.0),
        "grove":                   BiomeProfile("grove",                   "grass_block", "dirt",        "stone",          "spruce",      0.060, 0.16, 0.010, 0.10, 0.008, 0.0,   0.002,   18,  2.0),

        # ── 山地 ──
        "windswept_hills":         BiomeProfile("windswept_hills",         "grass_block", "dirt",        "stone",          "spruce",      0.030, 0.10, 0.008, 0.04, 0.004, 0.0,   0.002,   18,  2.2),
        "windswept_gravelly_hills":BiomeProfile("windswept_gravelly_hills","grass_block", "gravel",      "stone",          "spruce",      0.020, 0.06, 0.004, 0.02, 0.002, 0.0,   0.000,   20,  2.3),
        "windswept_forest":        BiomeProfile("windswept_forest",        "grass_block", "dirt",        "stone",          "oak",         0.055, 0.14, 0.012, 0.04, 0.006, 0.0,   0.003,   14,  1.8),
        "jagged_peaks":            BiomeProfile("jagged_peaks",            "stone",       "stone",       "stone",          None,          0.000, 0.00, 0.000, 0.0,  0.000, 0.0,   0.000,   55,  3.5),
        "frozen_peaks":            BiomeProfile("frozen_peaks",            "snow_block",  "stone",       "stone",          None,          0.000, 0.00, 0.000, 0.0,  0.000, 0.0,   0.000,   52,  3.3),
        "stony_peaks":             BiomeProfile("stony_peaks",             "stone",       "stone",       "stone",          None,          0.000, 0.00, 0.000, 0.0,  0.000, 0.0,   0.000,   46,  3.0),
        "snowy_slopes":            BiomeProfile("snowy_slopes",            "grass_block", "dirt",        "stone",          "spruce",      0.020, 0.08, 0.004, 0.06, 0.002, 0.0,   0.000,   24,  2.4),

        # ── 沙漠 / 热带草原 ──
        "desert":                  BiomeProfile("desert",                  "sand",        "sand",        "sandstone",      None,          0.000, 0.00, 0.000, 0.0,  0.000, 0.045, 0.000,  -2,  0.78),
        "savanna":                 BiomeProfile("savanna",                 "grass_block", "dirt",        "stone",          "acacia",      0.045, 0.20, 0.012, 0.0,  0.000, 0.0,   0.006,   2,  1.2),
        "savanna_plateau":         BiomeProfile("savanna_plateau",         "grass_block", "dirt",        "stone",          "acacia",      0.038, 0.16, 0.010, 0.0,  0.000, 0.0,   0.004,   10,  1.6),
        "windswept_savanna":       BiomeProfile("windswept_savanna",       "grass_block", "coarse_dirt", "stone",          "acacia",      0.035, 0.12, 0.006, 0.0,  0.000, 0.0,   0.002,   10,  2.0),
        "badlands":                BiomeProfile("badlands",                "red_sand",    "hardened_clay","red_sandstone", None,          0.000, 0.00, 0.000, 0.0,  0.000, 0.020, 0.000,   6,  1.4),
        "wooded_badlands":         BiomeProfile("wooded_badlands",         "red_sand",    "hardened_clay","red_sandstone","oak",         0.030, 0.06, 0.000, 0.0,  0.000, 0.012, 0.000,   8,  1.5),
        "eroded_badlands":         BiomeProfile("eroded_badlands",         "red_sand",    "hardened_clay","red_sandstone", None,         0.000, 0.00, 0.000, 0.0,  0.000, 0.016, 0.000,  14,  1.8),

        # ── 丛林 ──
        "jungle":                  BiomeProfile("jungle",                  "grass_block", "dirt",        "stone",          "jungle_tree", 0.160, 0.44, 0.025, 0.20, 0.014, 0.0,   0.040,   1,  1.05),
        "sparse_jungle":           BiomeProfile("sparse_jungle",           "grass_block", "dirt",        "stone",          "jungle_tree", 0.060, 0.40, 0.020, 0.14, 0.010, 0.0,   0.035,   0,  1.0),
        "bamboo_jungle":           BiomeProfile("bamboo_jungle",           "grass_block", "dirt",        "stone",          "jungle_tree", 0.140, 0.42, 0.022, 0.18, 0.012, 0.0,   0.038,   1,  1.05),

        # ── 沼泽 ──
        "swamp":                   BiomeProfile("swamp",                   "grass_block", "dirt",        "stone",          "oak",         0.055, 0.36, 0.015, 0.0,  0.045, 0.0,   0.070,  -4,  0.60),
        "mangrove_swamp":          BiomeProfile("mangrove_swamp",          "grass_block", "dirt",        "stone",          "oak",         0.070, 0.30, 0.010, 0.0,  0.040, 0.0,   0.055,  -3,  0.58),

        # ── 海洋 ──
        "ocean":                   BiomeProfile("ocean",                   "sand",        "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -14,  0.45),
        "deep_ocean":              BiomeProfile("deep_ocean",              "gravel",      "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -26,  0.38),
        "warm_ocean":              BiomeProfile("warm_ocean",              "sand",        "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -15,  0.42),
        "lukewarm_ocean":          BiomeProfile("lukewarm_ocean",          "sand",        "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -16,  0.40),
        "cold_ocean":              BiomeProfile("cold_ocean",              "gravel",      "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -17,  0.40),
        "frozen_ocean":            BiomeProfile("frozen_ocean",            "gravel",      "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -16,  0.38),
        "deep_cold_ocean":         BiomeProfile("deep_cold_ocean",         "gravel",      "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -28,  0.36),
        "deep_frozen_ocean":       BiomeProfile("deep_frozen_ocean",       "gravel",      "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -27,  0.36),
        "deep_lukewarm_ocean":     BiomeProfile("deep_lukewarm_ocean",     "sand",        "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.0,   -27,  0.37),

        # ── 沙滩 / 河流 ──
        "beach":                   BiomeProfile("beach",                   "sand",        "sand",        "sandstone",      None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.025,  -2,  0.55),
        "snowy_beach":             BiomeProfile("snowy_beach",             "sand",        "sand",        "sandstone",      None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.000,  -1,  0.52),
        "stony_shore":             BiomeProfile("stony_shore",             "stone",       "stone",       "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.000,   0,  0.50),
        "river":                   BiomeProfile("river",                   "sand",        "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.000,  -6,  0.35),
        "frozen_river":            BiomeProfile("frozen_river",            "sand",        "sand",        "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.000,  -5,  0.35),

        # ── 特殊 ──
        "mushroom_fields":         BiomeProfile("mushroom_fields",         "grass_block", "dirt",        "stone",          None,          0.0,   0.15, 0.020, 0.0,  0.080, 0.0,   0.000,   0,  0.90),

        # ── 洞穴（地表为最后回退） ──
        "dripstone_caves":         BiomeProfile("dripstone_caves",         "stone",       "stone",       "stone",          None,          0.0,   0.0,   0.0,   0.0,  0.0,   0.0,   0.000,  -5,  0.7),
        "lush_caves":              BiomeProfile("lush_caves",              "grass_block", "dirt",        "stone",          "oak",         0.02,  0.22, 0.030, 0.06, 0.030, 0.0,   0.010,  -3,  0.8),
    }
    # fmt: on

    # ---- 寒冷群系集合（用于积雪判定） ----
    COLD_BIOMES = frozenset({
        "snowy_plains", "snowy_taiga", "ice_spikes",
        "frozen_peaks", "jagged_peaks", "snowy_slopes", "grove",
        "snowy_beach", "frozen_river",
        "frozen_ocean", "deep_frozen_ocean",
    })

    # ---- 矿石生成规则 ----
    # 每个元组: (block_id, 生成概率, 最小Y, 最大Y, 哈希盐值)
    # 概率表示每个在Y范围内的石头方块生成该矿石的概率
    ore_rules: tuple[tuple[str, float, int, int, int], ...] = (
        ("coal_ore",     0.018,  10, 128, 301),
        ("iron_ore",     0.012,   5,  68, 302),
        ("gold_ore",     0.006,   3,  34, 303),
        ("redstone_ore", 0.005,   3,  22, 304),
        ("lapis_ore",    0.004,   5,  36, 305),
        ("diamond_ore",  0.003,   3,  18, 306),
        ("emerald_ore",  0.002,  18,  76, 307),
    )

    ore_vein_rules: tuple[tuple[str, float, int, int, int, int, int, int], ...] = (
        # block_id, veins per cell, min_y, max_y, salt, cell size, min radius, max radius
        ("coal_ore",     0.10,  24, 132, 301, 16, 2, 5),
        ("iron_ore",     0.075,  8,  82, 302, 15, 2, 4),
        ("gold_ore",     0.035,  3,  38, 303, 14, 1, 3),
        ("redstone_ore", 0.035,  3,  24, 304, 13, 1, 3),
        ("lapis_ore",    0.025,  6,  36, 305, 13, 1, 2),
        ("diamond_ore",  0.016,  3,  18, 306, 12, 1, 2),
        ("emerald_ore",  0.014, 18,  86, 307, 12, 1, 2),
    )

    # ------------------------------------------------------------------
    # 生物群系判定
    # ------------------------------------------------------------------

    def get_profile(self, biome_id: str) -> BiomeProfile:
        """根据生物群系 ID 获取对应的 BiomeProfile 配置。

        支持回退链：old_growth_ → 基础群系 → plains。
        """
        if biome_id in self.biome_profiles:
            return self.biome_profiles[biome_id]
        # 尝试去掉 "old_growth_" 前缀回退
        base = biome_id.replace("old_growth_", "")
        return self.biome_profiles.get(base, self.biome_profiles["plains"])

    @lru_cache(maxsize=8192)
    def get_column_biome(self, x: int) -> str:
        """通过五维噪声参数判定指定列的生物群系。

        五维参数：大陆性（continentalness）决定海陆分布，
        温度（temperature）和湿度（humidity）决定气候带，
        奇异度（weirdness）和侵蚀度（erosion）添加地形变化。

        阈值经过平衡，目标分布：~22% 海洋, ~10% 沙滩,
        ~5% 河流, ~10% 山地, ~12% 寒冷, ~12% 炎热,
        ~6% 丛林, ~4% 沼泽, ~14% 森林, ~5% 平原。
        """
        # 降低 octaves 以避免噪声值过度集中在 0 附近
        continentalness = self._noise1(x, 0.0085, 2, 10)
        temperature     = self._noise1(x, 0.011,  2, 20)
        humidity        = self._noise1(x, 0.010,  2, 30)
        weirdness       = self._noise1(x, 0.014,  2, 40)
        erosion         = self._noise1(x, 0.016,  2, 50)
        # 非线性拉伸：让噪声值更均匀地分布在整个 [-1,1] 范围
        continentalness = continentalness * (1.0 + abs(continentalness) * 1.2)
        temperature     = temperature * (1.0 + abs(temperature) * 0.6)
        humidity        = humidity * (1.0 + abs(humidity) * 0.6)

        # ── 1. 海洋（大陆性 < -0.12） ──
        if continentalness < -0.12:
            if continentalness < -0.48:          # 深海
                if temperature < -0.15:
                    return "deep_frozen_ocean"
                if temperature > 0.35:
                    return "deep_lukewarm_ocean"
                return "deep_ocean" if humidity > 0.2 else "deep_cold_ocean"
            else:                                 # 浅海
                if temperature < -0.10:
                    return "frozen_ocean"
                if temperature > 0.45:
                    return "warm_ocean"
                if temperature > 0.15:
                    return "lukewarm_ocean"
                return "cold_ocean" if humidity < 0.0 else "ocean"

        # ── 2. 沙滩（大陆性 -0.12 至 -0.04） ──
        if continentalness < -0.04:
            if temperature < -0.05:
                return "snowy_beach"
            if erosion < -0.30:
                return "stony_shore"
            return "beach"

        # ── 3. 河流（大陆性接近 0 + 奇异度低） ──
        if abs(continentalness) < 0.012 and abs(weirdness) < 0.045:
            return "frozen_river" if temperature < -0.05 else "river"

        # ── 4. 高峰（奇异度 > 0.35） ──
        if weirdness > 0.19:
            if temperature < -0.15:
                return "frozen_peaks" if continentalness > 0.20 else "jagged_peaks"
            if temperature > 0.40:
                return "stony_peaks"
            return "windswept_hills"

        # ── 5. 丘陵（奇异度 > 0.16） ──
        if weirdness > 0.085:
            if temperature < -0.25:
                return "snowy_slopes"
            if humidity < -0.28:
                return "windswept_gravelly_hills"
            if temperature > 0.32 and humidity < -0.08:
                return "windswept_savanna"
            if temperature > 0.12:
                return "windswept_forest"
            return "grove"

        # ── 气候带判定 ──

        # 6. 寒冷气候（温度 < -0.12）
        if temperature < -0.14:
            if humidity > 0.0:
                if weirdness > 0.15:
                    return "grove"
                if temperature < -0.32:
                    return "snowy_taiga"
                return "taiga" if humidity > 0.25 else "old_growth_pine_taiga"
            else:
                return "ice_spikes" if weirdness > 0.30 else "snowy_plains"

        # 7. 炎热气候（温度 > 0.28）
        if temperature > 0.16:
            if humidity < -0.08:                 # 干旱炎热
                if weirdness > 0.12:
                    if humidity < -0.32:
                        return "eroded_badlands"
                    return "wooded_badlands" if humidity < -0.20 else "savanna_plateau"
                if humidity < -0.30:
                    return "desert" if weirdness < -0.05 else "badlands"
                if humidity < -0.18:
                    return "savanna"
                return "savanna_plateau" if weirdness > 0.12 else "savanna"
            elif humidity > 0.18:                # 湿润炎热（丛林）
                if humidity > 0.34 and temperature > 0.32:
                    return "bamboo_jungle" if weirdness > 0.08 else "jungle"
                return "sparse_jungle"
            else:                                 # 中等炎热
                return "savanna" if weirdness > -0.12 else "plains"

        # 8. 温带气候（温度 -0.12 至 0.28） —— 按湿度细分
        if humidity > 0.24:                      # 湿润
            if weirdness < -0.06 and temperature > 0.06:
                return "mangrove_swamp" if temperature > 0.16 else "swamp"
            if weirdness > 0.16:
                return "dark_forest"
            if weirdness > 0.08:
                return "flower_forest"
            return "forest" if temperature > 0.06 else "taiga"
        elif humidity > 0.05:                    # 中等湿润
            if weirdness > 0.13:
                return "birch_forest" if temperature > 0.05 else "taiga"
            if weirdness < -0.16 and temperature > 0.12:
                return "swamp"
            return "forest" if temperature > -0.02 else "birch_forest"
        elif humidity > -0.15:                   # 中等干燥
            if weirdness > 0.10:
                return "sunflower_plains"
            return "meadow" if temperature > 0.04 else "plains"
        else:                                     # 干燥
            return "plains"

        # ── 9. 回退（不应到达） ──
        return "plains"

    # ------------------------------------------------------------------
    # 地形高度
    # ------------------------------------------------------------------

    def _raw_surface_height(self, x: int) -> float:
        profile = self.get_profile(self.get_column_biome(x))
        broad = self._noise1(x, 0.0024, 4, 80) * 12
        hills = self._noise1(x, 0.014, 3, 90) * 4.5 * min(profile.amplitude, 1.55)
        mountain_gate = max(0.0, min(1.0, (profile.amplitude - 1.35) / 1.65))
        ridge = abs(self._noise1(x, 0.0065, 2, 95))
        mountain = (ridge ** 1.8) * 18 * mountain_gate
        detail = self._noise1(x, 0.045, 1, 100) * 1.1
        return self.sea_level + profile.elevation_bias + broad + hills + mountain + detail

    @lru_cache(maxsize=8192)
    def get_surface_height(self, x: int) -> int:
        offsets = (-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6)
        weights = (1, 2, 3, 4, 5, 6, 8, 6, 5, 4, 3, 2, 1)
        total = 0.0
        weight_sum = 0
        for offset, weight in zip(offsets, weights):
            total += self._raw_surface_height(x + offset) * weight
            weight_sum += weight
        return max(4, min(245, int(round(total / weight_sum))))

    # ------------------------------------------------------------------
    # 地下方块
    # ------------------------------------------------------------------

    def get_underground_block(self, x: int, y: int, surface_y: int, profile: BiomeProfile, z: int = 0):
        """获取地表以下的方块（按深度分层）。

        分层规则（从地表往下）：
        - depth 0 → 表层方块；寒冷群系的草方块使用 snowed=True 变白
        - depth 1-4 → 亚层方块 (subsurface)
        - depth 5-8 → 填充层（仅砂岩/红砂岩群系）
        - 更深处 → 优先矿脉，无矿脉则放石头变种
        """
        depth = surface_y - y
        # 表层（地表方块）
        if depth == 0:
            # 寒冷群系：使用带积雪的草方块
            if profile.surface == "grass_block" and profile.biome_id in self.COLD_BIOMES:
                return GRASS_BLOCK(snowed=True)
            return self._block(profile.surface)
        # 亚层（地表下 1-4 格）
        if depth <= 4:
            return self._block(profile.subsurface)
        # 砂岩 / 红砂岩的额外填充层（地表下 5-8 格）
        if profile.filler in {"sandstone", "red_sandstone"} and depth <= 8:
            return self._block(profile.filler)

        # 矿石检查
        ore = self.get_ore_block_id(x, y, z)
        if ore:
            return self._block(ore)

        # 默认：石头变种
        stone_variant = self.get_stone_variant(x, y)
        return self._block(stone_variant)

    def get_stone_variant(self, x: int, y: int) -> str:
        """获取石头变种（花岗岩 / 闪长岩 / 安山岩 / 普通石头）。"""
        value = self._noise2(x, y, 0.055, 2, 220)
        if value > 0.52:
            return "granite"
        if value < -0.54:
            return "diorite"
        if self._noise2(x, y, 0.047, 2, 221) > 0.56:
            return "andesite"
        return "stone"

    def get_ore_block_id(self, x: int, y: int, z: int = 0) -> str | None:
        """尝试获取该位置的矿石 block_id。

        使用稳定哈希均匀分布，产生约 1-2% 的矿石覆盖率。
        每个矿石在其 Y 范围内以给定概率独立生成。
        """
        for block_id, chance, min_y, max_y, salt, cell_size, min_radius, max_radius in self.ore_vein_rules:
            if min_y <= y <= max_y and self._is_in_ore_vein(
                x, y, z, chance, salt, cell_size, min_radius, max_radius
            ):
                if z == 0 and self._has_background_ore_at(x, y):
                    continue
                return block_id
        return None

    def _has_background_ore_at(self, x: int, y: int) -> bool:
        for block_id, chance, min_y, max_y, salt, cell_size, min_radius, max_radius in self.ore_vein_rules:
            if min_y <= y <= max_y and self._is_in_ore_vein(
                x, y, 1, chance, salt, cell_size, min_radius, max_radius
            ):
                return True
        return False

    def _is_in_ore_vein(self, x: int, y: int, z: int, chance: float, salt: int,
                        cell_size: int, min_radius: int, max_radius: int) -> bool:
        cell_x = x // cell_size
        cell_y = y // cell_size
        layer_salt = salt + z * 997
        for cx in range(cell_x - 1, cell_x + 2):
            for cy in range(cell_y - 1, cell_y + 2):
                if self._rand01(cx, cy, layer_salt) >= chance:
                    continue
                usable = max(1, cell_size - 3)
                center_x = cx * cell_size + 2 + self._stable_hash(cx, cy, layer_salt + 11) % usable
                center_y = cy * cell_size + 2 + self._stable_hash(cx, cy, layer_salt + 12) % usable
                radius_span = max_radius - min_radius
                radius = min_radius
                if radius_span > 0:
                    radius += self._stable_hash(cx, cy, layer_salt + 13) % (radius_span + 1)
                stretch_x = 1.25 + self._rand01(cx, cy, layer_salt + 14) * 0.9
                stretch_y = 0.75 + self._rand01(cx, cy, layer_salt + 15) * 0.55
                dx = (x - center_x) / stretch_x
                dy = (y - center_y) / stretch_y
                vein_noise = self._noise2(x + z * 31, y, 0.28, 1, layer_salt + 16) * 0.55
                if dx * dx + dy * dy <= (radius + vein_noise) ** 2:
                    return True
        return False

    # ------------------------------------------------------------------
    # 洞穴系统
    # ------------------------------------------------------------------

    def is_cave_air(self, x: int, y: int, z: int, surface_y: int) -> bool:
        """判断指定位置是否为洞穴空气（应放置空气）。

        使用三层噪声混合生成洞穴：
        - large（大洞穴）: 低频 3-octave → 大型开放空间
        - tunnels（隧道）: 中频 2-octave → 连接通道
        - worms（虫洞）: 高频 1-octave → 细小的蜿蜒洞穴

        深度因子：越接近地表越少洞穴。
        """
        if z != 0 or y <= 2 or y >= surface_y - 3:
            return False
        large   = self._noise2(x, y, 0.035, 3, 400)
        tunnels = self._noise2(x, y, 0.09,  2, 410)
        worms   = abs(self._noise2(x, y, 0.022, 1, 420))
        depth_factor = min(1.0, max(0.0, (surface_y - y) / 32))
        return (
            large + tunnels * 0.55 + depth_factor * 0.18 > 0.47
        ) or (
            worms < 0.045 and tunnels > -0.18
        )
