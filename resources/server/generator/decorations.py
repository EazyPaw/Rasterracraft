"""Surface decoration generation for the Minecraft-like 2D generator."""

from __future__ import annotations

import json
from typing import Callable

from resources.server.blocks import *
from resources.server.biome import BiomeProfile
from resources.server.generator.config import TreeConfig, WORLDGEN_DIR
from resources.server.generator.noise import NoiseMixin


class DecorationMixin(NoiseMixin):
    """Trees, leaf caps, plants, mushrooms, cacti and sugar cane."""

    foreground_leaf_clearance = 2
    jungle_biomes = frozenset({"jungle", "sparse_jungle", "bamboo_jungle"})

    default_tree_configs = {
        "oak": TreeConfig("oak_log", "oak_leaves", 4, 2, 0, 2, "oak"),
        "birch": TreeConfig("birch_log", "birch_leaves", 5, 2, 0, 2, "birch"),
        "spruce": TreeConfig("spruce_log", "spruce_leaves", 6, 3, 1, 2, "spruce"),
        # Requested Java/Bedrock ranges and species-specific shapes.
        "jungle_tree": TreeConfig("jungle_log", "jungle_leaves", 5, 8, 0, 3, "jungle"),
        "acacia": TreeConfig("acacia_log", "acacia_leaves", 6, 5, 0, 2, "acacia"),
        "dark_oak": TreeConfig("dark_oak_log", "dark_oak_leaves", 7, 4, 0, 3, "dark_oak"),
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

    def _block_class(self, block_id: str):
        return self.block_factories.get(block_id, STONE)

    def _block(self, block_id: str):
        return self._block_class(block_id)()

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

    def get_structure_block(self, x: int, y: int, z: int, surface_y: int,
                            profile: BiomeProfile, foreground_surface_y: int | None = None):
        if foreground_surface_y is None:
            foreground_surface_y = surface_y

        giant = self.get_giant_mushroom_block(x, y, z, surface_y)
        if giant is not None:
            return giant

        if z == 1:
            tree_block = self.get_tree_block(x, y, surface_y, profile, z)
            if tree_block is not None:
                return tree_block
            if profile.biome_id in self.jungle_biomes:
                shrub = self.get_jungle_shrub_block(x, y, z)
                if shrub is not None:
                    return shrub
            return self.get_ground_decoration_block(x, y, z, surface_y, profile)

        cap_block = self.get_leaf_cap_block(x, y, foreground_surface_y, profile)
        if cap_block is not None:
            return cap_block

        # Vines are the lowest-priority foliage: never overwrite a leaf cap.
        vine = self.get_large_jungle_vine_block(x, y)
        if vine is not None:
            return vine

        return self.get_ground_decoration_block(x, y, z, surface_y, profile)

    def get_jungle_shrub_block(self, x: int, y: int, z: int):
        """Generate 2-3 block jungle bushes with one jungle-log base."""
        if z != 1:
            return None
        spacing = 6
        for cell in range(x // spacing - 1, x // spacing + 2):
            if self._stable_hash(cell, 872) % 100 >= 42:
                continue
            shrub_x = cell * spacing + 1 + self._stable_hash(cell, 873) % 4
            if abs(x - shrub_x) > 1:
                continue
            biome_id = self.get_column_biome(shrub_x)
            if biome_id not in self.jungle_biomes:
                continue
            if self._tree_at_column(shrub_x, 1) is not None:
                continue
            ground_y = self.get_layer_surface_height(shrub_x, z)
            if ground_y < self.sea_level:
                continue
            height = 2 + self._stable_hash(cell, 874) % 2
            dy = y - ground_y
            dx = x - shrub_x
            if dx == 0 and dy == 1:
                return JUNGLE_LOG()
            if 2 <= dy <= height and abs(dx) <= 1:
                return JUNGLE_LEAVES()
        return None

    def get_large_jungle_vine_block(self, x: int, y: int):
        """Place hanging vines along exposed sides of large jungle trunks."""
        for trunk_x in range(x - 3, x + 4):
            tree = self._tree_at_column(trunk_x, 1)
            if tree is None or tree[0] != "jungle_tree" or not self._is_large_jungle(trunk_x):
                continue
            ground_y = tree[1]
            height = self._tree_height(self.tree_configs["jungle_tree"], trunk_x)
            dx, dy = x - trunk_x, y - ground_y
            if dx not in (-1, 0, 1, 2) or not 2 <= dy <= height - 2:
                continue
            chance = 28 if dx in (0, 1) else 48
            if self._stable_hash(trunk_x + dx * 19, dy, 879) % 100 < chance:
                return VINE()
        return None

    def get_ground_decoration_block(self, x: int, y: int, z: int, surface_y: int,
                                    profile: BiomeProfile):
        stacked_plant = self._stacked_plant_for_column(x, surface_y, profile)
        if stacked_plant is not None:
            block_cls, height = stacked_plant
            if surface_y + 1 <= y <= surface_y + height:
                return block_cls()

        double_plant = self._double_plant_for_column(x, surface_y, z, profile)
        if double_plant is not None:
            bottom_cls, top_cls = double_plant
            if y == surface_y + 1:
                return bottom_cls()
            if y == surface_y + 2:
                return top_cls()

        if y != surface_y + 1 or surface_y < self.sea_level:
            return None

        local = self._noise1(x, 0.18, 1, 710)

        if (profile.is_arid
                and self._rand01(x, surface_y, 701) < 0.07
                and local > -0.25):
            return DEAD_BUSH()

        if (profile.fern_chance
                and self._rand01(x, surface_y, 703) < profile.fern_chance
                and local > -0.45):
            return FERN()

        if profile.biome_id == "mushroom_fields":
            if (self._rand01(x, surface_y, 704) < profile.mushroom_chance
                    and local < 0.60):
                return BROWN_MUSHROOM() if self._rand01(x, surface_y, 711) < 0.50 else RED_MUSHROOM()
        elif (profile.mushroom_chance
                and self._rand01(x, surface_y, 704) < profile.mushroom_chance * profile.mushroom_boost
                and local < 0.22):
            return BROWN_MUSHROOM() if self._rand01(x, surface_y, 711) < 0.55 else RED_MUSHROOM()

        if (profile.flower_chance
                and self._rand01(x, surface_y, 705) < profile.flower_chance
                and local > 0.02):
            return self._flower_for_profile(profile, x, surface_y)

        grass_chance = self._grass_chance(profile)
        if grass_chance and self._rand01(x, surface_y, 706) < grass_chance:
            if self._rand01(x, surface_y, 707) < 0.14 and profile.fern_chance > 0:
                return FERN()
            return SHORT_GRASS()

        if profile.is_cold:
            if profile.surface not in {"snow_block", "ice", "water"}:
                snow_extra = int(self._noise1(x, 0.15, 1, 850) * 3 + 1)
                return SNOW(layer=max(1, min(4, snow_extra)))
            return None

        return None

    def get_giant_mushroom_block(self, x: int, y: int, z: int, surface_y: int):
        """Deterministic 2.5D giant mushroom silhouettes for mushroom fields."""
        spacing = 10
        for cell in range(x // spacing - 1, x // spacing + 2):
            if self._stable_hash(cell, 977) % 100 >= 62:
                continue
            stem_x = cell * spacing + 3 + self._stable_hash(cell, 978) % 4
            biome_id = self.get_column_biome(stem_x)
            if biome_id not in {"mushroom_fields", "dark_forest"}:
                continue
            if biome_id == "dark_forest" and self._stable_hash(cell, 981) % 100 >= 9:
                continue
            ground_y = self.get_surface_height(stem_x)
            height = 5 + self._stable_hash(cell, 979) % 4
            dy = y - ground_y
            dx = x - stem_x
            # Stems, like tree trunks, remain in the background layer so the
            # player can walk past them.
            if z == 1 and dx == 0 and 1 <= dy <= height:
                return MUSHROOM_STEM()
            red = self._stable_hash(cell, 980) % 2 == 0
            if not red and dy == height + 1:
                if z == 1 and abs(dx) <= 3:
                    return BROWN_MUSHROOM_BLOCK()
                if z == 0 and abs(dx) <= 2:
                    return BROWN_MUSHROOM_BLOCK()
            if red:
                cap_top = height + 2
                if z == 1:
                    if dy == cap_top and abs(dx) <= 1:
                        return RED_MUSHROOM_BLOCK()
                    if cap_top - 3 <= dy <= cap_top - 1 and abs(dx) == 2:
                        return RED_MUSHROOM_BLOCK()
                if z == 0 and cap_top - 3 <= dy <= cap_top - 1 and abs(dx) <= 1:
                    return RED_MUSHROOM_BLOCK()
        return None

    def _stacked_plant_for_column(self, x: int, surface_y: int, profile: BiomeProfile):
        if surface_y < self.sea_level:
            return None

        if profile.cactus_chance and self._rand01(x, surface_y, 700) < profile.cactus_chance:
            height = 1 + self._stable_hash(x, surface_y, 721) % 3
            return CACTUS, height

        if profile.sugar_cane_chance and self.is_adjacent_to_water(x, surface_y):
            chance = min(0.14, max(0.06, profile.sugar_cane_chance * 3.0))
            if self._rand01(x, surface_y, 702) < chance:
                height = 1 + self._stable_hash(x, surface_y, 722) % 3
                return SUGAR_CANE, height

        return None

    def _grass_chance(self, profile: BiomeProfile) -> float:
        if profile.surface != "grass_block":
            return profile.grass_chance
        return max(profile.grass_chance, 0.10)

    def _double_plant_for_column(self, x: int, surface_y: int, z: int, profile: BiomeProfile):
        if surface_y < self.sea_level or profile.surface != "grass_block":
            return None

        chance = profile.double_plant_chance
        if chance <= 0 or self._rand01(x, surface_y, 730 + z * 17) >= chance:
            return None

        options = profile.double_plant_options
        if not options:
            return None

        roll = self._rand01(x, surface_y, 731 + z * 17)
        cumulative = 0.0
        for weight, bottom_id, top_id in options:
            cumulative += weight
            if roll <= cumulative:
                return self._block_class(bottom_id), self._block_class(top_id)
        bottom_id, top_id = options[-1][1], options[-1][2]
        return self._block_class(bottom_id), self._block_class(top_id)

    def _flower_for_profile(self, profile: BiomeProfile, x: int, y: int):
        roll = self._rand01(x, y, 712)
        for threshold, block_id in profile.flower_options:
            if roll < threshold:
                return self._block(block_id)
        return self._block(profile.flower_options[-1][1])

    def get_tree_block(self, x: int, y: int, surface_y: int,
                       profile: BiomeProfile, z: int = 1):
        if z != 1:
            return None
        if z == 1:
            for trunk_x in range(x - self.max_tree_lookup, x + self.max_tree_lookup + 1):
                tree = self._tree_at_column(trunk_x, 1)
                if tree is None or tree[0] != "spruce":
                    continue
                tree_profile = self.get_profile(self.get_column_biome(trunk_x))
                if not tree_profile.is_cold:
                    continue
                ground_y = tree[1]
                config = self.tree_configs["spruce"]
                height = self._tree_height(config, trunk_x)
                dx = abs(x - trunk_x)
                leaf_levels = [
                    dy for dy in range(height - 6, height + 2)
                    if (radius := self._background_leaf_radius(
                        config, height, dy, "spruce", trunk_x
                    )) is not None and dx <= radius
                ]
                if leaf_levels and y - ground_y == max(leaf_levels) + 1:
                    return SNOW(layer=1)

        for trunk_x in range(x - self.max_tree_lookup, x + self.max_tree_lookup + 1):
            tree = self._tree_at_column(trunk_x, z)
            if tree is None:
                continue
            tree_name, trunk_surface = tree
            config = self.tree_configs[tree_name]
            trunk_here = self.tree_block_at(tree_name, trunk_x, trunk_surface, x, y)
            if trunk_here == config.trunk:
                return self._block(config.trunk)

        for trunk_x in range(x - self.max_tree_lookup, x + self.max_tree_lookup + 1):
            tree = self._tree_at_column(trunk_x, z)
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
            tree = self._tree_at_column(trunk_x, 1)
            if tree is None:
                continue
            tree_name, trunk_surface = tree
            config = self.tree_configs[tree_name]
            height = self._tree_height(config, trunk_x)
            clearance_surface = (trunk_surface if config.shape == "acacia"
                                 else surface_y)
            if y <= clearance_surface + self.foreground_leaf_clearance:
                continue
            if config.shape == "acacia":
                if (x - trunk_x, y - trunk_surface) in self._acacia_geometry(
                        trunk_x, height
                )[2]:
                    return self._block(config.leaves)
                continue
            radius = self._foreground_leaf_radius(config, height, y - trunk_surface)
            if radius is not None and abs(x - trunk_x) <= radius:
                return self._block(config.leaves)
        return None

    def _tree_at_column(self, x: int, z: int = 1):
        cache = getattr(self, "_tree_column_cache", None)
        key = (x, z)
        if cache is not None and key in cache:
            return cache[key]

        surface_y = self.get_layer_surface_height(x, z)
        profile = self.get_profile(self.get_column_biome(x))
        result = None
        if profile.tree is not None and self.has_tree_at(x, surface_y, profile, z):
            result = (profile.tree, surface_y)

        if cache is not None:
            cache[key] = result
        return result

    def has_tree_at(self, x: int, surface_y: int, profile: BiomeProfile, z: int = 1) -> bool:
        cache = getattr(self, "_tree_presence_cache", None)
        key = (x, surface_y, profile.biome_id, z)
        if cache is not None and key in cache:
            return cache[key]

        result = self._compute_has_tree_at(x, surface_y, profile, z)
        if cache is not None:
            cache[key] = result
        return result

    def _compute_has_tree_at(self, x: int, surface_y: int, profile: BiomeProfile, z: int = 1) -> bool:
        if surface_y < self.sea_level or profile.tree_chance <= 0:
            return False

        spacing = self._tree_spacing(profile)
        cell = x // spacing
        if self._tree_candidate_x(cell, spacing) != x:
            return False

        config = self.tree_configs.get(profile.tree)
        min_gap = 2
        for neighbor_cell in (cell - 1, cell + 1):
            neighbor_x = self._tree_candidate_x(neighbor_cell, spacing)
            if abs(neighbor_x - x) < min_gap:
                return False

        nearby = [self.get_surface_height(nx) for nx in range(x - 3, x + 4)]
        if max(nearby) - min(nearby) > 3:
            return False

        density = (self._noise1(x, 0.026, 2, 811) + 1.0) * 0.5
        effective = profile.tree_chance * spacing * (0.74 + density * 0.85)
        cap = 0.98 if profile.tree_chance >= 0.13 else 0.86
        effective = max(0.02, min(cap, effective))
        if self._rand01(cell, surface_y // 4, 812) >= effective:
            return False

        priority = self._stable_hash(x, surface_y, 817)
        for nx in range(x - min_gap + 1, x + min_gap):
            if nx == x:
                continue
            competing = self._tree_candidate_without_gap(nx, z)
            if competing is None:
                continue
            competing_profile, competing_surface = competing
            competing_gap = min_gap
            if abs(nx - x) < competing_gap and self._stable_hash(nx, competing_surface, 817) < priority:
                return False
        return True

    def _tree_candidate_without_gap(self, x: int, z: int = 1):
        surface_y = self.get_layer_surface_height(x, z)
        if surface_y < self.sea_level:
            return None
        profile = self.get_profile(self.get_column_biome(x))
        if profile.tree is None or profile.tree_chance <= 0:
            return None
        spacing = self._tree_spacing(profile)
        cell = x // spacing
        if self._tree_candidate_x(cell, spacing) != x:
            return None
        nearby = [self.get_surface_height(nx) for nx in range(x - 3, x + 4)]
        if max(nearby) - min(nearby) > 3:
            return None
        density = (self._noise1(x, 0.026, 2, 811) + 1.0) * 0.5
        effective = profile.tree_chance * spacing * (0.74 + density * 0.85)
        cap = 0.98 if profile.tree_chance >= 0.13 else 0.86
        effective = max(0.02, min(cap, effective))
        if self._rand01(cell, surface_y // 4, 812) >= effective:
            return None
        return profile, surface_y

    def _tree_spacing(self, profile: BiomeProfile) -> int:
        if profile.tree_chance >= 0.24:
            return 5
        if profile.tree_chance >= 0.18:
            return 6
        if profile.tree_chance >= 0.13:
            return 6
        if profile.tree_chance >= 0.08:
            return 7
        if profile.tree_chance >= 0.045:
            return 9
        return 12

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
            if self._is_large_jungle(trunk_x):
                # 2x2 jungle trees are the tall variant, while ordinary
                # jungle trees retain the requested 5-13 block range.
                h += 4 + self._stable_hash(trunk_x, 827) % 5
        elif shape in {"acacia", "flat"}:
            h = max(h, 3)
        else:
            h = max(h, 4)
        return h

    def _is_large_jungle(self, trunk_x: int) -> bool:
        """About one third of jungle trees use the large 2x2 form."""
        return self._stable_hash(trunk_x, 823) % 100 < 34

    def tree_block_at(self, tree_name: str, trunk_x: int, ground_y: int,
                      x: int, y: int) -> str | None:
        config = self.tree_configs[tree_name]
        height = self._tree_height(config, trunk_x)
        dx = x - trunk_x
        dy = y - ground_y
        if config.shape == "acacia":
            block = self._acacia_block_at(config, trunk_x, height, dx, dy)
            if block is not None:
                return block
            # Acacia foliage is attached to each bent branch endpoint rather
            # than to the root column.  Keep it out of the generic canopy
            # radius path used by the other tree species.
            if (dx, dy) in self._acacia_background_leaf_set(trunk_x, height):
                return config.leaves
            return None
        elif config.shape == "dark_oak":
            # 2D representation of a 2x2 trunk; the northwest column rises
            # one block above its three neighbours.
            if 1 <= dy <= height - 1 and dx in (0, 1):
                return config.trunk
            if dy == height and dx == 0:
                return config.trunk
            branch_side = -1 if self._stable_hash(trunk_x, 825) % 2 else 1
            if dy == height - 3 and dx == (-1 if branch_side < 0 else 2):
                return config.trunk
            if dy == height - 2 and dx == (-2 if branch_side < 0 else 3):
                return config.trunk
        elif config.shape == "jungle" and self._is_large_jungle(trunk_x):
            if 1 <= dy <= height - 1 and dx in (0, 1):
                return config.trunk
            if dy == height and dx == 0:
                return config.trunk
            branch_side = -1 if self._stable_hash(trunk_x, 826) % 2 else 1
            if dy == height - 3 and dx == (-1 if branch_side < 0 else 2):
                return config.trunk
            if dy == height - 2 and dx == (-2 if branch_side < 0 else 3):
                return config.trunk
        elif dx == 0 and 1 <= dy <= height:
            return config.trunk

        radius = self._background_leaf_radius(config, height, dy, tree_name, trunk_x)
        if radius is not None and abs(dx) <= radius:
            return config.leaves
        return None

    def _acacia_block_at(self, config: TreeConfig, trunk_x: int, height: int,
                         dx: int, dy: int) -> str | None:
        """Return an acacia trunk block from the deterministic geometry."""
        if (dx, dy) in self._acacia_trunk_set(trunk_x, height):
            return config.trunk
        return None

    def _acacia_trunk_set(self, trunk_x: int, height: int) -> set[tuple[int, int]]:
        """Build a continuous main stem with sparse asynchronous forks.

        The main stem is vertical until the crown zone.  Forks start at
        different rows and move one block per row, leaving the central air
        gap between the two branches.  A no-fork variant bends only the top
        one or two blocks.
        """
        return self._acacia_geometry(trunk_x, height)[0]

    def _acacia_geometry(self, trunk_x: int, height: int):
        cache = getattr(self, "_acacia_geometry_cache", None)
        if cache is None:
            cache = self._acacia_geometry_cache = {}
        key = (trunk_x, height)
        if key in cache:
            return cache[key]

        trunks: set[tuple[int, int]] = set()
        endpoints: list[tuple[int, int]] = []
        direction = -1 if self._stable_hash(trunk_x, 825) % 2 else 1
        forked = self._stable_hash(trunk_x, 824) % 100 < 72

        if not forked:
            bend_count = 1 + self._stable_hash(trunk_x, 826) % 2
            bend_y = max(1, height - bend_count)
            for dy in range(1, bend_y + 1):
                trunks.add((0, dy))
            x = 0
            for step in range(1, bend_count + 1):
                x += direction
                dy = bend_y + step
                trunks.add((x, dy))
                trunks.add((x - direction, dy))
            endpoints.append((x, height))
        else:
            fork_y = max(3, height - 4)
            for dy in range(1, fork_y + 1):
                trunks.add((0, dy))

            # The forked form is binary: one main branch reaches the top and
            # exactly one lateral branch peels away.  This avoids the old
            # three-pronged silhouette while retaining short 1-2 block forks.
            main_x = 0
            for dy in range(fork_y + 1, height + 1):
                trunks.add((main_x, dy))
            endpoints.append((main_x, height))

            side_start = fork_y + 1 + self._stable_hash(trunk_x, 832) % 2
            side_len = min(2, max(0, height - side_start))
            side_x = direction
            for step in range(side_len + 1):
                dy = side_start + step
                x = direction * min(2, step + 1)
                trunks.add((x, dy))
                side_x = x
            endpoints.append((side_x, side_start + side_len))

        # Leaves are two rows high per endpoint: a narrower upper/background
        # row and a wider lower/background row, with a matching foreground
        # lower row.  Remove trunk cells so foliage can never truncate wood.
        background: set[tuple[int, int]] = set()
        foreground: set[tuple[int, int]] = set()
        for index, (cx, cy) in enumerate(endpoints):
            width = 5 if self._stable_hash(trunk_x, 831, index) % 100 < 45 else 4
            upper_half = (width - 1) // 2
            lower_width = width + 2
            lower_half = (lower_width - 1) // 2
            background.update((cx + dx, cy + 1) for dx in range(-upper_half, upper_half + 1))
            background.update((cx + dx, cy) for dx in range(-lower_half, lower_half + 1))
            foreground.update((cx + dx, cy) for dx in range(-upper_half, upper_half + 1))
        background.difference_update(trunks)
        foreground.difference_update(trunks)
        cache[key] = trunks, background, foreground
        return cache[key]

    def _acacia_background_leaf_set(self, trunk_x: int, height: int):
        return self._acacia_geometry(trunk_x, height)[1]

    def _background_leaf_radius(self, config: TreeConfig, height: int, dy: int,
                                tree_name: str | None = None,
                                trunk_x: int | None = None) -> int | None:
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
        if shape == "flat":
            return {
                height - 1: 2,
                height: 2,
                height + 1: 2,
            }.get(dy)
        return None

    def _foreground_leaf_radius(self, config: TreeConfig, height: int, dy: int,
                                tree_name: str | None = None,
                                trunk_x: int | None = None) -> int | None:
        radius = self._background_leaf_radius(config, height, dy, tree_name, trunk_x)
        if radius is None or radius <= 0:
            return None
        return radius - 1

    def is_adjacent_to_water(self, x: int, surface_y: int) -> bool:
        if surface_y > self.sea_level:
            return False
        for nx in (x - 1, x + 1):
            neighbor_surface = self.get_surface_height(nx)
            if neighbor_surface < surface_y <= self.sea_level:
                return True
        return False

    def is_near_water(self, x: int, surface_y: int) -> bool:
        return self.is_adjacent_to_water(x, surface_y)
