"""Side-view ModelEnderman: original UVs, long limbs and carrying/scream poses."""

import math
import time

import pygame

from src.client.entity_skeleton import BodyPart, EntitySkeleton, Pose
from src.server.blocks import get_block_by_id
from src.server.location import Location
from src.server.utils import client_method


class EndermanSkeleton(EntitySkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, "entity.enderman.enderman", entity)
        self._visual_center = (entity.width / 2, 1.45)
        self._last_frame = time.perf_counter()
        self._walk_time = 0.0
        self._teleport_revision = getattr(entity, "teleport_revision", 0)
        self._carried_key = None
        cx = entity.width / 2
        # ModelEnderman's 30 px legs overlap the torso by 3 px; its
        # shoulders sit 37 px above the feet, with arms extending 28 px down.
        self.body = {
            "back_arm": BodyPart("back_arm", self._crop((60, 2, 2, 30)),
                                 (cx, 37 / 16), (1, 2), layer=0),
            "back_leg": BodyPart("back_leg", self._crop((60, 2, 2, 30)),
                                 (cx, 30 / 16), (1, 0), layer=1),
            "body": BodyPart("body", self._crop((32, 20, 4, 12)),
                             (cx, 39 / 16), (2, 0), layer=2),
            "front_leg": BodyPart("front_leg", self._crop((58, 2, 2, 30)),
                                  (cx, 30 / 16), (1, 0), layer=3),
            "front_arm": BodyPart("front_arm", self._crop((58, 2, 2, 30)),
                                  (cx, 37 / 16), (1, 2), layer=4),
            "carried_block": BodyPart("carried_block", pygame.Surface((16, 16), pygame.SRCALPHA),
                                      (cx, 1.1), (8, 8), layer=5, show=False),
            "head": BodyPart("head", self._head_texture(),
                             (cx, 38 / 16), (4, 8), layer=6),
        }
        eyes = client.resources_manager.get_texture_img("entity.enderman.enderman_eyes")
        self.body["head"].set_overlay_texture(eyes.subsurface((8, 8, 8, 8)).copy())
        self.body["carried_block"].render_scale = 0.6
        self._pose(0.0, instant=True)
        self.conv_size()

    def _crop(self, uv):
        return self.texture.subsurface(uv).copy()

    def _head_texture(self):
        # ModelEnderman also renders bipedHeadwear (atlas origin 0, 16).
        # The base head has two transparent bottom rows; the jaw lives here.
        head = self._crop((8, 8, 8, 8))
        head.blit(self._crop((8, 24, 8, 8)), (0, 0))
        return head

    def _update_interpolation(self):
        revision = getattr(self.entity, "teleport_revision", 0)
        if revision != self._teleport_revision:
            self._teleport_revision = revision
            self._prev_x = self._target_x = self._render_x = self.entity.x
            self._prev_y = self._target_y = self._render_y = self.entity.y
        super()._update_interpolation()

    def _update_carried_texture(self):
        data = getattr(self.entity, "carried_block", None)
        key = repr(data)
        if key == self._carried_key:
            return
        self._carried_key = key
        if data:
            block = get_block_by_id(data["id"])
            block.write_nbt(data.get("nbt", {}))
            block.location = Location(self.client.client_world, math.floor(self.entity.x),
                                      math.floor(self.entity.y), self.entity.z)
            self.body["carried_block"].set_source_texture(block.get_texture(16, client=self.client))

    def _pose(self, swing, *, instant=False):
        direction = 1 if self.entity.facing == 1 else -1
        cx = self.entity.width / 2
        carrying = bool(getattr(self.entity, "carried_block", None))
        screaming = bool(getattr(self.entity, "screaming", False))
        # ModelEnderman halves the biped walk swing, then clamps to +/-0.4 rad.
        swing = max(-math.degrees(0.4), min(math.degrees(0.4), swing))
        arm = direction * math.degrees(0.5) if carrying else swing
        t = time.perf_counter()
        jitter = math.sin(t * 43) * 0.018 if screaming else 0.0
        poses = {
            "back_arm": Pose((cx, 37 / 16), (1, 2), arm if carrying else -swing),
            "back_leg": Pose((cx, 30 / 16), (1, 0), swing),
            "body": Pose((cx, 39 / 16), (2, 0)),
            "front_leg": Pose((cx, 30 / 16), (1, 0), -swing),
            "front_arm": Pose((cx, 37 / 16), (1, 2), arm),
            "head": Pose((cx + jitter, (38 + (5 if screaming else 0)) / 16), (4, 8),
                         direction * float(self.entity.look_angle), flip_x=direction < 0),
            "carried_block": Pose((cx + direction * 0.78, 0.93), (8, 8), visible=carrying),
        }
        for name, pose in poses.items():
            part = self.body[name]
            part.set_pose(pose)
            if instant:
                part.tick(1.0)

    def update(self):
        now = time.perf_counter()
        dt = min(0.1, now - self._last_frame)
        self._last_frame = now
        speed = abs(float(self.entity.motion.x))
        self._walk_time += dt * min(18.0, speed * 45.0)
        swing = math.sin(self._walk_time) * min(23.0, speed * 140.0)
        self._update_carried_texture()
        self._pose(swing)
        super().update()


class EndermiteSkeleton(EntitySkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, "entity.endermite", entity)
        self._visual_center = (entity.width / 2, entity.height / 2)
        # ModelEnderMite's four sections: width/height/depth and atlas origins.
        self._sections = ((2, 3, 0, 2), (5, 4, 0, 10), (1, 3, 0, 15), (1, 2, 0, 19))
        self._pose()
        self.conv_size()

    def _pose(self):
        direction = 1 if self.entity.facing == 1 else -1
        age = time.perf_counter() * 20
        offset = 0.0
        for i, (depth, height, u, v) in enumerate(self._sections):
            key = str(i)
            if key not in self.body:
                self.body[key] = BodyPart(key, self.texture.subsurface((u, v, depth, height)).copy(),
                                          (0, 0), (depth / 2, height), layer=i)
            phase = age * 0.9 + i * 0.15 * math.pi
            wiggle = math.sin(phase) * math.pi * 0.1 * abs(i - 2) / 16
            x = self.entity.width / 2 + direction * (4.5 - offset - depth / 2) / 16
            self.body[key].set_pose(Pose((x, wiggle), (depth / 2, height),
                                        math.degrees(math.cos(phase) * math.pi * 0.01 * (1 + abs(i - 2))),
                                        flip_x=direction < 0))
            offset += depth

    def update(self):
        self._pose()
        super().update()
