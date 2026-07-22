import math
import random

from resources.server.entity import Entity
from resources.server.item_class import ItemStack


class Item(Entity):
    blocks_block_placement = False
    merge_radius = 1.5
    merge_interval = 40
    escape_speed = 1.0

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
        self.pickup_delay = 40
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
        self.escape_solid_block()
        super().move_update()
        if self.age % self.merge_interval == 0:
            self.merge_nearby_items()
        if self.removed:
            return
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

    def escape_solid_block(self) -> bool:
        """Push a trapped drop toward the nearest free side without teleporting."""
        if not self._check_collision_at(self.x, self.y):
            return False

        boxes = []
        min_block_x = math.floor(self.x) - 1
        max_block_x = math.floor(self.x + self.width) + 2
        min_block_y = math.floor(self.y) - 1
        max_block_y = math.floor(self.y + self.height) + 2
        for block_x in range(min_block_x, max_block_x):
            for block_y in range(min_block_y, max_block_y):
                boxes.extend(self._get_collision_boxes(block_x, block_y, self.z))
        overlapping = [
            box for box in boxes
            if box.overlaps(self.x, self.y, self.x + self.width, self.y + self.height)
        ]
        if not overlapping:
            return False

        epsilon = 0.001
        side_candidates = []
        upward_candidates = []
        for box in overlapping:
            left = box.min_x - self.width - epsilon
            right = box.max_x + epsilon
            top = box.max_y + epsilon
            side_candidates.extend((left, right))
            upward_candidates.append(top)

        for candidate_x in sorted(
            set(side_candidates), key=lambda x: abs(x - self.x)
        ):
            if not self._check_collision_at(candidate_x, self.y):
                direction = -1.0 if candidate_x < self.x else 1.0
                self.motion.x = direction * self.escape_speed
                return True
        for candidate_y in sorted(
            set(upward_candidates), key=lambda y: abs(y - self.y)
        ):
            if not self._check_collision_at(self.x, candidate_y):
                self.motion.y = max(self.escape_speed, self.motion.y)
                return True
        return False

    def can_merge_with(self, other) -> bool:
        """Return whether ``other`` can contribute to this item stack."""
        return (
            isinstance(other, Item)
            and other is not self
            and not self.removed
            and not other.removed
            and self.z == other.z
            and not self.item.is_empty()
            and not other.item.is_empty()
            and self.item.is_stackable_with(
                other.item, require_full_fit=False
            )
            and self.item.amount < self.item.max_stack_size
        )

    def merge_nearby_items(self) -> None:
        """Merge matching nearby drops, capped by the material stack limit.

        Offsets and copy rendering are client concerns; the server owns the
        single authoritative stack.  The younger age is retained so merging
        never shortens the remaining lifetime of either drop.
        """
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

    def is_pickup_candidate(self, player) -> bool:
        return (
            abs((player.x + player.width / 2) - self.x) <= 1.2
            and player.y - 0.5 <= self.y <= player.y + player.height + 0.7
        )

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
        """Dropped items take damage silently."""
        return None

    def update(self):
        super().update()

# 负责物品渲染的类在 client_entity.py 中的 ItemEntityRenderer
        
