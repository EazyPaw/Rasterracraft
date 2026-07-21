import random

from resources.client.entity_skeleton import BodyPart, Pose
from resources.server.entities.animal import Animal, QuadrupedSkeleton, crop_x_side
from resources.server.entity_AI import PigAI
from resources.server.item_class import ItemStack
from resources.server.materials import COOKED_PORKCHOP, RAW_PORKCHOP
from resources.server.utils import client_method


class Pig(Animal):
    translation_key = "entity.Pig.name"
    tempt_items = frozenset({"carrot", "potato", "carrot_on_a_stick"})
    panic_speed_modifier = 1.25
    tempt_speed_modifier = 1.2
    sounds = {
        "ambient": "mob.pig.say",
        "hurt": "mob.pig.say",
        "death": "mob.pig.death",
        "step": "mob.pig.step",
    }

    def __init__(self, x: float, y: float, world, z: int = 0):
        super().__init__(x, y, world, z)
        self.entity_id = "pig"
        self.width = 0.9
        self.height = 0.9
        self.max_health = 10.0
        self.health = self.max_health
        self.move_speed = 0.25
        self.movement_acceleration = 0.05
        self.saddled = False
        self.finish_animal_init(PigAI)

    def get_synced_data(self) -> dict:
        data = super().get_synced_data()
        data["saddled"] = bool(self.saddled)
        return data

    def get_persistent_data(self) -> dict:
        data = super().get_persistent_data()
        data["saddled"] = bool(self.saddled)
        return data

    def read_persistent_data(self, data: dict) -> None:
        super().read_persistent_data(data)
        self.saddled = bool(data.get("saddled", False))

    def get_drops(self):
        if self.is_baby:
            return []
        meat = COOKED_PORKCHOP() if self.was_burning_when_killed() else RAW_PORKCHOP()
        return [ItemStack(meat, random.randint(1, 3))]


class PigSkeleton(QuadrupedSkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(entity, "entity.pig.pig", client=client)
        self.model_width = 1.25
        self.configure_quadruped(
            body_uv=(28, 8), body_size=(10, 16, 8),
            head_uv=(0, 0), head_size=(8, 8, 8),
            leg_uv=(0, 16), leg_size=(4, 6, 4),
            body_anchor=(0.08, 0.875), head_anchor=(1.03, 0.65),
            rear_leg_anchor=(0.305, 0.375), front_leg_anchor=(0.845, 0.375),
        )
        snout = crop_x_side(self.texture, (16, 16), (4, 3, 1))
        self._base_anchors["snout"] = (1.31125, 0.62625)
        self.body["snout"] = BodyPart("snout", snout, self._base_anchors["snout"], (0.5, 1.5), layer=4)
        self._visual_center = (0.625, 0.45)
        self.conv_size()

    def apply_extra_pose(self, flip: bool, swing: float) -> None:
        self.body["snout"].set_pose(Pose(
            self.pose_anchor("snout", self._base_anchors["snout"], flip),
            self.body["snout"].target_pivot, 0.0, True, flip,
        ))
