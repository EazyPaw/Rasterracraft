"""Side-view projections of the 1.8.9 ModelCreeper and ModelSpider atlases."""
import math
import time

import pygame

from src.client.entity_skeleton import BodyPart, EntitySkeleton, Pose
from src.server.utils import client_method


class MonsterSkeleton(EntitySkeleton):
    def _crop(self, uv):
        return self.texture.subsurface(uv).copy()

    def _animate_clock(self):
        now = time.perf_counter()
        dt = max(0.0, min(0.1, now - self._last_frame))
        self._last_frame = now
        speed = abs(float(self.entity.motion.x))
        if getattr(self.entity, "climbing", False):
            speed = max(speed, abs(float(self.entity.motion.y)))
        self._limb_swing += dt * speed * 20 * 4
        return min(0.8, speed * 4)

    def _apply(self, poses, instant=False):
        for name, pose in poses.items():
            self.body[name].set_pose(pose)
            if instant:
                self.body[name].tick(1.0)


class CreeperSkeleton(MonsterSkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, "entity.creeper.creeper", entity)
        self._visual_center = (entity.width / 2, 13 / 16)
        self._last_frame = time.perf_counter()
        self._limb_swing = 0.0
        self._flash_key = None
        # ModelBox side faces only. Authored height: 26 px.
        self._uvs = {"head": (0, 8, 8, 8), "body": (16, 20, 4, 12)}
        self._head_sides = {1: self._crop((0, 8, 8, 8)),
                            0: self._crop((16, 8, 8, 8))}
        self._head_side = None
        for i in range(4):
            self._uvs[f"leg{i}"] = (0, 20, 4, 6)
        for name, uv in self._uvs.items():
            layer = (0 if name in {"leg0", "leg2"} else
                     3 if name.startswith("leg") else 2 if name == "body" else 4)
            self.body[name] = BodyPart(name, self._crop(uv), (0, 0), (0, 0), layer=layer)
        self._pose(0.0, instant=True)
        self.conv_size()

    def _pose(self, amount, instant=False):
        direction = 1 if self.entity.facing == 1 else -1
        side = int(direction > 0)
        if side != self._head_side:
            self._head_side = side
            self._uvs["head"] = (0 if side else 16, 8, 8, 8)
            self.body["head"].set_source_texture(self._head_sides[side])
            self._flash_key = None
        cx = self.entity.width / 2
        intensity = max(0.0, float(getattr(self.entity, "fuse_ticks", 0)) /
                        max(1, int(getattr(self.entity, "fuse_time", 30)) - 2))
        # RenderCreeper.preRenderCallback: horizontal pulse and fourth-power swell.
        pulse = 1.0 + math.sin(intensity * 100) * intensity * 0.01
        swell = min(1.0, intensity) ** 4
        sx, sy = (1 + swell * 0.4) * pulse, (1 + swell * 0.1) / pulse
        poses = {
            "body": Pose((cx, 18 / 16 * sy), (2, 0)),
            "head": Pose((cx, 18 / 16 * sy), (4, 8),
                         direction * float(self.entity.look_angle), flip_x=direction < 0),
        }
        for i in range(4):
            offset = -4 if i < 2 else 4
            phase = math.pi if i in (1, 2) else 0
            angle = math.degrees(math.cos(self._limb_swing * 0.6662 + phase) * 1.4 * amount)
            poses[f"leg{i}"] = Pose((cx + direction * offset / 16 * sx, 6 / 16 * sy),
                                      (2, 0), direction * angle)
        flash = int(intensity * 10) % 2 == 1
        powered = bool(getattr(self.entity, "powered", False))
        key = (flash, powered)
        if key != self._flash_key:
            self._flash_key = key
            armor = (self.client.resources_manager.get_texture_img("entity.creeper.creeper_armor")
                     if powered else None)
            for name, part in self.body.items():
                overlay = None
                if flash:
                    overlay = part.original_texture.copy()
                    overlay.fill((180, 180, 180, 255), special_flags=pygame.BLEND_RGBA_MULT)
                    overlay.fill((100, 100, 100, 0), special_flags=pygame.BLEND_RGB_ADD)
                elif armor is not None:
                    overlay = armor.subsurface(self._uvs[name]).copy()
                    overlay.fill((100, 140, 180, 255), special_flags=pygame.BLEND_RGBA_MULT)
                part.set_overlay_texture(overlay)
        for part in self.body.values():
            part.render_scale = sx
            part.vertical_scale = sy / sx
        self._apply(poses, instant)

    def update(self):
        self._pose(self._animate_clock())
        super().update()


