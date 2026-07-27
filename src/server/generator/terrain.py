# Commented and arranged by ChatGPT
"""
地形生成 mixin 模块

提供生物群系判定、地形高度计算、地下方块放置、
矿石分布、石头变种和洞穴系统的生成逻辑。
"""

from functools import lru_cache

from src.server.blocks import *
from src.server.biome import BIOME_PROFILES, BiomeProfile
from src.server.generator.noise import NoiseMixin


class TerrainMixin(NoiseMixin):
    """地形生成 mixin。

    提供生物群系判定、地表高度、地下分层方块、矿石、
    石头变种以及洞穴系统的生成方法。
    需要宿主类提供 ``self.sea_level`` 属性。
    """

    background_surface_offset = 1

    # ---- 生物群系配置表 ----
    biome_profiles = BIOME_PROFILES
    emerald_biomes = frozenset(
        {
            "windswept_hills",
            "windswept_forest",
            "windswept_gravelly_hills",
            "jagged_peaks",
            "frozen_peaks",
            "stony_peaks",
            "snowy_slopes",
            "grove",
            "meadow",
        }
    )

    # ---- 矿石生成规则 ----
    # 每个元组: (block_id, 生成概率, 最小Y, 最大Y, 哈希盐值)
    # 概率表示每个在Y范围内的石头方块生成该矿石的概率
    ore_rules: tuple[tuple[str, float, int, int, int], ...] = (
        ("coal_ore", 0.012, 5, 132, 301),
        ("iron_ore", 0.010, 5, 68, 302),
        ("gold_ore", 0.005, 5, 34, 303),
        ("redstone_ore", 0.006, 5, 20, 304),
        ("lapis_ore", 0.004, 5, 33, 305),
        ("diamond_ore", 0.002, 5, 20, 306),
        ("emerald_ore", 0.001, 5, 33, 307),
    )

    ore_vein_rules: tuple[tuple[str, float, int, int, int, int, int, int], ...] = (
        ("coal_ore", 0.30, 5, 132, 301, 18, 2, 5),
        ("iron_ore", 0.25, 5, 68, 302, 17, 1, 4),
        ("gold_ore", 0.12, 5, 34, 303, 16, 1, 3),
        ("redstone_ore", 0.14, 5, 20, 304, 15, 1, 3),
        ("lapis_ore", 0.12, 5, 33, 305, 15, 1, 2),
        ("diamond_ore", 0.10, 5, 20, 306, 14, 1, 2),
        ("emerald_ore", 0.12, 5, 33, 307, 18, 0, 0),
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
    def _raw_river_candidate(self, x: int) -> bool:
        continentalness = self._noise1(x, 0.00040, 2, 10) * 3.5
        continentalness = max(-1.0, min(1.0, continentalness))
        continentalness *= 1.0 + abs(continentalness) * 1.2
        weirdness = self._noise1(x, 0.00060, 2, 40) * 3.5
        weirdness = max(-1.0, min(1.0, weirdness))
        river_noise = self._noise1(x, 0.00056, 2, 60)
        return (
            continentalness > -0.04
            and abs(river_noise) < 0.003
            and abs(weirdness) < 0.34
        )

    @lru_cache(maxsize=8192)
    def _is_wide_river_column(self, x: int) -> bool:
        if not self._raw_river_candidate(x):
            return False
        left = right = x
        for _ in range(64):
            if not self._raw_river_candidate(left - 1):
                break
            left -= 1
        for _ in range(64):
            if not self._raw_river_candidate(right + 1):
                break
            right += 1

        return right - left + 1 >= 19 and left + 6 <= x <= right - 6

    @lru_cache(maxsize=8192)
    def _get_column_biome_base(self, x: int) -> str:
        """通过五维噪声参数判定指定列的生物群系。

        五维参数：大陆性（continentalness）决定海陆分布，
        温度（temperature）和湿度（humidity）决定气候带，
        奇异度（weirdness）和侵蚀度（erosion）添加地形变化。

        阈值经过平衡，目标分布：~22% 海洋, ~8% 沙滩,
        ~5% 河流, ~10% 山地, ~12% 寒冷, ~12% 炎热,
        ~6% 丛林, ~4% 沼泽, ~14% 森林, ~5% 平原。
        """
        # 降低 octaves 以避免噪声值过度集中在 0 附近

        continentalness = self._noise1(x, 0.0012, 2, 10)
        temperature = self._noise1(x, 0.00145, 2, 20)
        humidity = self._noise1(x, 0.0013, 2, 30)
        weirdness = self._noise1(x, 0.0016, 2, 40)
        erosion = self._noise1(x, 0.00175, 2, 50)

        continentalness = max(-1.0, min(1.0, continentalness * 3.5))
        temperature = max(-1.0, min(1.0, temperature * 3.5))
        humidity = max(-1.0, min(1.0, humidity * 3.5))
        weirdness = max(-1.0, min(1.0, weirdness * 3.5))
        erosion = max(-1.0, min(1.0, erosion * 3.5))
        # 非线性拉伸：让噪声值更均匀地分布在整个 [-1,1] 范围
        continentalness = continentalness * (1.0 + abs(continentalness) * 1.2)
        temperature = temperature * (1.0 + abs(temperature) * 0.6)
        humidity = humidity * (1.0 + abs(humidity) * 0.6)

        # ── 1. 海洋（收紧阈值，避免海洋占据近半世界） ──
        if continentalness < -0.40:
            if continentalness < -0.78:  # 深海
                if temperature < -0.15:
                    return "deep_frozen_ocean"
                if temperature > 0.35:
                    return "deep_lukewarm_ocean"
                return "deep_ocean" if humidity > 0.2 else "deep_cold_ocean"
            else:  # 浅海
                if temperature < -0.10:
                    return "frozen_ocean"
                if temperature > 0.45:
                    return "warm_ocean"
                if temperature > 0.15:
                    return "lukewarm_ocean"
                return "cold_ocean" if humidity < 0.0 else "ocean"

        # ── 2. 沙滩（大陆性 -0.40 至 -0.20） ──
        if continentalness < -0.20:
            if temperature < -0.05:
                return "snowy_beach"
            if erosion < -0.30:
                return "stony_shore"
            return "beach"

        # ── 3. 河流（独立低频河网，跟随当地温度结冰） ──

        if self._is_wide_river_column(x):
            return "frozen_river" if temperature < -0.10 else "river"

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

        if continentalness > 0.25 and humidity > 0.30 and weirdness < -0.15:
            return "lush_caves"
        if continentalness > 0.25 and humidity < -0.30 and weirdness < -0.15:
            return "dripstone_caves"

        # ── 气候带判定 ──

        # 6. 寒冷气候（温度 < -0.12）
        if temperature < -0.14:
            if humidity > 0.0:
                if weirdness > 0.15:
                    return "grove"
                if temperature < -0.32:
                    return "snowy_taiga"
                if humidity > 0.32 and weirdness < -0.08:
                    return "old_growth_spruce_taiga"
                return "taiga" if humidity > 0.25 else "old_growth_pine_taiga"
            else:
                return "ice_spikes" if weirdness > 0.06 else "snowy_plains"

        # 7. 炎热气候（温度 > 0.28）
        if temperature > 0.16:
            if humidity < -0.08:  # 干旱炎热
                if humidity < -0.34:
                    if weirdness > 0.04:
                        return "eroded_badlands"
                    return "badlands" if weirdness > -0.05 else "desert"
                if weirdness > -0.10:
                    return "wooded_badlands" if humidity < -0.12 else "savanna_plateau"
                if humidity < -0.30:
                    return "desert" if weirdness < -0.05 else "badlands"
                if humidity < -0.18:
                    return "savanna"
                return "savanna_plateau" if weirdness > -0.12 else "savanna"
            elif humidity > 0.18:  # 湿润炎热（丛林）
                if humidity > 0.30 and temperature > 0.28:
                    return "bamboo_jungle" if weirdness > 0.02 else "jungle"
                return "sparse_jungle"
            else:  # 中等炎热
                return "savanna" if weirdness > -0.12 else "plains"

        # 8. 温带气候（温度 -0.12 至 0.28） —— 按湿度细分
        if humidity > 0.24:  # 湿润
            if weirdness < -0.05 and temperature > 0.04:
                return "mangrove_swamp" if temperature > 0.12 else "swamp"
            if humidity > 0.34 and weirdness > 0.02:
                return "dark_forest"
            if weirdness > -0.02:
                return "flower_forest"
            return "forest" if temperature > 0.06 else "taiga"
        elif humidity > 0.05:  # 中等湿润
            if weirdness > -0.08 and temperature > -0.02 and humidity > 0.08:
                return "old_growth_birch_forest"
            if weirdness > 0.03:
                return "birch_forest" if temperature > 0.05 else "taiga"
            if weirdness < -0.13 and temperature > 0.10:
                return "swamp"
            return "forest" if temperature > -0.02 else "birch_forest"
        elif humidity > -0.15:  # 中等干燥
            if temperature > 0.08 and humidity > -0.08 and weirdness < -0.10:
                return "mushroom_fields"
            if weirdness > 0.04:
                return "sunflower_plains"
            return "meadow" if temperature > 0.04 else "plains"
        else:  # 干燥
            return "plains"

        # ── 9. 回退（不应到达） ──
        return "plains"

    @lru_cache(maxsize=8192)
    def get_column_biome(self, x: int) -> str:
        biome_id = self._get_column_biome_base(x)

        cell_center = (x // 48) * 48 + 24
        cell_biome = self._get_column_biome_base(cell_center)
        if cell_biome not in {"river", "frozen_river"}:
            biome_id = cell_biome
        if "ocean" in biome_id or biome_id in {"beach", "snowy_beach", "stony_shore"}:
            return biome_id
        alternatives = {
            "stony_peaks": "windswept_hills",
            "frozen_peaks": "snowy_slopes",
            "jagged_peaks": "windswept_gravelly_hills",
            "windswept_hills": "meadow",
            "windswept_forest": "forest",
            "snowy_taiga": "taiga",
            "taiga": "birch_forest",
            "snowy_plains": "plains",
            "plains": "meadow",
            "meadow": "plains",
            "savanna": "plains",
            "savanna_plateau": "savanna",
            "sunflower_plains": "plains",
            "flower_forest": "forest",
            "birch_forest": "forest",
            "old_growth_birch_forest": "birch_forest",
            "dripstone_caves": "plains",
            "lush_caves": "forest",
            "desert": "savanna",
            "badlands": "desert",
            "eroded_badlands": "badlands",
            "dark_forest": "forest",
            "jungle": "sparse_jungle",
            "bamboo_jungle": "jungle",
            "mushroom_fields": "plains",
        }
        alternate = alternatives.get(biome_id)
        region = x // 48
        region_biome = self._get_column_biome_base(region * 48 + 24)
        if alternate and region_biome == biome_id and region % 2:
            return alternate
        return biome_id

    # ------------------------------------------------------------------
    # 地形高度
    # ------------------------------------------------------------------

    def _raw_surface_height(self, x: int) -> float:
        profile = self.get_profile(self.get_column_biome(x))
        broad = self._noise1(x, 0.0024, 4, 80) * 12
        hills = self._noise1(x, 0.014, 3, 90) * 4.5 * min(profile.amplitude, 1.55)
        mountain_gate = max(0.0, min(1.0, (profile.amplitude - 1.35) / 1.65))
        ridge = abs(self._noise1(x, 0.0065, 2, 95))
        mountain = (ridge**1.8) * 18 * mountain_gate
        detail = self._noise1(x, 0.045, 1, 100) * 1.1
        mushroom_hills = 0.0
        if profile.biome_id == "mushroom_fields":
            hill_gate = max(0.0, self._noise1(x, 0.0065, 2, 96))
            mushroom_hills = (hill_gate**1.45) * 24
        raw_height = (
            self.sea_level
            + profile.elevation_bias
            + broad
            + hills
            + mountain
            + mushroom_hills
            + detail
        )
        if profile.biome_id in {"river", "frozen_river"} or self._raw_river_candidate(
            x
        ):
            raw_height = min(raw_height, self.sea_level - 16)
        return raw_height

    @lru_cache(maxsize=8192)
    def get_surface_height(self, x: int) -> int:
        offsets = (-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6)
        weights = (1, 2, 3, 4, 5, 6, 8, 6, 5, 4, 3, 2, 1)
        total = 0.0
        weight_sum = 0
        for offset, weight in zip(offsets, weights):
            total += self._raw_surface_height(x + offset) * weight
            weight_sum += weight
        height = max(4, min(245, int(round(total / weight_sum))))
        if self.get_column_biome(x) == "mushroom_fields":
            cell = x // 32
            center = cell * 32 + 8 + self._stable_hash(cell, 991) % 16
            distance = abs(x - center)
            if distance <= 12:
                edge = 12
                for step in range(1, 13):
                    if (
                        self.get_column_biome(x - step) != "mushroom_fields"
                        or self.get_column_biome(x + step) != "mushroom_fields"
                    ):
                        edge = step
                        break
                edge_factor = min(1.0, edge / 8.0)
                height += int(max(0, (12 - distance) * 1.15) * edge_factor)
                if distance <= 3:
                    height += int(4 * edge_factor)
            height = min(245, height)
        return height

    @lru_cache(maxsize=8192)
    def get_layer_surface_height(self, x: int, z: int) -> int:
        surface_y = self.get_surface_height(x)
        if z == 1:
            offset = max(0, int(getattr(self, "background_surface_offset", 0)))
            return max(surface_y, min(245, surface_y + offset))
        return surface_y

    # ------------------------------------------------------------------
    # 地下方块
    # ------------------------------------------------------------------

    def get_underground_block(
        self, x: int, y: int, surface_y: int, profile: BiomeProfile, z: int = 0
    ):
        """获取地表以下的方块（按深度分层）。

        分层规则（从地表往下）：
        - depth 0 → 表层方块；寒冷群系的草方块使用 snowed=True 变白
        - depth 1-4 → 亚层方块 (subsurface)
        - depth 5-8 → 填充层（仅砂岩/红砂岩群系）
        - 更深处 → 优先矿脉，无矿脉则放石头变种
        """
        depth = surface_y - y

        if 2 <= y <= 7 and self._is_in_lava_vein(x, y, z):
            return LAVA()
        # 表层（地表方块）
        if depth == 0:
            if profile.biome_id == "mushroom_fields" and surface_y <= self.sea_level:
                if self._rand01(x, surface_y, 955 + z * 17) < 0.22:
                    return GRASS_BLOCK()
                return SAND()
            if surface_y < self.sea_level and profile.surface == "grass_block":
                return DIRT()
            # 寒冷群系：使用带积雪的草方块
            if profile.surface == "grass_block" and profile.is_cold:
                return GRASS_BLOCK(snowed=True)
            return self._block(profile.surface)
        if z == 0 and 1 <= depth <= 8 and self._is_exposed_ore_outcrop(x, y, surface_y):
            exposed_ore = self.get_ore_block_id(x, y, z)
            if exposed_ore and self._rand01(x, y, 965) < 0.72:
                return self._block(exposed_ore)
        # 亚层（地表下 1-4 格）
        if depth <= 4:
            return self._block(profile.subsurface)
        # 砂岩 / 红砂岩的额外填充层（地表下 5-8 格）
        if profile.filler in {"sandstone", "red_sandstone"} and depth <= 8:
            return self._block(profile.filler)

        if 2 <= y <= 12 and self._is_in_lava_vein(x, y, z):
            return LAVA()

        # 矿石检查
        ore = self.get_ore_block_id(x, y, z)
        if ore:
            return self._block(ore)

        # 默认：石头变种
        stone_variant = self.get_stone_variant(x, y)
        return self._block(stone_variant)

    def _is_exposed_ore_outcrop(self, x: int, y: int, surface_y: int) -> bool:
        for nx in (x - 1, x + 1):
            neighbour_surface = self.get_surface_height(nx)
            if y >= neighbour_surface:
                return True
            if self.is_cave_air(nx, y, 0, neighbour_surface):
                return True
        if self.is_cave_air(x, y + 1, 0, surface_y):
            return True
        return False

    def _is_in_lava_vein(self, x: int, y: int, z: int = 0) -> bool:
        cell_size = 13
        cell_x, cell_y = x // cell_size, y // cell_size
        for cx in range(cell_x - 1, cell_x + 2):
            for cy in range(cell_y - 1, cell_y + 2):
                salt = 960 + z * 997
                chance = 0.98 if y <= 7 else 0.38
                if self._rand01(cx, cy, salt) >= chance:
                    continue
                center_x = cx * cell_size + 2 + self._stable_hash(cx, cy, salt + 1) % 8
                center_y = cy * cell_size + 2 + self._stable_hash(cx, cy, salt + 2) % 7
                dx = x - center_x
                dy = y - center_y

                radius = 1 + self._stable_hash(cx, cy, salt + 3) % 3
                if abs(dy) == 0 and abs(dx) <= radius:
                    return True
                if (
                    abs(dy) == 1
                    and abs(dx) <= max(1, radius - 1)
                    and self._stable_hash(cx, cy, salt + 4) % 4 == 0
                ):
                    return True
        return False

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
        biome_id = self.get_column_biome(x)
        for (
            block_id,
            chance,
            min_y,
            max_y,
            salt,
            cell_size,
            min_radius,
            max_radius,
        ) in self.ore_vein_rules:
            if block_id == "emerald_ore" and biome_id not in self.emerald_biomes:
                continue
            weighted_chance = chance * self._ore_height_weight(
                block_id, y, min_y, max_y
            )
            if min_y <= y <= max_y and self._is_in_ore_vein(
                x, y, z, weighted_chance, salt, cell_size, min_radius, max_radius
            ):
                if z == 0 and self._has_background_ore_at(x, y):
                    continue
                return block_id
        return None

    def _has_background_ore_at(self, x: int, y: int) -> bool:
        biome_id = self.get_column_biome(x)
        for (
            block_id,
            chance,
            min_y,
            max_y,
            salt,
            cell_size,
            min_radius,
            max_radius,
        ) in self.ore_vein_rules:
            if block_id == "emerald_ore" and biome_id not in self.emerald_biomes:
                continue
            weighted_chance = chance * self._ore_height_weight(
                block_id, y, min_y, max_y
            )
            if min_y <= y <= max_y and self._is_in_ore_vein(
                x, y, 1, weighted_chance, salt, cell_size, min_radius, max_radius
            ):
                return True
        return False

    def _ore_height_weight(
        self, block_id: str, y: int, min_y: int, max_y: int
    ) -> float:
        if not min_y <= y <= max_y:
            return 0.0
        if block_id == "lapis_ore":
            peak = 16
            span = max(1, max(peak - min_y, max_y - peak))
            return max(0.18, 1.0 - abs(y - peak) / span)
        return 1.0

    def _is_in_ore_vein(
        self,
        x: int,
        y: int,
        z: int,
        chance: float,
        salt: int,
        cell_size: int,
        min_radius: int,
        max_radius: int,
    ) -> bool:
        cell_x = x // cell_size
        cell_y = y // cell_size
        layer_salt = salt + z * 997
        for cx in range(cell_x - 1, cell_x + 2):
            for cy in range(cell_y - 1, cell_y + 2):
                if self._rand01(cx, cy, layer_salt) >= chance:
                    continue
                usable = max(1, cell_size - 3)
                center_x = (
                    cx * cell_size
                    + 2
                    + self._stable_hash(cx, cy, layer_salt + 11) % usable
                )
                center_y = (
                    cy * cell_size
                    + 2
                    + self._stable_hash(cx, cy, layer_salt + 12) % usable
                )
                radius_span = max_radius - min_radius
                radius = min_radius
                if radius_span > 0:
                    radius += self._stable_hash(cx, cy, layer_salt + 13) % (
                        radius_span + 1
                    )
                dx, dy = abs(x - center_x), abs(y - center_y)
                pattern = self._stable_hash(cx, cy, layer_salt + 14) % 10

                if pattern < 7 and dy == 0 and dx <= radius:
                    return True
                if 7 <= pattern < 9 and dx <= radius and dy == (1 if dx % 2 else 0):
                    return True
                if pattern == 9 and dx * dx + dy * dy <= max(1, radius):
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
        large = self._noise2(x, y, 0.035, 3, 400)
        tunnels = self._noise2(x, y, 0.09, 2, 410)
        worms = abs(self._noise2(x, y, 0.022, 1, 420))
        depth_factor = min(1.0, max(0.0, (surface_y - y) / 32))
        return (large + tunnels * 0.55 + depth_factor * 0.18 > 0.47) or (
            worms < 0.045 and tunnels > -0.18
        )
