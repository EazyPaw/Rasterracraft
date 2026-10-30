"""Server-side destination search and safe return portal construction."""
import math

from src.server.blocks import AIR, OBSIDIAN, NETHER_PORTAL


def find_or_create_portal(world, target_x, target_y):
    target_x = max(-29999872, min(29999872, float(target_x)))
    target_y = max(1, min(118 if world.attribute.ENVIRONMENT == -1 else 248, int(target_y)))
    left, right = math.floor(target_x - 128), math.floor(target_x + 128)
    for rx in range(left // 16, right // 16 + 1):
        if not world.is_chunk_loaded(rx):
            world.generate_chunk(rx)
    candidates = []
    for rx in range(left // 16, right // 16 + 1):
        chunk = world.regions[rx]
        for lx in range(16):
            x = rx * 16 + lx
            if not left <= x <= right:
                continue
            for y in range(1, min(128 if world.attribute.ENVIRONMENT == -1 else 256,
                                  world.attribute.MAX_BUILD_HEIGHT - 2)):
                for z in (0, 1):
                    if chunk.region_array[lx, y, z].block_id != "nether_portal":
                        continue
                    if world.get_block(x, y - 1, z).block_id == "nether_portal":
                        continue
                    ground = world.get_block(x, y - 1, 0)
                    needs_platform = not ground.get_collision_box() or getattr(ground, "is_fluid", False)
                    # Hand-built background portals may have their bottom
                    # obsidian only in the rear layer. Reuse that frame and
                    # provide a front landing instead of building over it.
                    if needs_platform and not (
                        z == 1 and world.get_block(x, y - 1, 1).block_id == "obsidian"
                    ):
                        continue
                    # A portal in the back layer is entered from the front.
                    if all(not world.get_block(x, y + dy, 0).get_collision_box()
                           and not getattr(world.get_block(x, y + dy, 0), "is_fluid", False)
                           for dy in (0, 1)):
                        candidates.append(((x - target_x) ** 2 + (y - target_y) ** 2, x, y, needs_platform))
    if candidates:
        _, x, y, needs_platform = min(candidates)
        if needs_platform:
            world.set_block(OBSIDIAN(), x, y - 1, 0, block_update=False)
        return x + 0.2, float(y)

    # Search dry solid ground with a full four-by-five opening nearby.
    ceiling = min(122 if world.attribute.ENVIRONMENT == -1 else 250,
                  world.attribute.MAX_BUILD_HEIGHT - 5)
    sites = []
    for x in range(math.floor(target_x) - 16, math.floor(target_x) + 17):
        for y in range(2, ceiling):
            if all(world.get_block(px, y - 1, 0).solid and
                   not getattr(world.get_block(px, y - 1, 0), "is_fluid", False)
                   for px in range(x - 1, x + 3)) and all(
                       world.get_block(px, py, z).block_id == "air"
                       for px in range(x - 1, x + 3)
                       for py in range(y, y + 4) for z in (0, 1)):
                sites.append(((x - target_x) ** 2 + (y - target_y) ** 2, x, y))
    if sites:
        _, x, y = min(sites)
    else:
        x, y = math.floor(target_x), max(70, target_y)
        y = min(ceiling - 1, y)
    # Always provide an arrival platform and clear headroom in both layers.
    for px in range(x - 2, x + 4):
        for z in (0, 1):
            world.set_block(OBSIDIAN(), px, y - 1, z, block_update=False)
            for py in range(y, y + 4):
                world.set_block(AIR(), px, py, z, block_update=False)
    for px in range(x - 1, x + 3):
        for py in range(y - 1, y + 4):
            edge = px in (x - 1, x + 2) or py in (y - 1, y + 3)
            world.set_block(OBSIDIAN() if edge else NETHER_PORTAL(),
                            px, py, 1, block_update=False)
    return x + 0.2, float(y)
