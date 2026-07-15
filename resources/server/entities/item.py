import random

from resources.server.entity import Entity
from resources.server.item_class import ItemStack


class Item(Entity):
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
        self.pickup_delay = 10
        self.age = 0
        self.motion.x = random.uniform(-0.075, 0.075)
        self.motion.y = random.uniform(0.08, 0.15)

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        return super()._is_block_solid(x, y, self.z)

    def _get_block_at(self, x: float, y: float, z: int = 0):
        return super()._get_block_at(x, y, self.z)

    def move_update(self):
        self.age += 1
        if self.age > 6000:
            self.world.remove_entity(self)
            return
        super().move_update()
        if self.pickup_delay > 0:
            self.pickup_delay -= 1
            return
        for player in tuple(self.world.server.players):
            if player.world is not self.world:
                continue
            if not self.is_pickup_candidate(player):
                continue
            self.pick_up(player)
            return

    def is_pickup_candidate(self, player) -> bool:
        return (
            abs((player.x + player.width / 2) - self.x) <= 1.2
            and player.y - 0.5 <= self.y <= player.y + player.height + 0.7
        )

    def pick_up(self, player) -> bool:
        if self.pickup_delay > 0 or not self.is_pickup_candidate(player):
            return False
        self.world.server.send_client_socket(
            player,
            {"__class__": "ItemPickup", "item": {
                "id": self.item.material.name_id,
                "amount": self.item.amount,
                "nbt": self.item.nbt,
            }},
            "Forward",
        )
        self.world.remove_entity(self)
        return True
