"""Reusable authoritative boss health display, independent of any encounter."""
from dataclasses import dataclass


@dataclass
class BossBar:
    uuid: str
    name: str
    health: float
    max_health: float
    color: str = "pink"
    active: bool = True

    @classmethod
    def from_entity(cls, entity, color="pink"):
        return cls(str(entity.uuid), entity.translation_key, float(entity.health),
                   float(entity.max_health), color, not entity.removed and entity.health > 0)

    def update_from_entity(self, entity):
        """Keep the bar's identity when its owning encounter replaces a mob."""
        self.active = entity is not None and not entity.removed and entity.health > 0
        if entity is not None:
            self.name = entity.translation_key
            self.health, self.max_health = float(entity.health), float(entity.max_health)

    def to_packet(self, world_id):
        return {"__class__": "BossState", "world_id": world_id,
                "uuid": self.uuid, "name": self.name, "color": self.color,
                "active": self.active, "health": max(0.0, float(self.health)),
                "max_health": max(1.0, float(self.max_health))}
