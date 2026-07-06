"""Surface decoration generation for the Minecraft-like 2D generator."""

import json
from typing import Callable

from resources.server.blocks import *
from resources.server.generator.config import BiomeProfile, TreeConfig, WORLDGEN_DIR
from resources.server.generator.noise import NoiseMixin


class DecorationMixin(NoiseMixin):
    """Trees, leaf caps, plants, mushrooms, cacti and sugar cane."""

    default_tree_configs = {
        "oak": TreeConfig("oak_log", "oak_leaves", 4, 2, 0, 2, "oak"),
        "birch": TreeConfig("birch_log", "birch_leaves", 5, 2, 0, 2, "birch"),
        "spruce": TreeConfig("spruce_log", "spruce_leaves", 6, 3, 1, 2, "spruce"),
        "jungle_tree": TreeConfig("jungle_log", "jungle_leaves", 7, 5, 0, 3, "jungle"),
        "acacia": TreeConfig("acacia_log", "acacia_leaves", 5, 2, 1, 2, "acacia"),
        "dark_oak": TreeConfig("dark_oak_log", "dark_oak_leaves", 5, 2, 0, 3, "dark_oak"),
    }

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
        return cls() if cls is not None else STONE()

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

    def _is_cold_biome(self, biome_id: str) -> bool:
        return biome_id in {
            "snowy_plains", "snowy_taiga", "ice_spikes", "frozen_peaks",
            "jagged_peaks", "snowy_slopes", "grove", "snowy_beach",
            "frozen_river",
        }

    def _is_arid_biome(self, biome_id: str) -> bool:
        return biome_id in {"desert", "badlands", "eroded_badlands", "wooded_badlands"}

    def get_structure_block(self, x: int, y: int, z: int, surface_y: int,
                            profile: BiomeProfile):
        if z == 1:
            return self.get_tree_block(x, y, surface_y, profile)

        cap_block = self.get_leaf_cap_block(x, y, surface_y, profile)
        if cap_block is not None:
            return cap_block

        if y != surface_y + 1 or surface_y < self.sea_level:
            return None

        if self._is_cold_biome(profile.biome_id):
            if profile.surface not in {"snow_block", "ice", "water"}:
                snow_extra = int(self._noise1(x, 0.15, 1, 850) * 3 + 1)
                return SNOW(layer=max(1, min(4, snow_extra)))
            return None

        local = self._noise1(x, 0.18, 1, 710)

        if profile.cactus_chance and self._rand01(x, surface_y, 700) < profile.cactus_chance:
            return CACTUS()

        if (self._is_arid_biome(profile.biome_id)
                and self._rand01(x, surface_y, 701) < 0.07
                and local > -0.25):
            return DEAD_BUSH()

        if (profile.sugar_cane_chance
                and self.is_near_water(x, surface_y)
                and self._rand01(x, surface_y, 702) < profile.sugar_cane_chance * 2.0):
            return SUGAR_CANE()

        if (profile.fern_chance
                and self._rand01(x, surface_y, 703) < profile.fern_chance
                and local > -0.45):
            return FERN()

        mushroom_boost = 1.8 if profile.biome_id in {"dark_forest", "swamp"} else 1.0
        if (profile.mushroom_chance
                and self._rand01(x, surface_y, 704) < profile.mushroom_chance * mushroom_boost
                and local < 0.22):
            return BROWN_MUSHROOM() if self._rand01(x, surface_y, 711) < 0.55 else RED_MUSHROOM()

        if (profile.flower_chance
                and self._rand01(x, surface_y, 705) < profile.flower_chance
                and local > 0.02):
            return self._flower_for_biome(profile.biome_id, x, surface_y)

        if profile.grass_chance and self._rand01(x, surface_y, 706) < profile.grass_chance:
            if self._rand01(x, surface_y, 707) < 0.14 and profile.fern_chance > 0:
                return FERN()
            return SHORT_GRASS()

        return None

    def _flower_for_biome(self, biome_id: str, x: int, y: int):
        roll = self._rand01(x, y, 712)
        if biome_id == "swamp":
            return BLUE_ORCHID()
        if biome_id in {"flower_forest", "meadow", "sunflower_plains"}:
            if roll < 0.22:
                return ALLIUM()
            if roll < 0.44:
                return AZURE_BLUET()
            if roll < 0.66:
                return OXEYE_DAISY()
            if roll < 0.83:
                return POPPY()
            return DANDELION()
        return POPPY() if roll < 0.48 else DANDELION()

    def get_tree_block(self, x: int, y: int, surface_y: int,
                       profile: BiomeProfile):
        for trunk_x in range(x - self.max_tree_lookup, x + self.max_tree_lookup + 1):
            tree = self._tree_at_column(trunk_x)
            if tree is None:
                continue
            tree_name, trunk_surface = tree
            config = self.tree_configs[tree_name]
            height = self._tree_height(config, trunk_x)
            dx = x - trunk_x
            dy = y - trunk_surface
            if dx == 0 and 1 <= dy <= height:
                return self._block(config.trunk)

        for trunk_x in range(x - self.max_tree_lookup, x + self.max_tree_lookup + 1):
            tree = self._tree_at_column(trunk_x)
            if tree is None:
                continue
            tree_name, trunk_surface = tree
            block_id = self.tree_block_at(tree_name, trunk_x, trunk_surface, x, y)
            if block_id and block_id != self.tree_configs[tree_name].trunk:
                return self._block(block_id)
        return None

    def get_leaf_cap_block(self, x: int, y: int, surface_y: int,
                           profile: BiomeProfile):
        for trunk_x in range(x - self.max_tree_lookup, x + self.max_tree_lookup + 1):
            tree = self._tree_at_column(trunk_x)
            if tree is None:
                continue
            tree_name, trunk_surface = tree
            config = self.tree_configs[tree_name]
            height = self._tree_height(config, trunk_x)
            radius = self._foreground_leaf_radius(config, height, y - trunk_surface)
            if radius is not None and abs(x - trunk_x) <= radius:
                return self._block(config.leaves)
        return None

    def _tree_at_column(self, x: int):
        cache = getattr(self, "_tree_column_cache", None)
        if cache is not None and x in cache:
            return cache[x]

        surface_y = self.get_surface_height(x)
        profile = self.get_profile(self.get_column_biome(x))
        result = None
        if profile.tree is not None and self.has_tree_at(x, surface_y, profile):
            result = (profile.tree, surface_y)

        if cache is not None:
            cache[x] = result
        return result

    def has_tree_at(self, x: int, surface_y: int, profile: BiomeProfile) -> bool:
        cache = getattr(self, "_tree_presence_cache", None)
        key = (x, surface_y, profile.biome_id)
        if cache is not None and key in cache:
            return cache[key]

        result = self._compute_has_tree_at(x, surface_y, profile)
        if cache is not None:
            cache[key] = result
        return result

    def _compute_has_tree_at(self, x: int, surface_y: int, profile: BiomeProfile) -> bool:
        if surface_y < self.sea_level - 1 or profile.tree_chance <= 0:
            return False

        spacing = self._tree_spacing(profile)
        cell = x // spacing
        if self._tree_candidate_x(cell, spacing) != x:
            return False

        config = self.tree_configs.get(profile.tree)
        min_gap = max(6, (config.radius * 2 + 2) if config else spacing - 1)
        for neighbor_cell in (cell - 1, cell + 1):
            neighbor_x = self._tree_candidate_x(neighbor_cell, spacing)
            if abs(neighbor_x - x) < min_gap:
                return False

        nearby = [self.get_surface_height(nx) for nx in range(x - 3, x + 4)]
        if max(nearby) - min(nearby) > 2:
            return False

        density = (self._noise1(x, 0.026, 2, 811) + 1.0) * 0.5
        effective = profile.tree_chance * spacing * (0.55 + density * 0.65)
        effective = max(0.02, min(0.68, effective))
        if self._rand01(cell, surface_y // 4, 812) >= effective:
            return False

        priority = self._stable_hash(x, surface_y, 817)
        for nx in range(x - min_gap + 1, x + min_gap):
            if nx == x:
                continue
            competing = self._tree_candidate_without_gap(nx)
            if competing is None:
                continue
            competing_profile, competing_surface = competing
            competing_config = self.tree_configs.get(competing_profile.tree)
            competing_gap = max(
                min_gap,
                (competing_config.radius * 2 + 2) if competing_config else min_gap,
            )
            if abs(nx - x) < competing_gap and self._stable_hash(nx, competing_surface, 817) < priority:
                return False
        return True

    def _tree_candidate_without_gap(self, x: int):
        surface_y = self.get_surface_height(x)
        if surface_y < self.sea_level - 1:
            return None
        profile = self.get_profile(self.get_column_biome(x))
        if profile.tree is None or profile.tree_chance <= 0:
            return None
        spacing = self._tree_spacing(profile)
        cell = x // spacing
        if self._tree_candidate_x(cell, spacing) != x:
            return None
        nearby = [self.get_surface_height(nx) for nx in range(x - 3, x + 4)]
        if max(nearby) - min(nearby) > 2:
            return None
        density = (self._noise1(x, 0.026, 2, 811) + 1.0) * 0.5
        effective = profile.tree_chance * spacing * (0.55 + density * 0.65)
        effective = max(0.02, min(0.68, effective))
        if self._rand01(cell, surface_y // 4, 812) >= effective:
            return None
        return profile, surface_y

    def _tree_spacing(self, profile: BiomeProfile) -> int:
        if profile.tree_chance >= 0.13:
            return 8
        if profile.tree_chance >= 0.08:
            return 9
        if profile.tree_chance >= 0.045:
            return 11
        return 14

    def _tree_candidate_x(self, cell: int, spacing: int) -> int:
        margin = 2 if spacing >= 8 else 1
        usable = max(1, spacing - margin * 2)
        return cell * spacing + margin + self._stable_hash(cell, spacing, 813) % usable

    def _tree_height(self, config: TreeConfig, trunk_x: int) -> int:
        h = config.base_height
        if config.height_rand_a > 0:
            h += self._stable_hash(trunk_x, 820) % (config.height_rand_a + 1)
        if config.height_rand_b > 0:
            h += self._stable_hash(trunk_x, 821) % (config.height_rand_b + 1)
        # 保证最低树叶到地面的距离 >= 2 格
        shape = config.shape
        if shape == "spruce":
            h = max(h, 7)
        elif shape == "jungle":
            h = max(h, 5)
        elif shape in {"acacia", "flat"}:
            h = max(h, 3)
        else:
            h = max(h, 4)
        return h

    def tree_block_at(self, tree_name: str, trunk_x: int, ground_y: int,
                      x: int, y: int) -> str | None:
        config = self.tree_configs[tree_name]
        height = self._tree_height(config, trunk_x)
        dx = x - trunk_x
        dy = y - ground_y
        if dx == 0 and 1 <= dy <= height:
            return config.trunk

        radius = self._background_leaf_radius(config, height, dy)
        if radius is not None and abs(dx) <= radius:
            return config.leaves
        return None

    def _background_leaf_radius(self, config: TreeConfig, height: int, dy: int) -> int | None:
        shape = config.shape
        if shape in {"oak", "birch", "blob"}:
            return {
                height - 2: 2,
                height - 1: 2,
                height: 2,
                height + 1: 1,
                height + 2: 0,
            }.get(dy)
        if shape == "jungle":
            return {
                height - 3: 2,
                height - 2: 3,
                height - 1: 3,
                height: 3,
                height + 1: 2,
                height + 2: 1,
            }.get(dy)
        if shape == "dark_oak":
            return {
                height - 2: 3,
                height - 1: 3,
                height: 3,
                height + 1: 2,
                height + 2: 1,
            }.get(dy)
        if shape == "spruce":
            return {
                height - 5: 2,
                height - 4: 1,
                height - 3: 2,
                height - 2: 1,
                height - 1: 2,
                height: 1,
                height + 1: 0,
            }.get(dy)
        if shape in {"acacia", "flat"}:
            return {
                height - 1: 2,
                height: 3,
                height + 1: 3,
                height + 2: 1,
            }.get(dy)
        return None

    def _foreground_leaf_radius(self, config: TreeConfig, height: int, dy: int) -> int | None:
        radius = self._background_leaf_radius(config, height, dy)
        if radius is None or radius <= 0:
            return None
        return radius - 1

    def is_near_water(self, x: int, surface_y: int) -> bool:
        for nx in range(x - 3, x + 4):
            if self.get_surface_height(nx) < self.sea_level:
                return True
        return surface_y <= self.sea_level + 1
