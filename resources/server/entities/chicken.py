# Commented and arranged by ChatGPT
import math
import random

from resources.client.entity_skeleton import BodyPart, Pose
from resources.server.entities.animal import (
    Animal,
    AnimalSkeleton,
    crop_rotated_body,
    crop_x_side,
)
from resources.server.entities.item import Item
from resources.server.entity_AI import ChickenAI
from resources.server.entity_registry import register_entity
from resources.server.item_class import ItemStack
from resources.server.materials import COOKED_CHICKEN, EGG, FEATHER, RAW_CHICKEN
from resources.server.utils import client_method


@register_entity
class Chicken(Animal):
    entity_id = "chicken"
    translation_key = "entity.Chicken.name"
    tempt_items = frozenset({"wheat_seeds", "pumpkin_seeds", "melon_seeds"})
    panic_speed_modifier = 1.4
    sounds = {
        "ambient": "mob.chicken.say",
        "hurt": "mob.chicken.hurt",
        "death": "mob.chicken.hurt",
        "egg": "mob.chicken.plop",
        "step": "mob.chicken.step",
    }

    def __init__(self, x: float, y: float, world, z: int = 0):
        super().__init__(x, y, world, z)
        self.entity_id = "chicken"
        self.width = 0.4
        self.height = 0.7
        self.max_health = 4.0
        self.health = self.max_health
        self.move_speed = 0.25
        self.movement_acceleration = 0.05
        self.egg_time = random.randint(6000, 12000)
        self.finish_animal_init(ChickenAI)

    def update_ai(self) -> None:

        if not self.on_ground and self.motion.y < 0.0:
            self.motion.y *= 0.6
        super().update_ai()
        if not self.is_baby:
            self.egg_time -= 1
            if self.egg_time <= 0:
                self.world.spawn_entity(
                    Item(
                        self.x + self.width * 0.5,
                        self.y + 0.2,
                        self.world,
                        ItemStack(EGG(), 1),
                        self.z,
                    )
                )
                server = getattr(self.world, "server", None)
                if server is not None and not self.silent:
                    server.broadcast_sound(self.sounds["egg"], self.x, self.y, self.z)
                self.egg_time = random.randint(6000, 12000)

    def get_synced_data(self) -> dict:
        data = super().get_synced_data()
        data["flap_speed"] = 0.0 if self.on_ground else 1.0
        return data

    def get_persistent_data(self) -> dict:
        data = super().get_persistent_data()
        data["egg_time"] = int(self.egg_time)
        return data

    def read_persistent_data(self, data: dict) -> None:
        super().read_persistent_data(data)
        self.egg_time = max(1, int(data.get("egg_time", self.egg_time)))

    def get_drops(self):
        if self.is_baby:
            return []
        meat = COOKED_CHICKEN() if self.was_burning_when_killed() else RAW_CHICKEN()
        drops = [ItemStack(meat, 1)]
        feathers = random.randint(0, 2)
        if feathers:
            drops.append(ItemStack(FEATHER(), feathers))
        return drops


class ChickenSkeleton(AnimalSkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(entity, "entity.chicken", client=client)
        self.size = 1.0
        self.model_width = 0.8
        body = crop_rotated_body(self.texture, (0, 9), (6, 8, 6))
        head = crop_x_side(self.texture, (0, 0), (4, 6, 3))
        beak = crop_x_side(self.texture, (14, 0), (4, 2, 2))
        wattle = crop_x_side(self.texture, (14, 4), (2, 2, 2))
        leg = crop_x_side(self.texture, (26, 0), (3, 5, 3))
        wing = crop_x_side(self.texture, (24, 13), (1, 4, 6))
        self._base_anchors = {
            "back_leg": (0.29375, 0.3125),
            "front_leg": (0.49375, 0.3125),
            "body": (0.12, 0.6875),
            "wing": (0.2225, 0.5875),
            "head": (0.61375, 0.75),
            "beak": (0.7525, 0.7475),
            "wattle": (0.7125, 0.6275),
        }
        self.body = {
            "back_leg": BodyPart(
                "back_leg", leg, self._base_anchors["back_leg"], (1.5, 0), layer=0
            ),
            "body": BodyPart("body", body, self._base_anchors["body"], (0, 0), layer=1),
            "front_leg": BodyPart(
                "front_leg", leg, self._base_anchors["front_leg"], (1.5, 0), layer=2
            ),
            "wing": BodyPart("wing", wing, self._base_anchors["wing"], (1, 1), layer=3),
            "head": BodyPart(
                "head", head, self._base_anchors["head"], (1.5, 3), layer=4
            ),
            "beak": BodyPart("beak", beak, self._base_anchors["beak"], (1, 1), layer=5),
            "wattle": BodyPart(
                "wattle", wattle, self._base_anchors["wattle"], (1, 1), layer=5
            ),
        }
        self._visual_center = (0.4, 0.35)
        self.conv_size()

    def apply_pose(self, speed: float) -> None:
        flip = self.facing == self.LEFT
        moving = speed > 0.015
        swing = math.sin(self.walk_time) * (28.0 if moving else 0.0)
        flap = float(getattr(self.entity, "flap_speed", 0.0))
        wing_angle = math.sin(self.walk_time * 1.8) * 28.0 * flap
        for name in ("body", "head", "beak", "wattle"):
            pivot = self.body[name].target_pivot
            angle = (
                float(getattr(self.entity, "look_angle", 0.0)) * 0.25
                if name == "head"
                else 0.0
            )
            self.body[name].set_pose(
                Pose(
                    self.pose_anchor(name, self._base_anchors[name], flip),
                    pivot,
                    angle,
                    True,
                    flip,
                )
            )
        self.body["back_leg"].set_pose(
            Pose(
                self.pose_anchor("back_leg", self._base_anchors["back_leg"], flip),
                (1.5, 0),
                swing,
                True,
                flip,
            )
        )
        self.body["front_leg"].set_pose(
            Pose(
                self.pose_anchor("front_leg", self._base_anchors["front_leg"], flip),
                (1.5, 0),
                -swing,
                True,
                flip,
            )
        )
        self.body["wing"].set_pose(
            Pose(
                self.pose_anchor("wing", self._base_anchors["wing"], flip),
                (1, 1),
                wing_angle,
                True,
                flip,
            )
        )

    def draw(self):
        old_size = self.size
        self.size = old_size * self._age_scale
        try:
            super(AnimalSkeleton, self).draw()
        finally:
            self.size = old_size
