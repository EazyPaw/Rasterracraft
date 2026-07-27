# Commented and arranged by ChatGPT
import random

import pygame

from src.client.entity_skeleton import BodyPart, Pose
from src.server.blocks import AIR, DIRT
from src.server.entities.animal import (
    Animal,
    QuadrupedSkeleton,
    crop_rotated_body,
    crop_x_side,
)
from src.server.entities.item import Item
from src.server.entity_AI import SheepAI
from src.server.entity_registry import register_entity
from src.server.item_class import ItemStack
from src.server.materials import COOKED_MUTTON, RAW_MUTTON, WHITE_WOOL
from src.server.utils import client_method


@register_entity
class Sheep(Animal):
    entity_id = "sheep"
    translation_key = "entity.Sheep.name"
    tempt_items = frozenset({"wheat"})
    panic_speed_modifier = 1.25
    sounds = {
        "ambient": "mob.sheep.say",
        "hurt": "mob.sheep.say",
        "death": "mob.sheep.say",
        "shear": "mob.sheep.shear",
        "step": "mob.sheep.step",
    }
    edible_plants = frozenset({"short_grass", "fern", "tall_grass", "large_fern"})

    def __init__(self, x: float, y: float, world, z: int = 0):
        super().__init__(x, y, world, z)
        self.entity_id = "sheep"
        self.width = 0.9
        self.height = 1.3
        self.max_health = 8.0
        self.health = self.max_health
        self.move_speed = 0.23
        self.movement_acceleration = 0.05
        self.sheared = False
        self.wool_color = "white"
        self.eat_animation_ticks = 0
        self.finish_animal_init(SheepAI)

    def get_synced_data(self) -> dict:
        data = super().get_synced_data()
        data.update(
            {
                "sheared": bool(self.sheared),
                "wool_color": self.wool_color,
                "eat_animation_ticks": int(self.eat_animation_ticks),
            }
        )
        return data

    def get_persistent_data(self) -> dict:
        data = super().get_persistent_data()
        data.update({"sheared": bool(self.sheared), "wool_color": self.wool_color})
        return data

    def read_persistent_data(self, data: dict) -> None:
        super().read_persistent_data(data)
        self.sheared = bool(data.get("sheared", False))
        self.wool_color = str(data.get("wool_color", "white"))

    def _grazing_position(self):
        return (
            int(self.x + self.width * 0.5),
            int(self.y - 0.05),
            self.z,
        )

    def can_eat_grass(self) -> bool:
        x, y, z = self._grazing_position()
        block = self.world.get_block(x, y, z)
        above = self.world.get_block(x, y + 1, z)
        return block.block_id == "grass_block" or above.block_id in self.edible_plants

    def eat_grass(self) -> None:
        x, y, z = self._grazing_position()
        above = self.world.get_block(x, y + 1, z)
        if above.block_id in self.edible_plants:
            self.world.set_block(AIR(), x, y + 1, z)
        elif self.world.get_block(x, y, z).block_id == "grass_block":
            self.world.set_block(DIRT(), x, y, z)
        self.sheared = False
        if self.is_baby:
            self.set_age(min(0, self.age_ticks + 1200))

    def interact(self, player, held_stack) -> bool:
        if (
            not self.is_baby
            and not self.sheared
            and held_stack is not None
            and not held_stack.is_empty()
            and held_stack.material.name_id == "shears"
        ):
            self.sheared = True
            for _ in range(random.randint(1, 3)):
                self.world.spawn_entity(
                    Item(
                        self.x + self.width * 0.5,
                        self.y + self.height * 0.5,
                        self.world,
                        ItemStack(WHITE_WOOL(), 1),
                        self.z,
                    )
                )
            server = getattr(self.world, "server", None)
            if server is not None and not self.silent:
                server.broadcast_sound(self.sounds["shear"], self.x, self.y, self.z)
            return True
        return super().interact(player, held_stack)

    def get_drops(self):
        if self.is_baby:
            return []
        meat = COOKED_MUTTON() if self.was_burning_when_killed() else RAW_MUTTON()
        result = [ItemStack(meat, random.randint(1, 2))]
        if not self.sheared:
            result.append(ItemStack(WHITE_WOOL(), 1))
        return result


