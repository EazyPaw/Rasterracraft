"""Stable entity-id registry used by commands, spawning and save restore."""


def get_entity_types() -> dict[str, type]:
    # Delayed imports keep the base entity module independent of concrete mobs.
    from resources.server.entities.chicken import Chicken
    from resources.server.entities.cow import Cow
    from resources.server.entities.pig import Pig
    from resources.server.entities.sheep import Sheep
    from resources.server.entities.zombie import Zombie

    return {
        "chicken": Chicken,
        "cow": Cow,
        "pig": Pig,
        "sheep": Sheep,
        "zombie": Zombie,
    }


def create_entity(entity_id: str, x: float, y: float, world, z: int = 0):
    normalized = str(entity_id).lower().removeprefix("minecraft:")
    entity_type = get_entity_types().get(normalized)
    if entity_type is None:
        raise ValueError(f"Unknown entity: {entity_id}")
    return entity_type(float(x), float(y), world, int(z))


def create_entity_from_save(data: dict, world):
    try:
        entity = create_entity(
            data.get("entity_id", ""),
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            world,
            int(data.get("z", 0)),
        )
        entity.restore_common_save_data(data)
        return entity
    except (TypeError, ValueError):
        return None

