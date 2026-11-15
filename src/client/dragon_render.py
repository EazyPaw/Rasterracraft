"""Bounded offscreen dragon mesh rendering, with a software fallback.

One textured triangle draw handles the whole articulated model, including both
hinged membranes. It reuses the game's GL context when available, restores its
state, and reads a small RGBA target back into the existing pygame compositor.
"""
import logging
from contextlib import nullcontext

import numpy as np
import pygame


VERTEX = """#version 330
in vec3 position;
in vec2 uv;
in float shade;
out vec2 texcoord;
out float lighting;
void main() {
    gl_Position = vec4(position.x / 12.0, -position.y / 10.0, position.z / 32.0, 1.0);
    texcoord = uv;
    lighting = shade;
}
"""
FRAGMENT = """#version 330
uniform sampler2D skin;
uniform sampler2D eyes;
uniform sampler2D exploding;
uniform float death;
uniform float hurt;
in vec2 texcoord;
in float lighting;
out vec4 color;
void main() {
    vec4 base = texture(skin, texcoord);
    if (base.a < 0.1) discard;
    vec4 crack = texture(exploding, texcoord);
    if (death > 0.0 && crack.a < death) discard;
    vec3 rgb = base.rgb * lighting * vec3(0.82, 0.87, 1.0);
    rgb = mix(rgb, vec3(0.8, 0.05, 0.12), hurt * 0.5);
    rgb += texture(eyes, texcoord).rgb;
    if (death > 0.0) {
        float edge = 1.0 - smoothstep(0.0, 0.09, abs(crack.a - death));
        rgb += crack.rgb * edge * 1.5;
    }
    color = vec4(rgb, base.a);
}
"""