class SheepSkeleton(QuadrupedSkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(entity, "entity.sheep.sheep", client=client)
        self.model_width = 1.25
        self.configure_quadruped(
            body_uv=(28, 8),
            body_size=(8, 16, 6),
            head_uv=(0, 0),
            head_size=(6, 6, 8),
            leg_uv=(0, 16),
            leg_size=(4, 12, 4),
            body_anchor=(0.08, 1.125),
            head_anchor=(1.07, 1.1125),
            rear_leg_anchor=(0.105, 0.75),
            front_leg_anchor=(0.845, 0.75),
        )
        fur_texture = self.client.resources_manager.get_texture_img(
            "entity.sheep.sheep_fur"
        )
        fur_body = crop_rotated_body(fur_texture, (28, 8), (8, 16, 6))
        fur_head = crop_x_side(fur_texture, (0, 0), (6, 6, 6))
        fur_leg = crop_x_side(fur_texture, (0, 16), (4, 6, 4))

        fur_body = pygame.transform.scale(fur_body, (20, 10))
        fur_head = pygame.transform.scale(fur_head, (7, 7))
        fur_leg = pygame.transform.scale(fur_leg, (5, 7))

        fur_far_back = (0.10625, 0.78)
        fur_far_front = (0.84625, 0.78)
        fur_near_back = (0.10625 + 0.03, 0.78 - 0.04)
        fur_near_front = (0.84625 - 0.03, 0.78 - 0.04)
        self._base_anchors.update(
            {
                "fur_body": (-0.04, 1.30),
                "fur_head": (0.78, 1.36),
                "fur_far_back_leg": fur_far_back,
                "fur_far_front_leg": fur_far_front,
                "fur_near_back_leg": fur_near_back,
                "fur_near_front_leg": fur_near_front,
            }
        )
        fur_pivot = (2.5, 0)
        self.body.update(
            {
                "fur_far_back_leg": BodyPart(
                    "fur_far_back_leg", fur_leg, fur_far_back, fur_pivot, layer=0
                ),
                "fur_far_front_leg": BodyPart(
                    "fur_far_front_leg", fur_leg, fur_far_front, fur_pivot, layer=0
                ),
                "fur_body": BodyPart(
                    "fur_body",
                    fur_body,
                    self._base_anchors["fur_body"],
                    (0, 0),
                    layer=1,
                ),
                "fur_near_back_leg": BodyPart(
                    "fur_near_back_leg", fur_leg, fur_near_back, fur_pivot, layer=2
                ),
                "fur_near_front_leg": BodyPart(
                    "fur_near_front_leg", fur_leg, fur_near_front, fur_pivot, layer=2
                ),
                "fur_head": BodyPart(
                    "fur_head",
                    fur_head,
                    self._base_anchors["fur_head"],
                    (3.5, 3.5),
                    layer=3,
                ),
            }
        )
        self._visual_center = (0.625, 0.65)
        self.conv_size()

    def get_head_anchor(self) -> tuple[float, float]:
        remaining = int(getattr(self.entity, "eat_animation_ticks", 0))
        if remaining <= 0:
            return self._base_anchors["head"]
        progress = 1.0 if 4 <= remaining <= 36 else min(1.0, (40 - remaining) / 4.0)
        x, y = self._base_anchors["head"]
        return x + 0.12, y - 0.55 * progress

    def apply_extra_pose(self, flip: bool, swing: float) -> None:
        visible = not bool(getattr(self.entity, "sheared", False))
        head_anchor = self.get_head_anchor()
        fur_anchors = {
            "fur_far_back_leg": self._base_anchors["fur_far_back_leg"],
            "fur_far_front_leg": self._base_anchors["fur_far_front_leg"],
            "fur_body": self._base_anchors["fur_body"],
            "fur_near_back_leg": self._base_anchors["fur_near_back_leg"],
            "fur_near_front_leg": self._base_anchors["fur_near_front_leg"],
            "fur_head": (head_anchor[0], head_anchor[1]),
        }

        angles = {
            "fur_far_back_leg": swing,
            "fur_far_front_leg": -swing,
            "fur_near_back_leg": -swing,
            "fur_near_front_leg": swing,
            "fur_body": 0.0,
            "fur_head": 0.0,
        }
        for name, anchor in fur_anchors.items():
            self.body[name].set_pose(
                Pose(
                    self.pose_anchor(name, anchor, flip),
                    self.body[name].target_pivot,
                    angles[name],
                    visible,
                    flip,
                )
            )
