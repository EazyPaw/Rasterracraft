# Commented and arranged by ChatGPT

from src.server.entities.thrown_item import ThrownItem, ThrownItemSkeleton
from src.server.entity_registry import register_entity


@register_entity(persistent=False)
class SnowBall(ThrownItem):
    entity_id = "snowball"
    translation_key = "entity.Snowball.name"
    _texture_path = "items.snowball"

    def on_hit_entity(self, result):
        if getattr(result.target, "entity_id", "") == "blaze":
            result.target.apply_damage(3.0, self.damage_type, source=self.get_owner() or self)
            return True
        return super().on_hit_entity(result)


class SnowBallSkeleton(ThrownItemSkeleton):
    pass


Snowball = SnowBall
