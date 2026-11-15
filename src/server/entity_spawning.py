# Commented and arranged by ChatGPT

from __future__ import annotations

import math
import random

from src.server.entity_registry import create_entity
from src.server.tags import BlockTag
from src.server.block_collision import coerce_collision_shape
from src.server.mob_rules import brightness, local_light, peaceful


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
    if bool(getattr(world, "disable_mob_generation", False)) or world.id_name in {"nether", "end"}:
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

# BiomeGenBase's supported 1.8.9 monsters. Endermen use the same cap;
# the old separate six-endermen-per-player spawner is intentionally gone.
OVERWORLD_MONSTER_WEIGHTS = (("spider", 100), ("zombie", 100),
                             ("skeleton", 100), ("creeper", 100), ("enderman", 10))
OVERWORLD_MONSTERS = frozenset(key for key, _ in OVERWORLD_MONSTER_WEIGHTS)
MONSTER_CAP_2D = 12
MONSTER_SPAWN_INTERVAL = 20
MAX_MONSTERS_PER_PASS = 2
LOCAL_MONSTER_LIMIT = 3


def _spawn_players(world):
    return [p for p in tuple(world.server.players) if p.world is world and p.health > 0
            and not getattr(p, "removed", False)
            and getattr(p.gamemode, "name_id", "survival") != "spectator"]


def _distance_squared(x, y, player):
    return (x - player.x - player.width / 2) ** 2 + (y - player.y) ** 2


def tick_monster_despawning(world, players):
    """EntityLiving.despawnEntity: 128 hard / 32 soft / 600 tick grace."""
    for mob in tuple(world.entities.values()):
        if mob.entity_id not in OVERWORLD_MONSTERS or mob.removed:
            continue
        if peaceful(world):
            world.remove_entity(mob)
            continue
        if mob.persistence_required or getattr(mob, "name", None):
            mob.despawn_age = 0
            continue
        mob.despawn_age = getattr(mob, "despawn_age", 0) + 1
        if brightness(mob) > 0.5:
            mob.despawn_age += 2
        if not players:
            continue
        distance = min(_distance_squared(mob.x + mob.width / 2, mob.y, p) for p in players)
        if distance > 128 ** 2:
            world.remove_entity(mob)
        elif distance < 32 ** 2:
            mob.despawn_age = 0
        elif mob.despawn_age > 600 and random.randrange(800) == 0:
            world.remove_entity(mob)


def _monster_light_valid(world, x, y):
    # The raw-sky check is separate from the effective light check in EntityMob.
    return (world.get_sky_light(x, y) <= random.randrange(32)
            and local_light(world, x, y) <= random.randrange(8))


def _spawn_ground_valid(world, x, y):
    ground = world.get_block(x, y - 1, 0)
    if not ground.solid or ground.block_id in {"bedrock", "barrier", "glass", "ice"}:
        return False
    if "leaves" in ground.block_id:
        return False
    shape = coerce_collision_shape(ground.get_collision_box())
    # A full top face allows upper/double slabs and upside-down stairs.
    spans = sorted((b.min_x, b.max_x) for b in shape.boxes if b.max_y >= 1.0)
    end = 0.0
    for left, right in spans:
        if left > end + 1e-6:
            return False
        end = max(end, right)
    return end >= 1.0


