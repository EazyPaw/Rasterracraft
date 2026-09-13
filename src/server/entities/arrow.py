"""Minecraft-style arrows fired by bows."""

from __future__ import annotations

import math
import random

import pygame

from src.client.entity_skeleton import EntitySkeleton
from src.server.damange_type import ARROW as ARROW_DAMAGE
from src.server.entities.projectile import Projectile, ProjectileHitResult
from src.server.entity_registry import register_entity
from src.server.item_class import ItemStack
from src.server.location import Vector
from src.server.utils import client_method


@register_entity(summonable=False, persistent=True)
class Arrow(Projectile):
    """A recoverable arrow with velocity-scaled damage and block embedding."""

    entity_id = "arrow"
    translation_key = "entity.Arrow.name"
    _texture_path = "entity.arrow"
    damage_type = ARROW_DAMAGE
    default_speed = 3.0
    default_inaccuracy = 0.0075
    air_drag = 0.99
    water_drag = 0.60
    max_lifetime = 72_000
    max_in_ground_lifetime = 1200

    def __init__(
        self,
        x: float,
        y: float,
        world,
        z: int = 0,
        *,
        owner=None,
        base_damage: float = 2.0,
        critical: bool = False,
        punch_level: int = 0,
        flame: bool = False,
        pickup: str = "allowed",
    ):
        super().__init__(x, y, world, z, owner=owner)
        self.width = 0.5
        self.height = 0.25
        self.gravity = 0.05
        self.base_damage = max(0.0, float(base_damage))
        self.critical = bool(critical)
        self.punch_level = max(0, int(punch_level))
        self.impact_knockback = self.punch_level * 0.6
        self.flame = bool(flame)
        if self.flame:
            # Flame bows ignite the arrow itself for five seconds in 1.8.9.
            # Avoid syncing here: the world sends the complete spawn packet.
            self.fire_ticks = 100
        self.pickup = (
            pickup if pickup in {"allowed", "creative_only", "disallowed"}
            else "disallowed"
        )
        self.shake_time = 0
        self.in_ground_life = 0
        self._embedded_block_signature = None

    def get_synced_data(self) -> dict:
        data = super().get_synced_data()
        data.update(
            {
                "critical": self.critical,
                "shake_time": self.shake_time,
                "flame": self.flame,
            }
        )
        return data

    def get_persistent_data(self) -> dict:
        data = super().get_persistent_data()
        data.update(
            {
                "base_damage": self.base_damage,
                "critical": self.critical,
                "punch_level": self.punch_level,
                "flame": self.flame,
                "pickup": self.pickup,
                "shake_time": self.shake_time,
                "in_ground_life": self.in_ground_life,
                "embedded_block_signature": self._embedded_block_signature,
            }
        )
        return data

    def read_persistent_data(self, data: dict) -> None:
        super().read_persistent_data(data)
        self.base_damage = max(0.0, float(data.get("base_damage", 2.0)))
        self.critical = bool(data.get("critical", False))
        self.punch_level = max(0, int(data.get("punch_level", 0)))
        self.impact_knockback = self.punch_level * 0.6
        self.flame = bool(data.get("flame", False))
        pickup = str(data.get("pickup", "disallowed"))
        self.pickup = (
            pickup if pickup in {"allowed", "creative_only", "disallowed"}
            else "disallowed"
        )
        self.shake_time = max(0, int(data.get("shake_time", 0)))
        self.in_ground_life = max(0, int(data.get("in_ground_life", 0)))
        self._embedded_block_signature = data.get("embedded_block_signature")

    def _impact_damage(self) -> int:
        damage = math.ceil(
            min(
                2_147_483_647.0,
                math.hypot(self.motion.x, self.motion.y) * self.base_damage,
            )
        )
        if self.critical and damage > 0:
            damage += random.randrange(damage // 2 + 2)
        return min(2_147_483_647, damage)

    def get_impact_knockback(self, target) -> Vector | None:
        if self.punch_level <= 0 or abs(self.motion.x) <= 1.0e-12:
            return None
        return Vector(math.copysign(self.punch_level * 0.6, self.motion.x), 0.1)

    def on_hit_entity(self, result: ProjectileHitResult) -> bool:
        target = result.target
        owner = self.get_owner()
        callback = getattr(target, "on_projectile_hit", None)
        if callable(callback):
            callback(self, result)
        if self.is_burning():
            ignite = getattr(target, "set_seconds_on_fire", None)
            if callable(ignite):
                ignite(5.0)
            else:
                target.fire_ticks = max(int(getattr(target, "fire_ticks", 0)), 100)
        target.apply_damage(
            self._impact_damage(),
            self.damage_type,
            source=owner or self,
            knockback=self.get_impact_knockback(target),
        )
        return True

    def on_hit_block(self, result: ProjectileHitResult) -> bool:
        callback = getattr(result.target, "on_projectile_hit", None)
        if callable(callback):
            callback(self, result)
        self._embedded_block_signature = self._block_state_signature(result.target)
        self.embed_in_block(result)
        self.shake_time = 7
        self.in_ground_life = 0
        self.critical = False
        server = getattr(self.world, "server", None)
        if server is not None:
            server.broadcast_sound(
                f"random.bowhit",
                result.x,
                result.y,
                self.z,
            )
        return False

    @staticmethod
    def _block_state_signature(block):
        serializer = getattr(block, "to_dict", None)
        if callable(serializer):
            try:
                return repr(serializer())
            except (AttributeError, TypeError, ValueError):
                pass
        return getattr(block, "block_id", None)

    def _embedded_block_still_holds_arrow(self) -> bool:
        position = self.embedded_block_position
        if position is None:
            return False
        block_x, block_y, block_z = position
        if not self._get_collision_boxes(block_x, block_y, block_z):
            return False
        if self._embedded_block_signature is None:
            return True
        current = self._get_block_at(block_x, block_y, block_z)
        return self._block_state_signature(current) == self._embedded_block_signature

    def _try_pickup(self) -> bool:
        if self.pickup == "disallowed" or self.shake_time > 0:
            return False
        server = getattr(self.world, "server", None)
        for player in tuple(getattr(server, "players", ())):
            if (
                getattr(player, "world", None) is not self.world
                or int(getattr(player, "z", 0)) != self.z
                or float(getattr(player, "health", 0.0)) <= 0.0
                or not self._aabb_overlaps_entity(
                    self.x, self.y, self.width, self.height, player, padding=0.2
                )
            ):
                continue
            creative = (
                getattr(getattr(player, "gamemode", None), "name_id", "")
                == "creative"
            )
            if self.pickup == "creative_only":
                if not creative:
                    continue
                self.discard()
                return True
            from src.server.materials import ARROW

            pickup_stack = ItemStack(ARROW(), 1)
            if player.give_item_stack(pickup_stack) == 1:
                if server is not None:
                    server.broadcast_sound("random.pop", self.x, self.y, self.z)
                self.discard()
                return True
        return False

    def update(self) -> None:
        if self.fire_ticks > 0:
            if self.in_water:
                self.clear_fire()
            else:
                self.fire_ticks -= 1
        if self.shake_time > 0:
            self.shake_time -= 1
        if self.in_ground:
            self.age += 1
            self.in_ground_life += 1
            if self.in_ground_life >= self.max_in_ground_lifetime:
                self.discard()
                return
            if not self._embedded_block_still_holds_arrow():
                self.in_ground = False
                self.embedded_block_position = None
                self._embedded_block_signature = None
                self.in_ground_life = 0
                # ``Projectile.update`` owns the flying lifetime increment.
                self.age -= 1
            elif self._try_pickup():
                return
            else:
                return
        super().update()


class ArrowSkeleton(EntitySkeleton):
    # RenderArrow (1.8.9) submits this side face with UVs covering only the
    # first 16 x 5 texels of the 32 x 32 atlas.  Modern ArrowModel keeps the
    # same 16 x 4 crossed face.  A 2D side view sees one of those crossed
    # faces; the other face and the 5 x 5 rear cap are edge-on.
    ATLAS_SIZE = (32, 32)
    MODEL_SCALE = 0.05625
    MODEL_TRANSLATE_X = -4.0
    SIDE_VERTICES = ((-8.0, -2.0), (8.0, -2.0), (8.0, 2.0), (-8.0, 2.0))
    SIDE_UVS = ((0.0, 0.0), (0.5, 0.0), (0.5, 5.0 / 32.0), (0.0, 5.0 / 32.0))

    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, "entity.arrow", entity)
        self._visual_center = (entity.width * 0.5, entity.height * 0.5)
        self._side_texture = self._bake_side_face(self.texture)
        self._rendered_texture = None
        self._render_key = None

    @classmethod
    def _bake_side_face(cls, atlas: pygame.Surface) -> pygame.Surface:
        """Rasterize the vanilla side-face UVs from the entity atlas."""
        atlas_width, atlas_height = atlas.get_size()
        # Resource packs may upscale the atlas, so UVs rather than hard-coded
        # source pixels remain authoritative.
        min_u = min(vertex[0] for vertex in cls.SIDE_UVS)
        max_u = max(vertex[0] for vertex in cls.SIDE_UVS)
        min_v = min(vertex[1] for vertex in cls.SIDE_UVS)
        max_v = max(vertex[1] for vertex in cls.SIDE_UVS)
        rect = pygame.Rect(
            round(min_u * atlas_width),
            round(min_v * atlas_height),
            max(1, round((max_u - min_u) * atlas_width)),
            max(1, round((max_v - min_v) * atlas_height)),
        )
        rect.clamp_ip(pygame.Rect(0, 0, atlas_width, atlas_height))
        face = atlas.subsurface(rect).copy()
        # Keep the authored vertex aspect ratio (16 x 4), not the atlas crop's
        # 16 x 5 texel ratio; this is what the original textured quad does.
        model_width = max(x for x, _ in cls.SIDE_VERTICES) - min(
            x for x, _ in cls.SIDE_VERTICES
        )
        model_height = max(y for _, y in cls.SIDE_VERTICES) - min(
            y for _, y in cls.SIDE_VERTICES
        )
        target_height = max(1, round(face.get_width() * model_height / model_width))
        if face.get_height() != target_height:
            face = pygame.transform.scale(face, (face.get_width(), target_height))
        return face

    def draw(self):
        render = self.client.render
        angle = float(getattr(self.entity, "look_angle", 0.0))
        shake = float(getattr(self.entity, "shake_time", 0.0))
        if shake > 0.0:
            angle += -math.sin(shake * 3.0) * shake
        # The UV face points right; pygame rotates counter-clockwise.
        model_width = max(x for x, _ in self.SIDE_VERTICES) - min(
            x for x, _ in self.SIDE_VERTICES
        )
        key = (
            max(1, round(render.block_size * model_width * self.MODEL_SCALE)),
            round(angle, 1),
        )
        if key != self._render_key:
            width = key[0]
            height = max(
                1,
                round(
                    width
                    * (
                        max(y for _, y in self.SIDE_VERTICES)
                        - min(y for _, y in self.SIDE_VERTICES)
                    )
                    / (
                        max(x for x, _ in self.SIDE_VERTICES)
                        - min(x for x, _ in self.SIDE_VERTICES)
                    )
                ),
            )
            scaled = pygame.transform.scale(self._side_texture, (width, height))
            self._rendered_texture = pygame.transform.rotate(scaled, angle)
            self._render_key = key
        texture = self._rendered_texture
        entity_center_x = self._render_x + self.entity.width * 0.5
        entity_center_y = self._render_y + self.entity.height * 0.5
        model_center_offset = self.MODEL_TRANSLATE_X * self.MODEL_SCALE
        angle_radians = math.radians(angle)
        center_x = entity_center_x + math.cos(angle_radians) * model_center_offset
        center_y = entity_center_y + math.sin(angle_radians) * model_center_offset
        tint = render.get_world_light_tint(center_x, center_y)
        texture = render.get_tinted_surface(texture, tint)
        screen_x, screen_y = render.trans_world_location((center_x, center_y))
        render.blit(
            texture,
            (
                round(screen_x - texture.get_width() * 0.5),
                round(screen_y - texture.get_height() * 0.5),
            ),
        )