class DragonMeshRenderer:
    def __init__(self, resources, context=None, *, software=False):
        self.context, self.owns_context = context, context is None
        self.backend = "software"
        self.size = None
        self._closed = False
        self._gpu_objects = []
        sheets = [resources.get_texture_img("entity.enderdragon." + key)
                  for key in ("dragon", "dragon_eyes", "dragon_exploding")]
        self._pixels = [np.concatenate((pygame.surfarray.array3d(s), pygame.surfarray.array_alpha(s)[:, :, None]), axis=2)
                        for s in sheets]
        if not software:
            try:
                import moderngl
                self.gl = moderngl
                if self.context is None:
                    self.context = moderngl.create_standalone_context(require=330)
                with self._activate():
                    self.program = self.context.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
                    self._gpu_objects.append(self.program)
                    self.buffer = self.context.buffer(reserve=256 * 1024, dynamic=True)
                    self.vao = self.context.vertex_array(self.program, [(self.buffer, "3f 2f 1f", "position", "uv", "shade")])
                    self._gpu_objects.extend((self.buffer, self.vao))
                    self.textures = []
                    for unit, sheet in enumerate(sheets):
                        texture = self.context.texture(sheet.get_size(), 4, pygame.image.tobytes(sheet, "RGBA"))
                        texture.filter = moderngl.NEAREST, moderngl.NEAREST
                        self.textures.append(texture)
                        self._gpu_objects.append(texture)
                        self.program[("skin", "eyes", "exploding")[unit]].value = unit
                    self.backend = "gpu"
            except Exception:
                logging.warning("Dragon GPU renderer unavailable; using bounded software rendering", exc_info=True)
                self.release()
                self._closed = False

    def _activate(self):
        # Borrowed contexts are already active on the render thread. Entering
        # and exiting them would detach the compositor's native SDL context.
        return self.context if self.owns_context and self.context is not None else nullcontext()

    def release(self):
        if self._closed:
            return
        self._closed = True
        try:
            with self._activate():
                for obj in reversed(self._gpu_objects):
                    obj.release()
                if getattr(self, "framebuffer", None) is not None:
                    self.framebuffer.release()
                if getattr(self, "color_target", None) is not None:
                    self.color_target.release()
                    self.depth_target.release()
        except Exception:
            logging.debug("Could not release an expired dragon GL context", exc_info=True)
        if self.owns_context and self.context is not None:
            try:
                self.context.release()
            except Exception:
                pass
        self._gpu_objects.clear()

    def _target(self, ppb):
        size = (24 * ppb, 20 * ppb)
        if size == self.size:
            return
        self.size = size
        if getattr(self, "framebuffer", None) is not None:
            self.framebuffer.release()
            self.color_target.release()
            self.depth_target.release()
        self.color_target = self.context.texture(size, 4)
        self.depth_target = self.context.depth_renderbuffer(size)
        self.framebuffer = self.context.framebuffer((self.color_target,), self.depth_target)
        self._readback = bytearray(size[0] * size[1] * 4)
        self._surface = pygame.image.frombuffer(self._readback, size, "RGBA")

    def draw(self, vertices, ppb=16, death=0, hurt=0):
        ppb = max(4, min(24, int(ppb)))
        if self.backend == "gpu":
            with self._activate():
                self._target(ppb)
                viewport = self.context.viewport
                with self.context.scope(framebuffer=self.framebuffer, enable_only=self.gl.DEPTH_TEST,
                                         textures=tuple((texture, i) for i, texture in enumerate(self.textures))):
                    for unit, texture in enumerate(self.textures):
                        texture.use(location=unit)
                    self.context.viewport = (0, 0, *self.size)
                    self.framebuffer.clear(0, 0, 0, 0, depth=1)
                    self.buffer.write(vertices.tobytes())
                    self.program["death"].value = min(.999, max(0, death))
                    self.program["hurt"].value = float(hurt)
                    self.vao.render(vertices=len(vertices))
                    self.framebuffer.read_into(self._readback, components=4, alignment=1)
                self.context.viewport = viewport
                rect = self._surface.get_bounding_rect()
                return self._surface.subsurface(rect).copy(), rect, self.size
        # Keep fallback raster work independent of zoom; it remains textured,
        # articulated and depth-tested instead of replacing the dragon sprite.
        return self._software(vertices, min(10, ppb), death, hurt)

    def _software(self, vertices, ppb, death, hurt):
        width, height = 24 * ppb, 20 * ppb
        pixels = np.zeros((width, height, 4), dtype=np.uint8)
        depth = np.full(width * height, np.inf, dtype=np.float32)
        data = vertices.copy().reshape(-1, 3, 6)
        data[:, :, 0] = data[:, :, 0] * ppb + width / 2
        data[:, :, 1] = -data[:, :, 1] * ppb + height / 2
        skin, eyes, exploding = self._pixels
        a, b, c = data[:, 0, :2], data[:, 1, :2], data[:, 2, :2]
        det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
        low = np.maximum(0, np.floor(data[:, :, :2].min(axis=1)).astype(int))
        high = np.minimum((width - 1, height - 1), np.ceil(data[:, :, :2].max(axis=1)).astype(int))
        valid = (abs(det) >= .3) & np.all(high >= low, axis=1)
        data, low, high, det = data[valid], low[valid], high[valid], det[valid]
        # Rasterize similarly sized triangle boxes in NumPy batches. Hundreds
        # of tiny face-by-face Python loops were much slower than the pixels.
        buckets = np.ceil(np.log2(high - low + 1)).astype(int)
        for bucket in np.unique(buckets, axis=0):
            selection = np.all(buckets == bucket, axis=1)
            triangles, origins = data[selection], low[selection]
            bounds = high[selection]
            determinants = det[selection, None, None]
            bw, bh = 2 ** bucket
            xx = origins[:, 0, None, None] + np.arange(bw, dtype=np.float32)[None, :, None]
            yy = origins[:, 1, None, None] + np.arange(bh, dtype=np.float32)[None, None, :]
            a, b, c = (triangles[:, i, :2, None, None] for i in range(3))
            dx, dy = xx + .5 - c[:, 0], yy + .5 - c[:, 1]
            u = ((b[:, 1] - c[:, 1]) * dx + (c[:, 0] - b[:, 0]) * dy) / determinants
            v = ((c[:, 1] - a[:, 1]) * dx + (a[:, 0] - c[:, 0]) * dy) / determinants
            w = 1 - u - v
            inside = ((u >= 0) & (v >= 0) & (w >= 0)
                      & (xx <= bounds[:, 0, None, None]) & (yy <= bounds[:, 1, None, None]))
            ti, xi, yi = np.nonzero(inside)
            if not len(ti):
                continue
            weights = np.column_stack((u[inside], v[inside], w[inside]))
            fragments = np.einsum("ni,nij->nj", weights, triangles[ti])
            tx = (fragments[:, 3] * skin.shape[0]).astype(int) % skin.shape[0]
            ty = (fragments[:, 4] * skin.shape[1]).astype(int) % skin.shape[1]
            color, crack = skin[tx, ty].copy(), exploding[tx, ty]
            opaque = (color[:, 3] >= 26) & ((death <= 0) | (crack[:, 3] / 255 >= death))
            x, y = origins[ti, 0] + xi, origins[ti, 1] + yi
            ids = x * height + y
            z = fragments[:, 2]
            np.minimum.at(depth, ids[opaque], z[opaque])
            visible = opaque & (z <= depth[ids])
            light = fragments[:, 5, None]
            rgb = color[:, :3].astype(np.float32) * light * (.82, .87, 1)
            rgb = rgb * (1 - hurt * .5) + np.array((204, 13, 31)) * hurt * .5 + eyes[tx, ty, :3]
            if death > 0:
                edge = np.maximum(0, 1 - abs(crack[:, 3] / 255 - death) / .09)
                rgb += crack[:, :3] * edge[:, None] * 1.5
            color[:, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
            pixels[x[visible], y[visible]] = color[visible]
        surface = pygame.image.frombuffer(pixels.transpose(1, 0, 2).copy().tobytes(), (width, height), "RGBA")
        rect = surface.get_bounding_rect()
        return surface.subsurface(rect).copy(), rect, (width, height)
