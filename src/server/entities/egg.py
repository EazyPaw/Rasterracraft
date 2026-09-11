from src.server.entities.thrown_item import ThrownItem, ThrownItemSkeleton
from src.server.entity_registry import register_entity


@register_entity(persistent=False)
class Egg(ThrownItem):
    entity_id = "egg"
    translation_key = "item.egg.name"
    _texture_path = "items.egg"


class EggSkeleton(ThrownItemSkeleton):
    pass
