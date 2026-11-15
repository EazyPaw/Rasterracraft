"""EntityEnderEye's 1.8.9 homing motion projected onto X/Y (no collisions)."""
import math
import random

from src.server.entity import Entity
from src.server.entity_registry import register_entity
from src.server.entities.thrown_item import ThrownItemSkeleton
from src.server.particles import PORTAL, ITEM


@register_entity(persistent=False)
class EnderEye(Entity):
    entity_id = "ender_eye"
    translation_key = "item.eyeOfEnder.name"
    attackable = receives_damage = blocks_block_placement = False

    def __init__(self, x, y, world, z=0):
        super().__init__(x, y, world)
        self.z = z
        self.width = self.height = 0.25
        self.no_physics = True
        self.age = 0
        self.target_x, self.target_y = x, y
        self.drops_eye = True

    def move_towards(self, x, y):
        dx = x - self.x
        if abs(dx) > 12:
            self.target_x = self.x + math.copysign(12, dx)
            self.target_y = self.y + 8
        else:
            self.target_x, self.target_y = x, y
        self.age = 0
        self.drops_eye = random.randrange(5) > 0

    def update(self):
        if self.removed:
            return
        self.x += self.motion.x
        self.y += self.motion.y
        dx = self.target_x - self.x
        distance = abs(dx)
        speed = abs(self.motion.x) + (distance - abs(self.motion.x)) * 0.0025
        if distance < 1:
            speed *= 0.8
            self.motion.y *= 0.8
        self.motion.x = math.copysign(speed, dx)
        self.motion.y += ((1 if self.y < self.target_y else -1) - self.motion.y) * 0.015
        self.world.spawn_particle(PORTAL(self.x, self.y, self.z, count=1))
        self.age += 1
        if self.age > 80:
            self.world.remove_entity(self)
            if self.drops_eye:
                from src.server.entities.item import Item
                from src.server.item_class import ItemStack
                from src.server.materials import get_material_by_id
                self.world.spawn_entity(Item(self.x, self.y, self.world,
                    ItemStack(get_material_by_id("ender_eye"), 1), self.z))
            else:
                self.world.spawn_particle(ITEM(self.x, self.y, self.z, count=8,
                    data={"item_id": "ender_eye"}))


class EnderEyeSkeleton(ThrownItemSkeleton):
    visual_size = 0.5
    fullbright = True