class SpiderSkeleton(MonsterSkeleton):
    @client_method
    def __init__(self, entity, client=None):
        super().__init__(client, "entity.spider.spider", entity)
        self._visual_center = (entity.width / 2, 9 / 16)
        self._last_frame = time.perf_counter()
        self._limb_swing = 0.0
        # ModelSpider: head(32,4) 8x8x8, neck(0,0) 6x6x6,
        # abdomen(0,12) 10x8x12, legs(18,0) 16x2x2.
        for i in range(8):
            name = f"leg{i}"
            self.body[name] = BodyPart(name, self._crop((20, 2, 16, 2)),
                (0, 0), (1, 1), layer=0 if i % 2 == 0 else 4)
        for name, uv, pivot in (("body", (0, 22, 12, 8), (6, 4)),
                                ("neck", (0, 6, 6, 6), (3, 3)),
                                ("head", (32, 12, 8, 8), (4, 4))):
            self.body[name] = BodyPart(name, self._crop(uv), (0, 0), pivot, layer=2)
        eyes = client.resources_manager.get_texture_img("entity.spider_eyes")
        self._head_sides = {1: self._crop((32, 12, 8, 8)),
                            0: self._crop((48, 12, 8, 8))}
        self._eye_sides = {1: eyes.subsurface((32, 12, 8, 8)).copy(),
                           0: eyes.subsurface((48, 12, 8, 8)).copy()}
        self._head_side = None
        self._pose(0.0, instant=True)
        self.conv_size()

    def _pose(self, amount, instant=False):
        direction = 1 if self.entity.facing == 1 else -1
        side = int(direction > 0)
        if side != self._head_side:
            self._head_side = side
            self.body["head"].set_source_texture(self._head_sides[side])
            self.body["head"].set_overlay_texture(self._eye_sides[side])
        cx = self.entity.width / 2
        poses = {
            "body": Pose((cx - direction * 9 / 16, 9 / 16), (6, 4), flip_x=direction < 0),
            "neck": Pose((cx, 9 / 16), (3, 3)),
            "head": Pose((cx + direction * 7 / 16, 9 / 16), (4, 4),
                         direction * float(self.entity.look_angle)),
        }
        # Project ModelSpider's four yaw pairs onto X/Y, then solve each
        # straight leg against the ground. A common scale cannot keep all
        # eight feet grounded because their projected angles differ.
        phases = (0, math.pi, math.pi / 2, math.pi * 1.5)
        for i in range(8):
            pair, side = i // 2, i % 2
            phase = self._limb_swing * 0.6662 + phases[pair] + side * math.pi
            joint_x = pair - 1.5 + (side - 0.5) * 0.5
            foot_x = (-11, -5.5, 5.5, 11)[pair] + (side - 0.5) * 1.5
            foot_x += math.sin(phase) * amount * 3.0
            lift = max(0.0, math.cos(phase)) * amount * 3.0
            angle = math.atan2(lift - 9, direction * (foot_x - joint_x))
            # The UV strip is 16x2 with pivot (1,1): the far lower
            # corner, rather than its centerline, must land at Y=0.
            self.body[f"leg{i}"].render_scale = (9 - lift) / (
                -15 * math.sin(angle) + abs(math.cos(angle)))
            poses[f"leg{i}"] = Pose((cx + direction * joint_x / 16, 9 / 16),
                                      (1, 1), math.degrees(angle))
        self._apply(poses, instant)

    def update(self):
        self._pose(self._animate_clock())
        super().update()
