import random

from resources.client.entity_skeleton import BodyPart, Pose
from resources.server.entities.animal import Animal, QuadrupedSkeleton, crop_x_side
from resources.server.entity_AI import CowAI
from resources.server.entity_registry import register_entity
from resources.server.item_class import ItemStack
from resources.server.materials import BUCKET, COOKED_BEEF, LEATHER, MILK_BUCKET, RAW_BEEF
from resources.server.utils import client_method


@register_entity
class Cow(Animal):
    entity_id = "cow"
    translation_key = "entity.Cow.name"
    tempt_items = frozenset({"wheat"})
    panic_speed_modifier = 2.0
    tempt_speed_modifier = 1.25
    follow_parent_speed_modifier = 1.25
    sounds = {
        "ambient": "mob.cow.say",
        "hurt": "mob.cow.hurt",
        "death": "mob.cow.hurt",
        "milk": "mob.cow.say",
        "step": "mob.cow.step",
    }

    def __init__(self, x: float, y: float, world, z: int = 0):
        super().__init__(x, y, world, z)
        self.entity_id = "cow"
        self.width = 0.9
        self.height = 1.4
        self.max_health = 10.0
        self.health = self.max_health
        self.move_speed = 0.2
        self.movement_acceleration = 0.05
        self.finish_animal_init(CowAI)

    def interact(self, player, held_stack) -> bool:
        if (
            not self.is_baby
            and held_stack is not None
            and not held_stack.is_empty()
            and held_stack.material.name_id == "bucket"
        ):
            if self._player_is_creative(player):
                player.give_item(MILK_BUCKET(), 1)
            else:
                if not player.remove_item_stack(held_stack, 1, sync=False):
                    return False
                if player.give_item(MILK_BUCKET(), 1, sync=False) != 1:
                    player.give_item(BUCKET(), 1, sync=False)
                    player.sync_inventory()
                    return False
                player.sync_inventory()
            server = getattr(self.world, "server", None)
            if server is not None and not self.silent:
                server.broadcast_sound(self.sounds["milk"], self.x, self.y, self.z)
            return True
        return super().interact(player, held_stack)

    def get_drops(self):
        if self.is_baby:
            return []
        meat_type = COOKED_BEEF if self.was_burning_when_killed() else RAW_BEEF
        result = [ItemStack(meat_type(), random.randint(1, 3))]
        leather = random.randint(0, 2)
        if leather:
            result.append(ItemStack(LEATHER(), leather))
        return result


class CowSkeleton(QuadrupedSkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(entity, "entity.cow.cow", client=client)
        self.model_width = 1.35
        self.configure_quadruped(
            body_uv=(18, 4), body_size=(12, 18, 10),
            head_uv=(0, 0), head_size=(8, 8, 6),
            leg_uv=(0, 16), leg_size=(4, 12, 4),
            body_anchor=(0.10, 1.375), head_anchor=(1.1875, 1.17),
            rear_leg_anchor=(0.325, 0.75), front_leg_anchor=(0.975, 0.75),
        )
        horn = crop_x_side(self.texture, (22, 0), (1, 3, 1))
        udder = crop_x_side(self.texture, (52, 0), (4, 6, 1))
        self._base_anchors.update({"horn": (1.08125, 1.3925), "udder": (0.38, 0.83)})
        self.body["horn"] = BodyPart("horn", horn, self._base_anchors["horn"], (0.5, 3), layer=3)
        self.body["udder"] = BodyPart("udder", udder, self._base_anchors["udder"], (0, 0), layer=1)
        self._visual_center = (0.675, 0.7)
        self.conv_size()

    def apply_extra_pose(self, flip: bool, swing: float) -> None:
        for name in ("horn", "udder"):
            self.body[name].set_pose(Pose(
                self.pose_anchor(name, self._base_anchors[name], flip),
                self.body[name].target_pivot, 0.0, True, flip,
            ))
