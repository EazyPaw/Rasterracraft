"""The five-frame 2.5D End portal and authoritative dimension entry boundary."""


def frame_positions(left, y):
    # Facing is into the opening: right, left, and out of the rear layer.
    return ((left, y, 0, 1), (left + 4, y, 0, -1),
            *((left + dx, y, 1, 0) for dx in (1, 2, 3)))


def portal_status(world, left, y):
    """Return None for incomplete chunks, otherwise whether all eyes face inward."""
    if not all(world.is_chunk_loaded(x // 16) for x in (left, left + 4)):
        return None
    return all((block := world.get_block(x, py, z)).block_id == "end_portal_frame"
               and block.eye and block.facing == facing
               for x, py, z, facing in frame_positions(left, y))


def activate_end_portal(world, x, y):
    from src.server.blocks import END_PORTAL

    if getattr(world, "server", None) is None or getattr(world, "structure_build_mode", False):
        return False
    for left in range(x - 4, x + 1):
        if portal_status(world, left, y) is True:
            for dx in (1, 2, 3):
                if world.get_block(left + dx, y, 0).block_id != "end_portal":
                    world.set_block(END_PORTAL(), left + dx, y, 0, block_update=False)
            return True
    return False


def request_end_entry(entity, location=None):
    """Request server travel; pending arena loads latch this portal contact."""
    if (entity.removed or entity.health <= 0
            or getattr(entity, "riding_entity", None) is not None):
        return False
    server = getattr(entity.world, "server", None)
    if server is None:
        return False
    tick = int(getattr(server, "server_ticks", 0))
    if tick < getattr(entity, "_end_entry_retry_tick", -1):
        return False
    entity._end_entry_retry_tick = tick + 20
    handler = getattr(server, "enter_end", None)
    return bool(handler(entity, location)) if callable(handler) else False
