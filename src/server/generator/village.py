"""Deterministic village layouts, shared by chunk generation and /locate.

Templates describe buildings; this planner owns spacing, terrain adaptation,
roads and decorations. It only reads original terrain, never loaded chunks or
player edits. Each chunk applies its own slice before block initialization.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import cached_property, lru_cache

from src.server.blocks import get_block_by_id
from src.server.generator.classic_flat import ClassicFlat
from src.server.generator.minecraft_like import MinecraftLike2D
from src.server.location import Location
from src.server.structure import iter_structure_blocks, load_structure_data


@dataclass(frozen=True)
class VillagePiece:
    template: str
    x: int
    y: int
    width: int
    mirror_x: bool = False


@dataclass(frozen=True)
class VillagePlan:
    center_x: int
    x_min: int
    ground: tuple[int, ...]
    houses: tuple[VillagePiece, ...]
    lamps: tuple[VillagePiece, ...]
    hay: tuple[tuple[int, int, int], ...]

    @property
    def x_max(self) -> int:
        return self.x_min + len(self.ground) - 1

    @property
    def location(self) -> tuple[int, int]:
        return self.center_x, self.ground[self.center_x - self.x_min] + 1


class VillageGenerator:
    # One candidate per 32 chunks, with an eight-chunk margin on either side.
    # The full village remains in its region, so adjacent starts cannot collide.
    SPACING = 512
    MARGIN = 128
    MAX_RADIUS = 96
    BIOMES = frozenset({"plains", "desert", "savanna"})

    def __init__(self, generator, max_height=256, enabled=True):
        self.generator = generator
        self.max_height = max_height
        self.enabled = bool(enabled) and isinstance(generator, (MinecraftLike2D, ClassicFlat))
        if isinstance(generator, ClassicFlat):
            self.enabled = self.enabled and "village" in generator.settings.structures
        # Bound memory even when /locate searches a long stretch of the world.
        self.plan_for_region = lru_cache(maxsize=256)(self._build_plan)

    @cached_property
    def templates(self):
        return {name: load_structure_data(name)[1] for name in ("house1", "house2", "light")}

    def _random(self, region: int) -> random.Random:
        # Explicit integer mixing is stable across processes, including x < 0.
        value = (int(self.generator.seed) ^ (region * 341873128712) ^ 10387312) & ((1 << 64) - 1)
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
        return random.Random(value ^ (value >> 27))

    def _surface(self, x, z=0):
        layered = getattr(self.generator, "get_layer_surface_height", None)
        return layered(x, z) if callable(layered) else self.generator.get_surface_height(x)

    def _build_plan(self, region: int) -> VillagePlan | None:
        if not self.enabled:
            return None
        rng = self._random(region)
        center = region * self.SPACING + self.MARGIN + rng.randrange(self.SPACING - 2 * self.MARGIN)
        if self.generator.get_original_biome(center, 0) not in self.BIOMES:
            return None

        # House2 has one entrance, so keep it at either end facing the road.
        # House1 has doors on both sides and forms the village's connectors.
        names = ["house2", *(["house1"] * rng.randint(2, 4)), "house2"]
        widths = [self.templates[name]["size"][0] for name in names]
        gaps = [rng.randint(8, 12) for _ in range(len(names) - 1)]
        span = sum(widths) + sum(gaps) + 8
        if span > self.MAX_RADIUS * 2:
            return None
        x_min = center - span // 2
        natural = [self._surface(x) for x in range(x_min, x_min + span)]
        if min(natural) < 1 or max(natural) + 17 >= self.max_height:
            return None
        sea_level = getattr(self.generator, "sea_level", -1)
        for i, y in enumerate(natural):
            x = x_min + i
            if y < sea_level or self.generator.get_original_biome(x, y) not in self.BIOMES:
                return None
            # Superflat presets can have water, lava or non-solid top layers.
            if isinstance(self.generator, ClassicFlat):
                block = self.generator.get_original_block(x, y, 0)
                if not block.solid or block.block_id in ("water", "lava"):
                    return None

        houses = []
        cursor = 4
        ground = list(natural)
        for i, (name, width) in enumerate(zip(names, widths)):
            footprint = natural[cursor:cursor + width]
            if max(footprint) - min(footprint) > 4:
                return None
            floor = sorted(footprint)[len(footprint) // 2]
            if floor + self.templates[name]["size"][1] > self.max_height:
                return None
            if i == 0:
                mirror_x = True
            elif i == len(names) - 1:
                mirror_x = False
            else:
                mirror_x = bool(rng.getrandbits(1))
            houses.append(
                VillagePiece(name, x_min + cursor, floor, width, mirror_x)
            )
            ground[cursor:cursor + width] = [floor] * width
            cursor += width
            if i < len(gaps):
                cursor += gaps[i]

        # Keep each house level; join plateaus with a walkable, gradual road.
        links = [(0, natural[0])]
        for house in houses:
            links.extend(((house.x - x_min, house.y), (house.x - x_min + house.width - 1, house.y)))
        links.append((span - 1, natural[-1]))
        for (a, ay), (b, by) in zip(links, links[1:]):
            if abs(by - ay) > b - a:
                return None
            for i in range(a, b + 1):
                ground[i] = ay + round((by - ay) * (i - a) / (b - a))
        if any(abs(y - natural[i]) > 5 for i, y in enumerate(ground)):
            return None

        lamps = []
        hay = []
        lamp_width = self.templates["light"]["size"][0]
        for i, (left, right) in enumerate(zip(houses, houses[1:])):
            gap_start, gap_end = left.x + left.width, right.x - 1
            # Separate footprints leave the house entrances and road usable.
            if i == 0 or rng.random() < 0.65:
                lamp_x = gap_start + 1
                support_x = lamp_x + lamp_width // 2
                lamps.append(
                    VillagePiece(
                        "light", lamp_x,
                        self._surface(support_x, 1) + 1,
                        lamp_width,
                    )
                )
            if i == 1 or rng.random() < 0.65:
                hay_width = rng.randint(2, 3)
                hay_start = gap_end - hay_width
                for x in range(hay_start, hay_start + hay_width):
                    base_y = self._surface(x, 1) + 1
                    height = 1
                    if x == hay_start + hay_width // 2 and rng.random() < 0.7:
                        height = 2
                    # Decorations sit on natural background terrain, not the
                    # graded foreground road. Never replace existing plants.
                    if all(
                        self.generator.get_original_block(x, y, 1).block_id == "air"
                        for y in range(base_y, base_y + height)
                    ):
                        hay.extend((x, y, 1) for y in range(base_y, base_y + height))
        return VillagePlan(center, x_min, tuple(ground), tuple(houses), tuple(lamps), tuple(hay))

    def plans_for_chunk(self, rx: int):
        if not self.enabled:
            return
        first, last = rx * 16, rx * 16 + 15
        first_region = (first - self.MAX_RADIUS) // self.SPACING
        last_region = (last + self.MAX_RADIUS) // self.SPACING
        for region in range(first_region, last_region + 1):
            plan = self.plan_for_region(region)
            if plan is not None and plan.x_min <= last and plan.x_max >= first:
                yield plan

    def locate(self, origin_x: int, max_radius=524288) -> tuple[int, int] | None:
        """Find the nearest valid start without generating or loading chunks."""
        if not self.enabled:
            return None

        def distance_to_region(region):
            first = region * self.SPACING + self.MARGIN
            last = (region + 1) * self.SPACING - self.MARGIN - 1
            return max(first - origin_x, origin_x - last, 0)

        first_region = (origin_x - max_radius) // self.SPACING
        last_region = (origin_x + max_radius) // self.SPACING
        regions = range(first_region, last_region + 1)
        nearest = None
        distance = max_radius + 1
        for region in sorted(regions, key=lambda r: (distance_to_region(r), r)):
            if distance_to_region(region) > min(distance, max_radius):
                break
            plan = self.plan_for_region(region)
            if plan is None:
                continue
            candidate_distance = abs(plan.center_x - origin_x)
            if candidate_distance <= max_radius and candidate_distance < distance:
                nearest, distance = plan.location, candidate_distance
        return nearest

    def apply_chunk(self, world, rx: int, blocks) -> None:
        """Apply only to the new chunk array, before hooks, light and fluids."""
        first, last = rx * 16, rx * 16 + 15

        def write(x, y, z, entry):
            if not 0 <= y < blocks.shape[1]:
                return
            block = get_block_by_id(entry["id"])
            if entry.get("nbt"):
                block.write_nbt(entry["nbt"])
            block.location = Location(world, x, y, z)
            blocks[x - first, y, z] = block

        for plan in self.plans_for_chunk(rx):
            for x in range(max(first, plan.x_min), min(last, plan.x_max) + 1):
                road_y = plan.ground[x - plan.x_min]
                foundation = any(h.x <= x < h.x + h.width for h in plan.houses)
                # Only the foreground is graded for the road. The background
                # keeps its original height, grass and trees between buildings.
                original_y = self._surface(x, 0)
                for y in range(max(1, min(original_y, road_y) - 2), road_y):
                    write(x, y, 0, {"id": "cobblestone" if foundation else "dirt"})
                write(x, road_y, 0, {"id": "gravel"})
                for y in range(road_y + 1, min(self.max_height, max(original_y, road_y) + 17)):
                    write(x, y, 0, {"id": "air"})
            for piece in (*plan.houses, *plan.lamps):
                data = self.templates[piece.template]
                for x, y, z, entry in iter_structure_blocks(
                    data, (piece.x, piece.y, 0), x_bounds=(first, last), mirror_x=piece.mirror_x
                ):
                    write(x, y, z, entry)
            for x, y, z in plan.hay:
                if (first <= x <= last and 0 <= y < blocks.shape[1]
                        and blocks[x - first, y, z].block_id == "air"):
                    write(x, y, z, {"id": "hay_block"})
