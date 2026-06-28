import json
import math
from abc import ABC
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import noise

import resources.server.biome as biome
from resources.server.blocks import *


WORLDGEN_DIR = Path(__file__).resolve().parents[2] / "data" / "minecraft" / "worldgen"


class Generator(ABC):
    def __init__(self, seed):
        self.seed = int(seed)

    def get_original_block(self, x, y, z):
        return AIR()

    def get_original_biome(self, x, y):
        return biome.Void.biome_id


@dataclass(frozen=True)
class TreeConfig:
    trunk: str
    leaves: str
    base_height: int
    height_rand_a: int
    height_rand_b: int
    radius: int
    shape: str = "blob"


@dataclass(frozen=True)
class BiomeProfile:
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


class MinecraftLike2D(Generator):
    sea_level = 68
    stone_level = 52
    max_tree_lookup = 9

    default_tree_configs = {
        "oak": TreeConfig("oak_log", "oak_leaves", 4, 2, 0, 2, "blob"),
        "birch": TreeConfig("birch_log", "birch_leaves", 5, 2, 0, 2, "blob"),
        "spruce": TreeConfig("spruce_log", "spruce_leaves", 5, 2, 1, 3, "spruce"),
        "jungle_tree": TreeConfig("jungle_log", "jungle_leaves", 6, 5, 0, 2, "blob"),
        "acacia": TreeConfig("acacia_log", "acacia_leaves", 5, 2, 2, 2, "flat"),
        "dark_oak": TreeConfig("dark_oak_log", "dark_oak_leaves", 5, 2, 0, 3, "blob"),
    }

    biome_profiles = {
        "plains": BiomeProfile("plains", "grass_block", "dirt", "stone", "oak", 0.018, 0.28, 0.035, 0.0, 0.002, 0.0, 0.018, 0, 1.0),
        "sunflower_plains": BiomeProfile("sunflower_plains", "grass_block", "dirt", "stone", "oak", 0.018, 0.32, 0.08, 0.0, 0.002, 0.0, 0.018, 0, 1.0),
        "forest": BiomeProfile("forest", "grass_block", "dirt", "stone", "oak", 0.095, 0.34, 0.035, 0.02, 0.018, 0.0, 0.01, 2, 1.05),
        "birch_forest": BiomeProfile("birch_forest", "grass_block", "dirt", "stone", "birch", 0.08, 0.30, 0.03, 0.015, 0.01, 0.0, 0.01, 2, 1.0),
        "old_growth_birch_forest": BiomeProfile("old_growth_birch_forest", "grass_block", "dirt", "stone", "birch", 0.11, 0.28, 0.025, 0.02, 0.014, 0.0, 0.008, 3, 1.05),
        "dark_forest": BiomeProfile("dark_forest", "grass_block", "dirt", "stone", "dark_oak", 0.13, 0.22, 0.02, 0.025, 0.035, 0.0, 0.005, 1, 1.0),
        "taiga": BiomeProfile("taiga", "grass_block", "dirt", "stone", "spruce", 0.075, 0.22, 0.01, 0.13, 0.016, 0.0, 0.004, 3, 1.05),
        "snowy_taiga": BiomeProfile("snowy_taiga", "snow", "dirt", "stone", "spruce", 0.07, 0.12, 0.0, 0.08, 0.004, 0.0, 0.0, 4, 1.05),
        "snowy_plains": BiomeProfile("snowy_plains", "snow", "dirt", "stone", None, 0.0, 0.08, 0.0, 0.0, 0.0, 0.0, 0.0, 2, 0.95),
        "desert": BiomeProfile("desert", "sand", "sand", "sandstone", None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.035, 0.0, -2, 0.78),
        "savanna": BiomeProfile("savanna", "grass_block", "dirt", "stone", "acacia", 0.04, 0.18, 0.01, 0.0, 0.0, 0.0, 0.006, 1, 1.2),
        "windswept_savanna": BiomeProfile("windswept_savanna", "grass_block", "coarse_dirt", "stone", "acacia", 0.035, 0.12, 0.005, 0.0, 0.0, 0.0, 0.002, 8, 1.8),
        "jungle": BiomeProfile("jungle", "grass_block", "dirt", "stone", "jungle_tree", 0.12, 0.42, 0.02, 0.18, 0.012, 0.0, 0.035, 1, 1.05),
        "sparse_jungle": BiomeProfile("sparse_jungle", "grass_block", "dirt", "stone", "jungle_tree", 0.045, 0.38, 0.018, 0.12, 0.008, 0.0, 0.03, 0, 1.0),
        "badlands": BiomeProfile("badlands", "red_sand", "hardened_clay", "red_sandstone", None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.018, 0.0, 5, 1.35),
        "wooded_badlands": BiomeProfile("wooded_badlands", "red_sand", "hardened_clay", "red_sandstone", "oak", 0.025, 0.05, 0.0, 0.0, 0.0, 0.01, 0.0, 7, 1.45),
        "swamp": BiomeProfile("swamp", "grass_block", "dirt", "stone", "oak", 0.045, 0.35, 0.015, 0.0, 0.035, 0.0, 0.06, -4, 0.62),
        "beach": BiomeProfile("beach", "sand", "sand", "sandstone", None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.025, -2, 0.55),
        "ocean": BiomeProfile("ocean", "sand", "sand", "stone", None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -13, 0.45),
        "deep_ocean": BiomeProfile("deep_ocean", "gravel", "sand", "stone", None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -24, 0.4),
        "frozen_ocean": BiomeProfile("frozen_ocean", "gravel", "sand", "stone", None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -15, 0.4),
        "mountains": BiomeProfile("windswept_hills", "grass_block", "dirt", "stone", "spruce", 0.026, 0.08, 0.0, 0.04, 0.0, 0.0, 0.0, 17, 2.1),
    }

    ore_rules: tuple[tuple[str, float, int, int, int], ...] = (
        ("coal_ore", 0.078, 34, 128, 301),
        ("iron_ore", 0.052, 8, 88, 302),
        ("gold_ore", 0.018, 4, 42, 303),
        ("redstone_ore", 0.019, 4, 28, 304),
        ("lapis_ore", 0.014, 10, 40, 305),
        ("diamond_ore", 0.010, 3, 22, 306),
        ("emerald_ore", 0.006, 18, 80, 307),
    )

    def __init__(self, seed):
        super().__init__(seed)
        self.tree_configs = self._load_tree_configs()
        self.block_factories = self._build_block_factories()

    def _build_block_factories(self) -> dict[str, Callable[[], Block]]:
        factories = {}
        for cls in Block.__subclasses__():
            self._collect_block_factory(cls, factories)
        return factories

    def _collect_block_factory(self, cls, factories):
        block_id = getattr(cls, "block_id", None)
        if block_id:
            factories[block_id] = cls
        for subclass in cls.__subclasses__():
            self._collect_block_factory(subclass, factories)

    def _block(self, block_id: str):
        cls = self.block_factories.get(block_id)
        if cls is None:
            return STONE()
        return cls()

    def _load_tree_configs(self):
        configs = dict(self.default_tree_configs)
        configured_feature_dir = WORLDGEN_DIR / "configured_feature"
        for name, fallback in self.default_tree_configs.items():
            path = configured_feature_dir / f"{name}.json"
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            config = data.get("config", {})
            trunk = self._minecraft_name_to_block_id(
                config.get("trunk_provider", {}).get("state", {}).get("Name"),
                fallback.trunk,
            )
            leaves = self._minecraft_name_to_block_id(
                config.get("foliage_provider", {}).get("state", {}).get("Name"),
                fallback.leaves,
            )
            trunk_placer = config.get("trunk_placer", {})
            foliage_placer = config.get("foliage_placer", {})
            configs[name] = TreeConfig(
                trunk=trunk,
                leaves=leaves,
                base_height=int(trunk_placer.get("base_height", fallback.base_height)),
                height_rand_a=int(trunk_placer.get("height_rand_a", fallback.height_rand_a)),
                height_rand_b=int(trunk_placer.get("height_rand_b", fallback.height_rand_b)),
                radius=self._read_int_provider(foliage_placer.get("radius", fallback.radius)),
                shape=fallback.shape,
            )
        return configs

    def _read_int_provider(self, value) -> int:
        if isinstance(value, int):
            return value
        if isinstance(value, dict):
            nested = value.get("value", value)
            if isinstance(nested, dict):
                return int(nested.get("max_inclusive", nested.get("min_inclusive", 2)))
        return 2

    def _minecraft_name_to_block_id(self, name, fallback):
        if not name:
            return fallback
        return str(name).split(":", 1)[-1]

    def get_original_biome(self, x, y):
        return self.get_profile(self.get_column_biome(x)).biome_id

    def get_original_block(self, x, y, z):
        if y <= 0:
            return BEDROCK()
        if y >= 255:
            return AIR()

        column_biome = self.get_column_biome(x)
        profile = self.get_profile(column_biome)
        surface_y = self.get_surface_height(x)

        structure_block = self.get_structure_block(x, y, z, surface_y, profile)
        if structure_block is not None:
            return structure_block

        if y > surface_y:
            if y <= self.sea_level and z == 0:
                if column_biome in {"frozen_ocean", "deep_frozen_ocean"} and y == self.sea_level:
                    return ICE()
                return WATER()
            return AIR()

        if self.is_cave_air(x, y, z, surface_y):
            return AIR() if z == 0 else self.get_underground_block(x, y, surface_y, profile)

        return self.get_underground_block(x, y, surface_y, profile)

    def get_profile(self, biome_id: str) -> BiomeProfile:
        if biome_id in self.biome_profiles:
            return self.biome_profiles[biome_id]
        return self.biome_profiles.get(biome_id.replace("old_growth_", ""), self.biome_profiles["plains"])

    def get_column_biome(self, x: int) -> str:
        continentalness = self._noise1(x, 0.0025, 4, 10)
        temperature = self._noise1(x, 0.0032, 3, 20)
        humidity = self._noise1(x, 0.0030, 3, 30)
        weirdness = self._noise1(x, 0.0042, 2, 40)
        erosion = self._noise1(x, 0.005, 2, 50)

        if continentalness < -0.58:
            return "deep_ocean" if continentalness < -0.78 else ("frozen_ocean" if temperature < -0.45 else "ocean")
        if continentalness < -0.43:
            return "beach"
        if weirdness > 0.68 and continentalness > 0.08:
            return "mountains"
        if temperature < -0.48:
            return "snowy_taiga" if humidity > -0.2 else "snowy_plains"
        if temperature > 0.55 and humidity < -0.35:
            return "badlands" if weirdness > 0.35 else "desert"
        if temperature > 0.45 and humidity < 0.05:
            return "windswept_savanna" if erosion < -0.45 else "savanna"
        if temperature > 0.35 and humidity > 0.45:
            return "jungle" if humidity > 0.62 else "sparse_jungle"
        if humidity > 0.55 and continentalness < 0.15:
            return "swamp"
        if humidity > 0.28:
            if weirdness > 0.42:
                return "dark_forest"
            return "birch_forest" if temperature > 0.12 else "taiga"
        if weirdness > 0.58:
            return "sunflower_plains"
        return "forest" if humidity > 0.0 else "plains"

    def get_surface_height(self, x: int) -> int:
        profile = self.get_profile(self.get_column_biome(x))
        broad = self._noise1(x, 0.004, 5, 80) * 10
        hills = self._noise1(x, 0.018, 4, 90) * 6 * profile.amplitude
        detail = self._noise1(x, 0.065, 2, 100) * 2
        height = self.sea_level + profile.elevation_bias + broad + hills + detail
        return max(8, min(230, int(round(height))))

    def get_underground_block(self, x: int, y: int, surface_y: int, profile: BiomeProfile):
        depth = surface_y - y
        if depth == 0:
            return self._block(profile.surface)
        if depth <= 4:
            return self._block(profile.subsurface)
        if profile.filler in {"sandstone", "red_sandstone"} and depth <= 8:
            return self._block(profile.filler)

        ore = self.get_ore_block_id(x, y)
        if ore:
            return self._block(ore)

        stone_variant = self.get_stone_variant(x, y)
        return self._block(stone_variant)

    def get_stone_variant(self, x: int, y: int) -> str:
        value = self._noise2(x, y, 0.055, 2, 220)
        if value > 0.52:
            return "granite"
        if value < -0.54:
            return "diorite"
        if self._noise2(x, y, 0.047, 2, 221) > 0.56:
            return "andesite"
        return "stone"

    def get_ore_block_id(self, x: int, y: int) -> str | None:
        for block_id, threshold, min_y, max_y, salt in self.ore_rules:
            if min_y <= y <= max_y:
                richness = self._noise2(x, y, 0.087, 2, salt)
                pocket = self._noise2(x, y, 0.22, 1, salt + 90)
                if richness > 1.0 - threshold * 6 and pocket > 0.08:
                    return block_id
        return None

    def is_cave_air(self, x: int, y: int, z: int, surface_y: int) -> bool:
        if z != 0 or y <= 2 or y >= surface_y - 3:
            return False
        large = self._noise2(x, y, 0.035, 3, 400)
        tunnels = self._noise2(x, y, 0.09, 2, 410)
        worms = abs(self._noise2(x, y, 0.022, 1, 420))
        depth_factor = min(1.0, max(0.0, (surface_y - y) / 32))
        return (large + tunnels * 0.55 + depth_factor * 0.18 > 0.47) or (worms < 0.045 and tunnels > -0.18)

    def get_structure_block(self, x: int, y: int, z: int, surface_y: int, profile: BiomeProfile):
        if z != 0:
            return None

        tree_block = self.get_tree_block(x, y, surface_y, profile)
        if tree_block is not None:
            return tree_block

        if y != surface_y + 1:
            return None
        if surface_y < self.sea_level - 1:
            return None

        chance = self._rand01(x, 0, 700)
        local = self._noise1(x, 0.18, 1, 710)

        if profile.cactus_chance and chance < profile.cactus_chance:
            return CACTUS()
        if profile.sugar_cane_chance and self.is_near_water(x, surface_y) and chance < profile.sugar_cane_chance:
            return SUGAR_CANE()
        if profile.fern_chance and chance < profile.fern_chance and local > -0.4:
            return FERN()
        if profile.mushroom_chance and chance < profile.mushroom_chance and local < 0.15:
            return BROWN_MUSHROOM() if self._rand01(x, 0, 711) < 0.55 else RED_MUSHROOM()
        if profile.flower_chance and chance < profile.flower_chance and local > 0.2:
            return POPPY() if self._rand01(x, 0, 712) < 0.5 else DANDELION()
        if profile.grass_chance and chance < profile.grass_chance:
            return SHORT_GRASS()

        return None

    def get_tree_block(self, x: int, y: int, surface_y: int, profile: BiomeProfile):
        if profile.tree is None:
            return None
        for trunk_x in range(x - self.max_tree_lookup, x + self.max_tree_lookup + 1):
            trunk_surface = self.get_surface_height(trunk_x)
            if trunk_surface < self.sea_level - 1:
                continue
            trunk_profile = self.get_profile(self.get_column_biome(trunk_x))
            if trunk_profile.tree != profile.tree:
                continue
            if not self.has_tree_at(trunk_x, trunk_surface, trunk_profile):
                continue
            block_id = self.tree_block_at(profile.tree, trunk_x, trunk_surface, x, y)
            if block_id:
                return self._block(block_id)
        return None

    def has_tree_at(self, x: int, surface_y: int, profile: BiomeProfile) -> bool:
        if surface_y < self.sea_level - 1:
            return False
        spacing = 5 if profile.tree_chance > 0.07 else 7
        if self._stable_hash(x // spacing, 810) % spacing != x % spacing:
            return False
        density = self._noise1(x, 0.035, 2, 811)
        return self._rand01(x, surface_y, 812) < profile.tree_chance * (1.25 + density)

    def tree_block_at(self, tree_name: str, trunk_x: int, ground_y: int, x: int, y: int) -> str | None:
        config = self.tree_configs[tree_name]
        height = config.base_height
        if config.height_rand_a > 0:
            height += self._stable_hash(trunk_x, 820) % (config.height_rand_a + 1)
        if config.height_rand_b > 0:
            height += self._stable_hash(trunk_x, 821) % (config.height_rand_b + 1)

        dx = x - trunk_x
        dy = y - ground_y
        if dx == 0 and 1 <= dy <= height:
            return config.trunk

        top = height + 1
        if config.shape == "spruce":
            leaf_start = max(2, height - 4)
            if leaf_start <= dy <= top:
                layer_radius = max(1, min(config.radius, (top - dy) // 2 + 1))
                if abs(dx) <= layer_radius and not (abs(dx) == layer_radius and dy == top):
                    return config.leaves
        elif config.shape == "flat":
            if height - 1 <= dy <= height + 2:
                layer_radius = config.radius + (1 if dy in {height, height + 1} else 0)
                if abs(dx) <= layer_radius:
                    return config.leaves
        else:
            center_y = height + 1
            dist = abs(dx) + abs(y - (ground_y + center_y)) * 0.75
            if dist <= config.radius + 1.1 and dy >= height - 2:
                return config.leaves
        return None

    def is_near_water(self, x: int, surface_y: int) -> bool:
        for nx in range(x - 2, x + 3):
            if self.get_surface_height(nx) < self.sea_level:
                return True
        return surface_y <= self.sea_level + 1

    def _noise1(self, x: int, scale: float, octaves: int, salt: int) -> float:
        return noise.pnoise1(
            (x + self.seed * 17) * scale,
            octaves=octaves,
            persistence=0.5,
            lacunarity=2.0,
            repeat=1048576,
            base=self.seed + salt,
        )

    def _noise2(self, x: int, y: int, scale: float, octaves: int, salt: int) -> float:
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
        return self._stable_hash(x, y, salt) / 0xFFFFFFFF

    def _stable_hash(self, x: int, y: int = 0, salt: int = 0) -> int:
        value = (x * 374761393 + y * 668265263 + (self.seed + salt) * 1442695041) & 0xFFFFFFFF
        value = (value ^ (value >> 13)) * 1274126177 & 0xFFFFFFFF
        return value ^ (value >> 16)


class ClassicFlat(Generator):
    def get_original_biome(self, x, y):
        return biome.PLAIN.biome_id

    def get_original_block(self, x, y, z):
        if 60 < y < 70:
            return DIRT()
        elif y == 70:
            return GRASS_BLOCK()
        elif y == 0:
            return BEDROCK()
        elif y <= 60:
            return STONE()
        elif y == 71:
            veg_patch = noise.pnoise2(
                x * 0.02, z * 0.02,
                octaves=2, persistence=0.5, lacunarity=2.0,
                base=self.seed
            )
            if veg_patch > -0.15:
                grass_detail1 = noise.pnoise2(x * 0.25, z * 0.25, base=self.seed + 10)
                grass_detail2 = noise.pnoise2(x * 0.4, z * 0.4, base=self.seed + 11)
                if (grass_detail1 + grass_detail2) / 2 > -0.3:
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
                        if noise.pnoise2(x * 0.7, z * 0.7, base=self.seed + 200) > 0:
                            return POPPY()
                        else:
                            return DANDELION()
                    else:
                        return SHORT_GRASS()

            return AIR()

        else:
            return AIR()


class bedrock_flat_generator(Generator):
    def get_original_block(self, x, y, z):
        return BEDROCK() if y == 0 else AIR()
