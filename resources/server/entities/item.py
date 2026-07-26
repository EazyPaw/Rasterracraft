# Commented and arranged by ChatGPT
import random

from resources.server.entities.collectible import CollectibleEntity
from resources.server.entity_registry import register_entity
from resources.server.item_class import ItemStack


@register_entity(summonable=False)
class Item(CollectibleEntity):
    entity_id = "item"
    blocks_block_placement = False
    merge_radius = 1.5
    merge_interval = 40
    escape_speed = 0.1

    def __init__(self, x, y, world, item: ItemStack, z: int = 0):
        super().__init__(x, y, world)
        self.entity_id = "item"
        self.item = item
        self.z = z
        self.width = 0.25
        self.height = 0.25
        self.gravity = 0.035
        self.drag_vertical = 0.88
        self.air_friction = 0.82
        self.damping = self.air_friction
        self.motion.x = random.uniform(-0.075, 0.075)
        self.motion.y = random.uniform(0.08, 0.15)

    @classmethod
    def create_from_save(cls, data: dict, world):
        from resources.server.materials import get_material_by_id

        item_data = data.get("data", {}).get("item", {})
        material = get_material_by_id(item_data.get("id", "air"))
        stack = ItemStack(
            material,
            max(0, int(item_data.get("amount", 0))),
            dict(item_data.get("nbt", {})),
        )
        return cls(
            float(data.get("x", 0.0)),
            float(data.get("y", 0.0)),
            world,
            stack,
            int(data.get("z", 0)),
        )

    def get_persistent_data(self) -> dict:
        return {
            **super().get_persistent_data(),
            "item": {
                "id": str(self.item.material.name_id),
                "amount": int(self.item.amount),
                "nbt": dict(self.item.nbt),
            },
        }

    def read_persistent_data(self, data: dict) -> None:
        super().read_persistent_data(data)

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        return super()._is_block_solid(x, y, self.z)

    def _get_block_at(self, x: float, y: float, z: int = 0):
        return super()._get_block_at(x, y, self.z)

    def move_update(self):
        if not self.advance_collectible_lifetime():
            return
        pickup_delayed = self.tick_pickup_delay()
        self.escape_solid_block()
        super().move_update()
        if self.age % self.merge_interval == 0:
            self.merge_nearby_items()
        if self.removed:
            return
        if pickup_delayed:
            return
        player = self.get_pickup_player()
        if player is not None:
            self.pick_up(player)

    def escape_solid_block(self) -> bool:
        return super().escape_solid_block()

    def can_merge_with(self, other) -> bool:
        return (
            isinstance(other, Item)
            and other is not self
            and not self.removed
            and not other.removed
            and self.z == other.z
            and not self.item.is_empty()
            and not other.item.is_empty()
            and self.item.is_stackable_with(other.item, require_full_fit=False)
            and self.item.amount < self.item.max_stack_size
        )

    def merge_nearby_items(self) -> None:
        entities = tuple(getattr(self.world, "entities", {}).values())
        for other in entities:
            if not self.can_merge_with(other):
                continue
            if self.calc_entity_distance(other) > self.merge_radius:
                continue
            capacity = self.item.max_stack_size - self.item.amount
            transferred = min(capacity, other.item.amount)
            if transferred <= 0:
                continue
            self.item.amount += transferred
            other.item.amount -= transferred
            self.age = min(self.age, other.age)
            self.pickup_delay = max(self.pickup_delay, other.pickup_delay)
            if other.item.amount <= 0:
                self.world.remove_entity(other)
            if self.item.amount >= self.item.max_stack_size:
                return

    def pick_up(self, player) -> bool:
        if self.pickup_delay > 0 or not self.is_pickup_candidate(player):
            return False
        before = self.item.amount
        player.give_item_stack(self.item)
        if self.item.amount != before:
            self.world.server.broadcast_sound("random.pop", self.x, self.y, self.z)
        if self.item.amount <= 0:
            self.world.remove_entity(self)
        return True

    def get_hurt_sound(self, damage_type, actual_damage: float) -> None:
        return None

    def update(self):
        super().update()


# 负责物品渲染的类在 client_entity.py 中的 ItemEntityRenderer
