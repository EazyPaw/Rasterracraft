"""Shared eye-ray picking for client previews and authoritative attacks."""

import math


def player_eye(player):
    return (player.x + player.width * 0.5,
            player.y + getattr(player, "eye_height", player.height * 0.85))


def ray_box_distance(origin, direction, bounds, reach):
    entry, exit_ = 0.0, reach
    for start, delta, low, high in zip(origin, direction, bounds[:2], bounds[2:]):
        if abs(delta) < 1e-12:
            if start < low or start > high:
                return None
            continue
        near, far = sorted(((low - start) / delta, (high - start) / delta))
        entry, exit_ = max(entry, near), min(exit_, far)
        if entry > exit_:
            return None
    return entry


def pick_entity(player, world, entities, direction):
    """Return the first live attackable entity before any blocking geometry."""
    try:
        dx, dy = map(float, direction)
        length = math.hypot(dx, dy)
        reach = max(0.0, float(player.interact_range))
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in (dx, dy, length, reach)) or length < 1e-12:
        return None
    direction = dx / length, dy / length
    origin = player_eye(player)
    best, distance = None, reach
    for entity in entities:
        if (entity is player or getattr(entity, "removed", False)
                or getattr(entity, "health", 0) <= 0
                or not getattr(entity, "attackable", True)
                or int(getattr(entity, "z", 0)) != int(getattr(player, "z", 0))
                or getattr(entity, "world", world) is not world):
            continue
        hit = ray_box_distance(origin, direction, (
            entity.x, entity.y, entity.x + entity.width, entity.y + entity.height,
        ), distance)
        if hit is not None and (best is None or hit < distance):
            best, distance = entity, hit
    if best is None:
        return None
    end = origin[0] + direction[0] * distance, origin[1] + direction[1] * distance
    for x in range(math.floor(min(origin[0], end[0])) - 1,
                   math.floor(max(origin[0], end[0])) + 2):
        for y in range(math.floor(min(origin[1], end[1])) - 1,
                       math.floor(max(origin[1], end[1])) + 2):
            block = world.get_block(x, y, int(getattr(player, "z", 0)))
            for box in block.get_collision_box():
                hit = ray_box_distance(origin, direction, (
                    x + box.min_x, y + box.min_y, x + box.max_x, y + box.max_y,
                ), distance)
                if hit is not None:
                    return None
    return best