def _random_spawn_height(world, x):
    # SpawnerAnimals#getRandomChunkPosition rounds the column height to 16.
    top = 0
    for y in range(world.attribute.MAX_BUILD_HEIGHT - 1, -1, -1):
        block = world.get_block(x, y, 0)
        if getattr(block, "light_attenuation", 1) > 1:
            top = y + 1
            break
    ceiling = min(world.attribute.MAX_BUILD_HEIGHT, ((top + 1 + 15) // 16) * 16)
    return random.randrange(max(1, ceiling))


def tick_monster_spawning(world):
    """SpawnerAnimals, projected from X/Z chunks onto the game's X axis.

    The vanilla 70 applies to a 17x17 chunk area, not a one-chunk-deep
    slice. Use a 12-monster budget here, with shared multiplayer coverage.
    """
    if world.id_name not in {"overworld", "end"}:
        return
    players = _spawn_players(world)
    tick_monster_despawning(world, players)
    if not players or getattr(world, "disable_mob_generation", False) or peaceful(world):
        return
    neighborhoods = {rx for p in players for rx in range(math.floor(p.x / 16) - 8,
                                                        math.floor(p.x / 16) + 9)}
    eligible = list({rx for p in players for rx in range(math.floor(p.x / 16) - 7,
                                                        math.floor(p.x / 16) + 8)
                     if world.is_chunk_loaded(rx)})
    cap = MONSTER_CAP_2D * len(neighborhoods) // 17
    monsters = [e for e in tuple(world.entities.values())
                if e.entity_id in OVERWORLD_MONSTERS and not e.removed
                and not e.persistence_required and not getattr(e, "name", None)]
    # Migrate existing crowded saves too. Keep the closest ordinary monsters;
    # trimming is despawning, so it emits neither loot nor death effects.
    if len(monsters) > cap:
        monsters.sort(key=lambda e: min(_distance_squared(e.x + e.width / 2, e.y, p)
                                       for p in players))
        for mob in monsters[cap:]:
            world.remove_entity(mob)
        monsters = monsters[:cap]
    count = len(monsters)
    if count >= cap:
        return
    if getattr(world.server, "server_ticks", 0) % MONSTER_SPAWN_INTERVAL:
        return
    random.shuffle(eligible)
    spawn_x = 100.0 if world.id_name == "end" else float(world.spawn_point)
    height_getter = getattr(getattr(world, "generator", None), "get_spawn_height", None)
    # Match Server.get_player_spawn's default until the world stores a Y.
    spawn_y = float(height_getter(spawn_x)) if callable(height_getter) else 100.0
    spawned_this_pass = 0
    for rx in eligible:
        origin_x = rx * 16 + random.randrange(16)
        y = _random_spawn_height(world, origin_x)
        if y < 1:
            continue
        chunk_count = 0
        # Three packs, four random-walk attempts each, at a fixed Y.
        for _pack in range(3):
            x = origin_x
            entity_id = None
            for _attempt in range(4):
                x += random.randrange(6) - random.randrange(6)
                if not world.is_chunk_loaded(x // 16):
                    continue
                if any(_distance_squared(x + 0.5, y, p) < 24 ** 2 for p in players):
                    continue
                if (x + 0.5 - spawn_x) ** 2 + (y - spawn_y) ** 2 < 24 ** 2:
                    continue
                if world.get_biome(x, y) in {"mushroom_fields", "mushroom_island", "void"}:
                    continue
                if sum(abs(mob.x + mob.width / 2 - x - 0.5) < 16
                       and abs(mob.y - y) < 8 for mob in monsters) >= LOCAL_MONSTER_LIMIT:
                    continue
                if entity_id is None:
                    entity_id = ("enderman" if world.id_name == "end" else
                                 random.choices([k for k, _ in OVERWORLD_MONSTER_WEIGHTS],
                                                [w for _, w in OVERWORLD_MONSTER_WEIGHTS])[0])
                if not _spawn_ground_valid(world, x, y) or not _monster_light_valid(world, x, y):
                    continue
                entity = create_entity(entity_id, x + 0.5, y, world, 0)
                entity.x -= entity.width / 2
                if y + entity.height >= world.attribute.MAX_BUILD_HEIGHT:
                    continue
                if not all(world.is_chunk_loaded(cx) for cx in
                    range(math.floor(entity.x) // 16, math.floor(entity.x + entity.width) // 16 + 1)):
                    continue
                if not _can_fit(world, entity):
                    continue
                entity.facing = random.randrange(2)
                world.spawn_entity(entity)
                monsters.append(entity)
                spawned_this_pass += 1
                chunk_count += 1
                count += 1
                if count >= cap or spawned_this_pass >= MAX_MONSTERS_PER_PASS:
                    return
                if chunk_count >= 4:
                    break
            if chunk_count >= 4:
                break


def tick_enderman_spawning(world):
    """Compatibility entry point; endermen now share the monster population."""
    return tick_monster_spawning(world)


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
