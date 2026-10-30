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
    occupants = list(getattr(world, "entities", {}).values())
    occupants.extend(getattr(getattr(world, "server", None), "players", ()))
    for other in occupants:
        if (getattr(other, "world", None) is not world or getattr(other, "removed", False)
                or not getattr(other, "blocks_block_placement", True)
                or int(getattr(other, "z", 0)) != int(entity.z)):
            continue
        if (entity.x < other.x + other.width and entity.x + entity.width > other.x
                and entity.y < other.y + other.height and entity.y + entity.height > other.y):
            return False
    return True


def spawn_animals_for_chunk(world, rx: int) -> list:
    if bool(getattr(world, "disable_mob_generation", False)) or world.id_name == "nether":
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


NETHER_MONSTER_WEIGHTS = (("ghast", 50), ("zombie_pigman", 100), ("magma_cube", 1))
FORTRESS_MONSTER_WEIGHTS = (("blaze", 10), ("zombie_pigman", 5),
                            ("wither_skeleton", 10), ("magma_cube", 3))


def tick_enderman_spawning(world):
    """Rare overworld dark-area spawns, adapted to the game's 2-D population."""
    if world.id_name != "overworld" or world.disable_mob_generation:
        return
    players = [p for p in tuple(world.server.players) if p.world is world and p.health > 0
               and getattr(p.gamemode, "name_id", "survival") != "spectator"]
    if not players:
        return
    endermen = [e for e in tuple(world.entities.values()) if e.entity_id == "enderman"]
    for mob in endermen:
        distance = min((mob.x - p.x) ** 2 + (mob.y - p.y) ** 2 for p in players)
        if (not mob.persistence_required and not getattr(mob, "name", None)
                and (distance > 128 ** 2 or (distance > 32 ** 2 and random.randrange(800) == 0))):
            world.remove_entity(mob)
    if len(endermen) >= 6 * len(players):
        return
    eligible = sorted({rx for p in players for rx in range(int(p.x // 16) - 7, int(p.x // 16) + 8)
                       if world.is_chunk_loaded(rx)})
    if not eligible:
        return
    for _ in range(8):
        x = random.choice(eligible) * 16 + random.randrange(16)
        y = random.randrange(1, world.attribute.MAX_BUILD_HEIGHT - 3)
        if min((x - p.x) ** 2 + (y - p.y) ** 2 for p in players) < 24 ** 2:
            continue
        if (x - world.spawn_point) ** 2 + (y - 64) ** 2 < 24 ** 2:
            continue
        ground = world.get_block(x, y - 1, 0)
        if not ground.solid or ground.block_id == "bedrock":
            continue
        sky = world.get_sky_light(x, y)
        # Skylight arrays store the daytime value; apply the day/night darkening.
        sky -= 11 if 13000 <= world.world_time % 24000 <= 23000 else 0
        if max(sky, world.get_block_light(x, y)) > random.randrange(8):
            continue
        entity = create_entity("enderman", x + 0.2, y, world, 0)
        if _can_fit(world, entity):
            world.spawn_entity(entity)
            break


def tick_nether_spawning(world):
    """Bound the mob population for a 2-D slice; never spawn beside a player."""
    if world.id_name != "nether" or world.disable_mob_generation:
        return
    players = [p for p in tuple(world.server.players) if p.world is world and p.health > 0
               and getattr(p.gamemode, "name_id", "survival") != "spectator"]
    if not players:
        return
    monsters = [e for e in tuple(world.entities.values()) if e.entity_id in {
        "ghast", "zombie_pigman", "magma_cube", "blaze", "wither_skeleton", "skeleton"}]
    for mob in monsters:
        distance = min((mob.x - p.x) ** 2 + (mob.y - p.y) ** 2 for p in players)
        if not mob.persistence_required and (distance > 128 ** 2 or
                (distance > 32 ** 2 and random.randrange(100) == 0)):
            world.remove_entity(mob)
    if len(monsters) >= 24 * len(players):
        return
    eligible = sorted({rx for p in players for rx in range(int(p.x // 16) - 7, int(p.x // 16) + 8)
                       if world.is_chunk_loaded(rx)})
    if not eligible:
        return
    slots = 24 * len(players) - len(monsters)
    for _ in range(16):
        x = random.choice(eligible) * 16 + random.randrange(16)
        y = random.randint(5, 119)
        if min((x - p.x) ** 2 + (y - p.y) ** 2 for p in players) < 24 ** 2:
            continue
        fortress = getattr(world.structure_generator, "fortress_at", lambda *_: False)(x, y)
        weights = FORTRESS_MONSTER_WEIGHTS if fortress else NETHER_MONSTER_WEIGHTS
        entity_id = random.choices([key for key, _ in weights], [w for _, w in weights])[0]
        if entity_id == "wither_skeleton" and random.randrange(5) == 0:
            entity_id = "skeleton"
        if entity_id == "ghast" and random.randrange(20) != 0:
            continue  # EntityGhast#getCanSpawnHere's 1-in-20 check.
        entity = create_entity(entity_id, x + 0.1, y, world, 0)
        if not world.is_position_loaded(math.floor(entity.x + entity.width),
                                        math.floor(entity.y + entity.height), 0):
            continue
        if not _can_fit(world, entity):
            continue
        if entity_id != "ghast":
            ground = world.get_block(x, y - 1, 0)
            if not ground.solid or ground.block_id == "bedrock":
                continue
        world.spawn_entity(entity)
        slots -= 1
        if slots <= 0:
            break
