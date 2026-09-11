# Commented and arranged by ChatGPT

from src.server.entities.thrown_item import ThrownItem, ThrownItemSkeleton
from src.server.entity_registry import register_entity


@register_entity(persistent=False)
class SnowBall(ThrownItem):
    entity_id = "snowball"
    translation_key = "entity.Snowball.name"
    _texture_path = "items.snowball"


class SnowBallSkeleton(ThrownItemSkeleton):
    pass


Snowball = SnowBall
