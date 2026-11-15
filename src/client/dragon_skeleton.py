"""Smooth packet interpolation around the original dragon's 3D bone rig."""
import math
import random
import time
from collections import deque

import pygame

from src.client.dragon_model import dragon_model
from src.client.dragon_render import DragonMeshRenderer
from src.server.dragon_geometry import wrap_degrees


class EnderDragonSkeleton:
    INTERPOLATION_DELAY = .075

    def __init__(self, entity):
        self.entity, self.client = entity, entity.client
        self._states = deque(maxlen=8)
        self._received_age = None
        self._mesh_time = -1
        self._frame = None
        self._scaled_key = None
        self._rays_surface = None
        self._ray_count = 0
        rng = random.Random(432)
        self._rays = [(rng.random() * math.tau, rng.random() * 20 + 5, rng.random() * 2 + 1)
                      for _ in range(60)]
        self.update()

    def update(self):
        entity = self.entity
        age = entity.dragon_age
        if age == self._received_age:
            return
        self._received_age = age
        state = (entity.dragon_received_at, entity.x, entity.y, entity.dragon_yaw, entity.dragon_anim,
                 entity.dragon_history, entity.dragon_death_ticks)
        if self._states and state[0] <= self._states[-1][0]:
            self._states.clear()
        self._states.append(state)

    def sample(self, now=None):
        self.update()
        now = time.perf_counter() if now is None else now
        target = now - self.INTERPOLATION_DELAY
        before = after = self._states[0]
        for state in self._states:
            after = state
            if state[0] >= target:
                break
            before = state
        alpha = max(0, min(1, (target - before[0]) / max(.001, after[0] - before[0])))
        lerp = lambda a, b: a + (b - a) * alpha
        yaw = before[3] + wrap_degrees(after[3] - before[3]) * alpha
        history = [(a[0] + wrap_degrees(b[0] - a[0]) * alpha, lerp(a[1], b[1]))
                   for a, b in zip(before[5], after[5])]
        return lerp(before[1], after[1]), lerp(before[2], after[2]), yaw, lerp(before[4], after[4]), history, lerp(before[6], after[6])

    def _drawer(self, render):
        shader = getattr(render, "_status_effect_shader", None) or getattr(render, "_portal_effect_shader", None)
        context = getattr(shader, "ctx", None)
        drawer = getattr(render, "_dragon_mesh_renderer", None)
        if drawer is None or getattr(render, "_dragon_borrowed_context", None) is not context:
            if drawer is not None:
                drawer.release()
            drawer = DragonMeshRenderer(self.client.resources_manager, context)
            render._dragon_mesh_renderer = drawer
            render._dragon_borrowed_context = context
        return drawer

    def draw(self):
        render = self.client.render
        now = time.perf_counter()
        x, y, yaw, phase, history, death_ticks = self.sample(now)
        self._render_x, self._render_y = x, y
        cx, cy = render.trans_world_location((x + 8, y + 4))
        margin = render.block_size * (40 if death_ticks else 13)
        if cx + margin < 0 or cx - margin > render.SCREEN_WIDTH or cy + margin < 0 or cy - margin > render.SCREEN_HEIGHT:
            return
        drawer = self._drawer(render)
        ppb = next((n for n in (4, 8, 12, 16, 24) if n >= render.block_size), 24)
        interval = 1 / (60 if drawer.backend == "gpu" else 24)
        if self._frame is None or now - self._mesh_time >= interval or ppb != getattr(self, "_ppb", None):
            vertices = dragon_model().pose(yaw, phase, history, y + 4, death_ticks / 200)
            self._frame, self._bounds, self._size = drawer.draw(vertices, ppb, death_ticks / 200,
                                                               float(self.entity.hurt_time > 0))
            self._mesh_time, self._ppb = now, ppb
            self._scaled_key = None
        factor = render.block_size / (self._size[0] / 24)
        key = self._frame, render.block_size
        if self._bounds.width and self._bounds.height and key != self._scaled_key:
            width = max(1, round(self._bounds.width * factor))
            height = max(1, round(self._bounds.height * factor))
            self._scaled_frame = pygame.transform.scale(self._frame, (width, height))
            self._scaled_key = key
        if self._bounds.width and self._bounds.height:
            render.blit(self._scaled_frame, (round(cx + (self._bounds.x - self._size[0] / 2) * factor),
                                              round(cy + (self._bounds.y - self._size[1] / 2) * factor)))
        if death_ticks > 0:
            self.draw_death_rays(render, (cx, cy), death_ticks / 200)

    def draw_death_rays(self, render, center, progress):
        progress = max(0, min(1, progress))
        fade = max(0, min(1, (progress - .8) / .2))
        count = min(60, math.ceil((progress + progress * progress) / 2 * 60))
        if not count or fade >= 1:
            return
        # Bake each new beam only once into a small additive light field.
        # Rotating this shared field gives smooth gradients without hundreds
        # of full-resolution polygons, and intersections accumulate light.
        ppb = 4
        if self._rays_surface is None or count < self._ray_count:
            self._rays_surface = pygame.Surface((224, 224))
            self._rays_surface.fill((0, 0, 0))
            self._ray_scratch = pygame.Surface((224, 224))
            self._ray_count = 0
        origin = pygame.Vector2(112, 112)
        for angle, length, width in self._rays[self._ray_count:count]:
            self._ray_scratch.fill((0, 0, 0))
            direction = pygame.Vector2(math.cos(angle), math.sin(angle))
            normal = pygame.Vector2(-direction.y, direction.x)
            reach, spread = length * ppb, width * ppb * .42
            for segment in range(32):
                a, b = segment / 32, (segment + 1) / 32
                intensity = 1 - (a + b) / 2
                color = (round(255 * intensity), round(255 * intensity ** 2), round(255 * intensity))
                points = (origin + direction * reach * a - normal * spread * a,
                          origin + direction * reach * b - normal * spread * b,
                          origin + direction * reach * b + normal * spread * b,
                          origin + direction * reach * a + normal * spread * a)
                pygame.draw.polygon(self._ray_scratch, color, points)
            self._rays_surface.blit(self._ray_scratch, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        self._ray_count = count
        layer = pygame.transform.rotate(self._rays_surface, -progress * 90)
        if fade:
            value = round(255 * (1 - fade))
            layer.fill((value, value, value), special_flags=pygame.BLEND_RGB_MULT)
        # Crop before zooming so a close camera never allocates a huge image.
        factor = render.block_size / ppb * (1 + fade * .4)
        left, top = center[0] - layer.get_width() * factor / 2, center[1] - layer.get_height() * factor / 2
        visible = pygame.Rect(math.floor(-left / factor), math.floor(-top / factor),
                              math.ceil(render.SCREEN_WIDTH / factor) + 2,
                              math.ceil(render.SCREEN_HEIGHT / factor) + 2).clip(layer.get_rect())
        if visible.width and visible.height:
            image = pygame.transform.scale(layer.subsurface(visible),
                                            (max(1, round(visible.width * factor)),
                                             max(1, round(visible.height * factor))))
            render.screen.blit(image, (round(left + visible.x * factor), round(top + visible.y * factor)),
                               special_flags=pygame.BLEND_RGB_ADD)
