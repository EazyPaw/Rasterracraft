import math
import random
import time

import pygame

from resources.client.entity_skeleton import BodyPart, EntitySkeleton, PlayerSkeleton
from resources.server.entity import Entity
from resources.server.entity_AI import ZombieAI
from resources.server.entity_registry import register_entity
from resources.server.item_class import ItemStack
from resources.server.materials import ROTTEN_FLESH
from resources.server.utils import client_method


@register_entity
class Zombie(Entity):
    """Server-authoritative zombie; behavior is supplied by :class:`ZombieAI`."""

    entity_id = "zombie"
    translation_key = "entity.Zombie.name"
    sounds = {
        "ambient": "mob.zombie.say",
        "hurt": "mob.zombie.hurt",
        "death": "mob.zombie.death",
    }

    def __init__(self, x: float, y: float, world, z: int = 0):
        super().__init__(float(x), float(y), world)
        self.entity_id = "zombie"
        self.z = int(z)
        self.width = 0.6
        self.height = 1.95
        self.max_health = 20.0
        self.health = self.max_health
        # ``get_move_acceleration`` now scales from this attribute, so changing
        # move_speed at runtime changes actual horizontal movement immediately.
        self.move_speed = 0.1
        self.movement_acceleration = 0.05
        self.interact_range = 1.5
        self.attack_damage = 3.0
        rotten_flesh = random.randint(0, 2)
        self.drops = (
            [ItemStack(ROTTEN_FLESH(), rotten_flesh)]
            if rotten_flesh > 0
            else []
        )
        self.ai = ZombieAI(self)

    def update_ai(self) -> None:
        self.ai.tick()


class ZombieSkeleton(PlayerSkeleton):
    """Zombie renderer kept beside Zombie, matching falling_block.py."""

    @client_method
    def __init__(self, entity, client=None):
        EntitySkeleton.__init__(self, client, "entity.zombie.zombie", entity)
        self.size = self.VISUAL_HEIGHT_BLOCKS / self.AUTHORED_HEIGHT_BLOCKS
        self._pinned = False
        self._visual_center = (
            getattr(entity, "width", 0.6) * 0.5,
            self.VISUAL_HEIGHT_BLOCKS / 2,
        )
        self.walk_time = 0.0
        self._swing_time = -1.0
        self._smoothed_head_angle = 0.0
        self._last_facing = self.facing
        self._last_update_time = time.perf_counter()
        self._last_x = entity.x
        self._last_y = entity.y
        self._current_texture_side = None
        self._held_item_key = None
        self._held_item_pivot = (0.0, 0.0)
        self._held_item_anchor = (0.5, 0.5)
        self._held_item_offset = (0.0, 0.0)
        self._held_item_scale = 0.7
        self._held_item_rotation = 0.0
        self._held_item_textures = {}
        self._held_item_pivots = {}
        self._held_item_texture_side = None
        self._build_zombie_body()
        self._apply_pose(instant=True)
        self.conv_size()

    def _build_zombie_body(self):
        """Build the legacy 64x32 zombie layout used by the bundled asset."""
        self._part_textures = {
            self.RIGHT: {
                "head": self._skin((0, 8, 8, 8)),
                "body": self._skin((16, 20, 4, 12)),
                "front_arm": self._skin((40, 20, 4, 12)),
                "back_arm": self._skin((32, 20, 4, 12)),
                "front_leg": self._skin((0, 20, 4, 12)),
                "back_leg": self._skin((16, 20, 4, 12)),
            },
            self.LEFT: {
                "head": self._skin((16, 8, 8, 8)),
                "body": self._skin((28, 20, 4, 12)),
                "front_arm": self._skin((32, 20, 4, 12)),
                "back_arm": self._skin((40, 20, 4, 12)),
                "front_leg": self._skin((16, 20, 4, 12)),
                "back_leg": self._skin((0, 20, 4, 12)),
            },
        }
        textures = self._part_textures[self.RIGHT]
        empty = pygame.Surface((1, 1), pygame.SRCALPHA)
        self.body = {
            "back_arm": BodyPart("back_arm", textures["back_arm"], (0.50, 1.50), (2, 0), layer=0),
            "back_leg": BodyPart("back_leg", textures["back_leg"], (0.50, 0.75), (2, 0), layer=1),
            "body": BodyPart("body", textures["body"], (0.50, 1.50), (2, 0), layer=2),
            "front_leg": BodyPart("front_leg", textures["front_leg"], (0.50, 0.75), (2, 0), layer=3),
            "front_arm": BodyPart("front_arm", textures["front_arm"], (0.50, 1.50), (2, 0), layer=4),
            "held_item": BodyPart("held_item", empty, (0.50, 1.05), (0.5, 0.5), layer=3, show=False),
            "head": BodyPart("head", textures["head"], (0.50, 1.50), (4, 8), layer=5),
            "head_overlay": BodyPart("head_overlay", empty, (0.50, 1.50), (4, 8), layer=6, show=False),
        }

    def _update_facing(self):
        EntitySkeleton._update_facing(self)
        if abs(getattr(self.entity.motion, "x", 0.0)) <= 0.02:
            self.facing = int(getattr(self.entity, "facing", self.facing))

    def _update_held_item_texture(self):
        self.body["held_item"].target_show = False

    def _calc_head_angle(self, direction: int) -> float:
        return direction * float(getattr(self.entity, "look_angle", 0.0))

    def _calc_walk_angles(self, direction: int) -> dict:
        angles = super()._calc_walk_angles(direction)
        if getattr(self.entity, "aggressive", False):
            attack_ticks = max(0, int(getattr(self.entity, "attack_animation_ticks", 0)))
            attack_pulse = (
                math.sin((8 - min(attack_ticks, 8)) / 8 * math.pi)
                if attack_ticks else 0.0
            )
            shamble = math.sin(self.walk_time * 0.75) * 7.0
            angles["front_arm_angle"] = direction * (82.0 + shamble - attack_pulse * 18.0)
            angles["back_arm_angle"] = direction * (76.0 - shamble - attack_pulse * 12.0)
        return angles
