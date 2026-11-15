"""ModelDragon 1.8 cuboids/UVs and its articulated neck, tail and double wings.

Only geometry lives here. The same mesh can use the GPU or software renderer;
wing membranes are actual two-sided planes with a separate hinged wing tip.
"""
import math
from functools import lru_cache

import numpy as np

from src.server.dragon_geometry import movement_offset, wrap_degrees


def transform(position=(0, 0, 0), angles=(0, 0, 0)):
    x, y, z = angles
    sx, cx, sy, cy, sz, cz = math.sin(x), math.cos(x), math.sin(y), math.cos(y), math.sin(z), math.cos(z)
    result = np.eye(4, dtype=np.float32)
    result[:3, :3] = ((cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
                      (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
                      (-sy, cy * sx, cy * cx))
    result[:3, 3] = position
    return result


class DragonModel:
    def __init__(self):
        self.bones = []
        self._vertices, self._uvs, self._normals, self._indices = [], [], [], []
        self.body = self.bone("body")
        self.box(self.body, (-12, 0, -16), (24, 24, 64), (0, 0))
        for z in (-10, 10, 30):
            self.box(self.body, (-1, -6, z), (2, 6, 12), (220, 53))
        self.neck = [self.spine("neck" + str(i)) for i in range(5)]
        self.tail = [self.spine("tail" + str(i)) for i in range(12)]
        self.head, self.jaw = self.bone("head"), self.bone("jaw")
        self.box(self.head, (-6, -1, -24), (12, 5, 16), (176, 44))
        self.box(self.head, (-8, -8, -10), (16, 16, 16), (112, 30))
        for x in (-5, 3):
            self.box(self.head, (x, -12, -4), (2, 4, 6), (0, 0))
            self.box(self.head, (x, -3, -22), (2, 2, 4), (112, 0))
        self.box(self.jaw, (-6, 0, -16), (12, 4, 16), (176, 65))
        self.sides = []
        for side in (-1, 1):
            wing, tip = self.bone(f"wing{side}"), self.bone(f"wingtip{side}")
            self.box(wing, (-56, -4, -4), (56, 8, 8), (112, 88))
            self.box(wing, (-56, 0, 2), (56, 0, 56), (-56, 88))
            self.box(tip, (-56, -2, -2), (56, 4, 4), (112, 136))
            self.box(tip, (-56, 0, 2), (56, 0, 56), (-56, 144))
            legs = []
            for rear in (False, True):
                upper, lower, foot = (self.bone(f"leg{side}:{rear}:{i}") for i in range(3))
                if rear:
                    self.box(upper, (-8, -4, -8), (16, 32, 16), (0, 0))
                    self.box(lower, (-6, -2, 0), (12, 32, 12), (196, 0))
                    self.box(foot, (-9, 0, -20), (18, 6, 24), (112, 0))
                else:
                    self.box(upper, (-4, -4, -4), (8, 24, 8), (112, 104))
                    self.box(lower, (-3, -1, -3), (6, 24, 6), (226, 138))
                    self.box(foot, (-4, 0, -12), (8, 4, 16), (144, 104))
                legs.append((upper, lower, foot))
            self.sides.append((side, wing, tip, legs))
        self.vertices = np.array(self._vertices, dtype=np.float32)
        self.normals = np.array(self._normals, dtype=np.float32)
        self.uvs = np.array(self._uvs, dtype=np.float32) / 256
        self.indices = np.array(self._indices, dtype=np.int32)
        del self._vertices, self._uvs, self._normals, self._indices

    def bone(self, name):
        self.bones.append(name)
        return len(self.bones) - 1

    def spine(self, name):
        bone = self.bone(name)
        self.box(bone, (-5, -5, -5), (10, 10, 10), (192, 104))
        self.box(bone, (-1, -9, -3), (2, 4, 6), (48, 0))
        return bone

    def box(self, bone, origin, size, texture):
        x, y, z = origin
        w, h, d = size
        u, v = texture
        corners = np.array(((x, y, z), (x + w, y, z), (x + w, y + h, z), (x, y + h, z),
                            (x, y, z + d), (x + w, y, z + d), (x + w, y + h, z + d), (x, y + h, z + d)))
        faces = (((5, 1, 2, 6), (u + d + w, v + d, u + d + w + d, v + d + h)),
                 ((0, 4, 7, 3), (u, v + d, u + d, v + d + h)),
                 ((5, 4, 0, 1), (u + d, v, u + d + w, v + d)),
                 ((2, 3, 7, 6), (u + d + w, v + d, u + d + w + w, v)),
                 ((1, 0, 3, 2), (u + d, v + d, u + d + w, v + d + h)),
                 ((4, 5, 6, 7), (u + d + w + d, v + d, u + d + w + d + w, v + d + h)))
        for indices, (u1, v1, u2, v2) in faces:
            points = corners[list(indices)]
            normal = np.cross(points[1] - points[0], points[2] - points[0]).astype(np.float32)
            length = np.linalg.norm(normal)
            if length < .001:
                continue
            normal /= length
            # TexturedQuad maps its first vertex to (u2,v1).
            uv = ((u2, v1), (u1, v1), (u1, v2), (u2, v2))
            for i in (0, 1, 2, 0, 2, 3):
                self._vertices.append((*points[i], 1))
                self._uvs.append(uv[i])
                self._normals.append(normal)
                self._indices.append(bone)

    def pose(self, yaw, phase, history=(), y=92, death=0):
        radians = math.radians
        offset = lambda i: movement_offset(history, i, yaw, y)
        reference = offset(6)
        bend = wrap_degrees(offset(5)[0] - offset(10)[0])
        middle = wrap_degrees(offset(5)[0] + bend / 2)
        f = phase * math.tau
        bob = (math.sin(f - 1) + 1)
        bob = (bob * bob + bob * 2) * .05
        matrices = np.repeat(np.eye(4, dtype=np.float32)[None], len(self.bones), axis=0)
        bank = max(-.6, min(.6, radians(-bend * 1.5)))
        torso = transform(angles=(0, 0, bank))
        matrices[self.body] = torso @ transform((0, 4, 8))
        point = np.array((0., 20., -12.))
        for i, bone in enumerate(self.neck):
            sample = offset(5 - i)
            ax = math.cos(i * .45 + f) * .15 + radians(sample[1] - reference[1]) * 7.5
            ay = radians(wrap_degrees(sample[0] - reference[0])) * 1.5
            az = -radians(wrap_degrees(sample[0] - middle)) * 1.5
            matrices[bone] = transform(point, (ax, ay, az))
            point += (-math.sin(ay) * math.cos(ax) * 10, math.sin(ax) * 10, -math.cos(ay) * math.cos(ax) * 10)
        sample = offset(0)
        matrices[self.head] = transform(point, (0, radians(wrap_degrees(sample[0] - reference[0])),
                                                -radians(wrap_degrees(sample[0] - middle))))
        matrices[self.jaw] = matrices[self.head] @ transform((0, 4, -8), ((math.sin(f) + 1) * .2, 0, 0))
        point = np.array((0., 10., 60.))
        reference = offset(11)
        wave = 0
        for i, bone in enumerate(self.tail):
            sample = offset(12 + i)
            wave += math.sin(i * .45 + f) * .05
            ay = radians(wrap_degrees(sample[0] - reference[0]) * 1.5 + 180)
            ax = wave + radians(sample[1] - reference[1]) * 7.5
            az = radians(wrap_degrees(sample[0] - middle)) * 1.5
            matrices[bone] = transform(point, (ax, ay, az))
            point += (-math.sin(ay) * math.cos(ax) * 10, math.sin(ax) * 10, -math.cos(ay) * math.cos(ax) * 10)
        for side, wing, tip, legs in self.sides:
            mirror = np.diag((side, 1, 1, 1)).astype(np.float32)
            base = torso @ mirror
            matrices[wing] = base @ transform((-12, 5, 2), (.125 - math.cos(f) * .2, .25, (math.sin(f) + .125) * .8))
            matrices[tip] = matrices[wing] @ transform((-56, 0, 0), (0, 0, -(math.sin(f + 2) + .5) * .75))
            for rear, (upper, lower, foot) in zip((False, True), legs):
                matrices[upper] = base @ transform((-16, 16, 42) if rear else (-12, 20, 2),
                                                   ((1 if rear else 1.3) + bob * .1, 0, 0))
                matrices[lower] = matrices[upper] @ transform((0, 32, -4) if rear else (0, 20, -1),
                                                             ((.5 if rear else -.5) + bob * .1, 0, 0))
                matrices[foot] = matrices[lower] @ transform((0, 31, 4) if rear else (0, 23, 0), (.75 + bob * .1, 0, 0))
        # Vanilla model coordinates are Y-down, forward=-Z. Orthographic side
        # projection preserves volume throughout a full yaw, without flipping.
        pitch = max(-.55, min(.55, radians((offset(5)[1] - offset(10)[1]) * 10)))
        root = transform(angles=(0, -radians(yaw), 0)) @ transform(angles=(-pitch, 0, 0))
        invert = np.diag((1., -1., 1., 1.)).astype(np.float32)
        root = root @ invert @ transform((0, -16 + bob * 4, -28))
        matrices = root[None] @ matrices
        assigned = matrices[self.indices]
        positions = np.einsum("nij,nj->ni", assigned, self.vertices)[:, :3] / 16
        normals = np.einsum("nij,nj->ni", assigned[:, :3, :3], self.normals)
        lighting = .50 + .50 * np.maximum(0, normals @ np.array((-.25, .85, -.45), dtype=np.float32))
        # A slight elevated view reveals both wing membranes even when level.
        c, s = math.cos(.14), math.sin(.14)
        depth = positions[:, 2].copy()
        positions[:, 2] = depth * c - positions[:, 1] * s
        positions[:, 1] = positions[:, 1] * c + depth * s
        return np.column_stack((positions, self.uvs, lighting)).astype(np.float32)


@lru_cache(maxsize=1)
def dragon_model():
    return DragonModel()
