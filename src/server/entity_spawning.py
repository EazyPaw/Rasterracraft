# Commented and arranged by ChatGPT

from __future__ import annotations

import math
import random

from src.server.entity_registry import create_entity
from src.server.tags import BlockTag


CREATURE_WEIGHTS = (
    ("sheep", 12),
    ("pig", 10),
    ("chicken", 10),
    ("cow", 8),
)
SNOWY_CREATURE_BIOMES = frozenset({"snowy_plains", "ice_spikes"})
MAX_GENERATION_GROUPS = 8


def _weighted_entity_id(rng: random.Random) -> str:
    total = sum(weight for _, weight in CREATURE_WEIGHTS)
    value = rng.randrange(total)
    for entity_id, weight in CREATURE_WEIGHTS:
        if value < weight:
            return entity_id
        value -= weight
    return CREATURE_WEIGHTS[-1][0]


def _surface_y(world, x: int, z: int = 0) -> int | None:
    for y in range(world.attribute.MAX_BUILD_HEIGHT - 2, 0, -1):
        block = world.get_block(x, y, z)
        if BlockTag.ANIMALS_SPAWNABLE_ON not in getattr(block, "Tags", ()):
            continue

        return y + 1
    return None


def _creature_probability(world, rx: int) -> float:
    sample_x = rx * 16 + 8
    y = _surface_y(world, sample_x, 0)
    biome_id = world.get_biome(sample_x, y if y is not None else 64)
    return 0.07 if biome_id in SNOWY_CREATURE_BIOMES else 0.10


def _can_fit(world, entity) -> bool:
    left = math.floor(entity.x)
    right = math.floor(entity.x + entity.width - 1e-6)
    bottom = math.floor(entity.y)
    top = math.floor(entity.y + entity.height - 1e-6)
    for x in range(left, right + 1):
        for y in range(bottom, top + 1):
            block = world.get_block(x, y, entity.z)
            getter = getattr(block, "get_collision_box", None)
            shape = (
                getter() if callable(getter) else getattr(block, "collision_box", None)
            )
            if shape or getattr(block, "is_fluid", False):
                return False
    return True


def spawn_animals_for_chunk(world, rx: int) -> list:
    if bool(getattr(world, "disable_mob_generation", False)):
        return []
    rng = random.Random(f"{world.seed}:{world.id_name}:{int(rx)}:initial_animals")
    probability = _creature_probability(world, rx)
    spawned = []
    group_count = 0
    while group_count < MAX_GENERATION_GROUPS and rng.random() < probability:
        group_count += 1
        entity_id = _weighted_entity_id(rng)
        group_origin = rx * 16 + rng.randrange(16)
        for _ in range(4):
            placed = False
            for _attempt in range(4):
                block_x = max(
                    rx * 16, min(rx * 16 + 15, group_origin + rng.randint(-4, 4))
                )
                spawn_y = _surface_y(world, block_x, 0)
                if spawn_y is None:
                    continue
                entity = create_entity(entity_id, block_x + 0.5, spawn_y, world, 0)
                entity.x -= entity.width * 0.5
                if not _can_fit(world, entity):
                    continue
                world.spawn_entity(entity)
                spawned.append(entity)
                group_origin = block_x
                placed = True
                break
            if not placed:
                continue
    return spawned
