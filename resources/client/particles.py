import logging
import math
import random
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING

import pygame

from resources.server.particles import BLOCK, Particle, get_particle_by_id

if TYPE_CHECKING:
    from resources.client.client_main import Client
    from resources.client.render.renderer import Render
    from resources.server.block_class import Block
    from resources.server.location import Location


class ParticleManager:
    """
    客户端粒子运行时管理器。

    粒子的定义、材质、更新和绘制逻辑都在 resources.server.particles 的粒子
    子类里；这里只负责接包、保存存活粒子、碰撞查询和纹理缓存。
    """

    def __init__(self, client: 'Client'):
        self.client = client
        self.particles: list[Particle] = []
        self.max_particles = 700
        self._lock = threading.RLock()

        self._scaled_texture_cache: OrderedDict[tuple[pygame.Surface, int, int], pygame.Surface] = OrderedDict()
        self._block_fragment_cache: OrderedDict[tuple[pygame.Surface, int, int, int], tuple[pygame.Surface, ...]] = OrderedDict()
        self._max_scaled_cache = 512
        self._max_fragment_cache = 192

    def handle_packet(self, packet: dict) -> None:
        """处理服务器发来的粒子包，并交给对应粒子子类生成客户端实体。"""
        particle_id = packet.get("particle_id")
        if not isinstance(particle_id, str):
            logging.warning(f"Invalid Particle ID {particle_id}")
            return

        try:
            particle_cls = get_particle_by_id(particle_id)
        except ValueError:
            logging.warning(f"Unknown Particle ID {particle_id}")
            return

        particle = particle_cls.from_packet(packet)
        particle.spawn_from_packet(self)

    def spawn(
        self,
        particle_id: str,
        x: float,
        y: float,
        *,
        z: int = 0,
        motion: tuple[float, float] = (0.0, 0.0),
        texture: pygame.Surface | None = None,
        size_: float | None = None,
        lifetime: int | None = None,
        rotation_speed: float | None = None,
    ) -> Particle | None:
        """客户端本地生成一个普通粒子，主要供特效内部复用。"""
        try:
            particle_cls = get_particle_by_id(particle_id)
        except ValueError:
            return None

        particle = particle_cls.from_values(float(x), float(y), int(z), motion=motion)
        if not particle.setup_client_state(
            self,
            texture=texture,
            size_=size_,
            lifetime=lifetime,
            rotation_speed=rotation_speed,
        ):
            return None
        self.add_particle(particle)
        return particle

    def add_particle(self, particle: Particle) -> None:
        """加入一个已经完成客户端初始化的粒子实体。"""
        with self._lock:
            self.particles.append(particle)
            overflow = len(self.particles) - self.max_particles
            if overflow > 0:
                del self.particles[:overflow]

    def spawn_block_break(self, block: 'Block', location: 'Location', count: int = 18) -> None:
        """
        根据方块和格子位置生成破碎碎片。

        方块破坏粒子刻意固定在整数格内；普通粒子则保留服务器传来的浮点坐标。
        """
        if block is None or getattr(block, "block_id", None) == "air":
            return

        fragments = self._get_block_fragments(block)
        if not fragments:
            return

        block_x = math.floor(location.x)
        block_y = math.floor(location.y)
        cx = block_x + 0.5
        cy = block_y + 0.5
        z = int(location.z or 0)

        for _ in range(count):
            px = block_x + random.uniform(0.12, 0.88)
            py = block_y + random.uniform(0.12, 0.88)
            away_x = px - cx
            away_y = py - cy
            length = max(math.hypot(away_x, away_y), 0.001)
            burst = random.uniform(0.03, 0.11)
            jitter_x = random.uniform(-0.04, 0.04)
            jitter_y = random.uniform(0.01, 0.10)
            motion = (
                away_x / length * burst + jitter_x,
                away_y / length * burst + jitter_y,
            )
            particle = BLOCK.from_values(
                px,
                py,
                z,
                motion=motion,
                data={"block_id": block.block_id},
            )
            if particle.setup_client_state(self, texture=random.choice(fragments)):
                self.add_particle(particle)

    def update(self) -> None:
        """更新所有粒子，并移除死亡或离玩家太远的粒子。"""
        with self._lock:
            if not self.particles:
                return

            alive: list[Particle] = []
            for particle in self.particles:
                particle.update(self)
                if particle.alive and self._is_near_player(particle):
                    alive.append(particle)
            self.particles = alive

    def draw(self, render: 'Render', z_filter: int | None = None) -> None:
        """绘制当前存活的粒子，可按前景/背景层筛选。"""
        with self._lock:
            if not self.particles:
                return
            particles = tuple(self.particles)

        for particle in particles:
            if z_filter is not None and int(getattr(particle, "z", 0)) != int(z_filter):
                continue
            particle.draw(self, render)

    def move_with_collision(self, particle: Particle) -> None:
        """带碰撞移动粒子，供 Particle.update 调用。"""
        collided_x = self._sweep_particle_x(particle)
        collided_y = self._sweep_particle_y(particle)
        collision = particle.collision

        if (collided_x or collided_y) and collision.die_on_contact:
            particle.age = particle.lifetime
            return

        if collided_x:
            particle.motion_x = -particle.motion_x * collision.restitution
            particle.motion_y *= collision.drag
            if abs(particle.motion_x) < 0.003:
                particle.motion_x = 0.0

        if collided_y:
            particle.motion_y = -particle.motion_y * collision.restitution
            particle.motion_x *= collision.drag
            if abs(particle.motion_y) < 0.003:
                particle.motion_y = 0.0

    def _sweep_particle_x(self, particle: Particle) -> bool:
        """沿 X 轴扫描碰撞。"""
        dx = particle.motion_x
        if dx == 0.0:
            return False

        radius = particle.collision.radius
        target_x = particle.x + dx
        start_edge = particle.x + radius if dx > 0 else particle.x - radius
        end_edge = target_x + radius if dx > 0 else target_x - radius
        start_cell = math.floor(start_edge)
        end_cell = math.floor(end_edge)
        step = 1 if dx > 0 else -1

        if start_cell == end_cell:
            particle.x = target_x
            return False

        for cell_x in range(start_cell + step, end_cell + step, step):
            if self._collides_at(cell_x, particle.y - radius, particle.y + radius, particle.z):
                if dx > 0:
                    particle.x = cell_x - radius - 0.001
                else:
                    particle.x = cell_x + 1.0 + radius + 0.001
                return True

        particle.x = target_x
        return False

    def _sweep_particle_y(self, particle: Particle) -> bool:
        """沿 Y 轴扫描碰撞。"""
        dy = particle.motion_y
        if dy == 0.0:
            return False

        radius = particle.collision.radius
        target_y = particle.y + dy
        start_edge = particle.y + radius if dy > 0 else particle.y - radius
        end_edge = target_y + radius if dy > 0 else target_y - radius
        start_cell = math.floor(start_edge)
        end_cell = math.floor(end_edge)
        step = 1 if dy > 0 else -1

        if start_cell == end_cell:
            particle.y = target_y
            return False

        for cell_y in range(start_cell + step, end_cell + step, step):
            if self._collides_at_y(particle.x - radius, particle.x + radius, cell_y, particle.z):
                if dy > 0:
                    particle.y = cell_y - radius - 0.001
                else:
                    particle.y = cell_y + 1.0 + radius + 0.001
                return True

        particle.y = target_y
        return False

    def _collides_at(self, block_x: int, y_min: float, y_max: float, z: int) -> bool:
        """检查某个 X 列和 Y 范围内是否有碰撞箱。"""
        for block_y in range(math.floor(y_min), math.floor(y_max) + 1):
            try:
                block = self.client.client_world.get_block(block_x, block_y, z)
                getter = getattr(block, "get_collision_box", None)
                shape = getter() if callable(getter) else getattr(block, "collision_box", ())
                local_min_y = y_min - block_y
                local_max_y = y_max - block_y
                if any(box.max_y > local_min_y and box.min_y < local_max_y
                       for box in shape):
                    return True
            except (IndexError, AttributeError, TypeError, ValueError):
                continue
        return False

    def _collides_at_y(self, x_min: float, x_max: float, block_y: int, z: int) -> bool:
        """检查某个 Y 行和 X 范围内是否有碰撞箱。"""
        for block_x in range(math.floor(x_min), math.floor(x_max) + 1):
            try:
                block = self.client.client_world.get_block(block_x, block_y, z)
                getter = getattr(block, "get_collision_box", None)
                shape = getter() if callable(getter) else getattr(block, "collision_box", ())
                if any(box.max_x > x_min - block_x and box.min_x < x_max - block_x
                       for box in shape):
                    return True
            except (IndexError, AttributeError, TypeError, ValueError):
                continue
        return False

    def _is_block_solid(self, x: int, y: int, z: int) -> bool:
        """判断指定格子是否有碰撞形状（兼容旧方法名）。"""
        try:
            block = self.client.client_world.get_block(x, y, z)
            getter = getattr(block, "get_collision_box", None)
            shape = getter() if callable(getter) else getattr(block, "collision_box", ())
            return bool(shape)
        except (IndexError, AttributeError, TypeError, ValueError):
            return False

    def _is_near_player(self, particle: Particle) -> bool:
        """检查粒子是否在玩家附近。"""
        player = self.client.client_player
        if player is None:
            return True
        return abs(particle.x - player.x) < 96 and abs(particle.y - player.y) < 64

    def _get_block_fragments(self, block: 'Block') -> tuple[pygame.Surface, ...]:
        """将方块纹理切成小碎片，并缓存结果。"""
        try:
            texture = block.get_texture(32)
        except Exception:
            texture = None
        if texture is None:
            return ()

        grid = 4
        key = (texture, texture.get_width(), texture.get_height(), grid)
        cached = self._block_fragment_cache.get(key)
        if cached is not None:
            self._block_fragment_cache.move_to_end(key)
            return cached

        width, height = texture.get_size()
        cell_w = max(1, width // grid)
        cell_h = max(1, height // grid)
        fragments: list[pygame.Surface] = []
        for gy in range(grid):
            for gx in range(grid):
                rect = pygame.Rect(gx * cell_w, gy * cell_h, cell_w, cell_h)
                rect = rect.clip(texture.get_rect())
                if rect.width > 0 and rect.height > 0:
                    fragments.append(texture.subsurface(rect).copy().convert_alpha())

        result = tuple(fragments)
        self._block_fragment_cache[key] = result
        if len(self._block_fragment_cache) > self._max_fragment_cache:
            self._block_fragment_cache.popitem(last=False)
        return result

    def get_scaled_texture(self, texture: pygame.Surface, scale: float) -> pygame.Surface:
        """按原始贴图尺寸和缩放倍数获取粒子材质缓存。"""
        width = max(1, round(texture.get_width() * scale))
        height = max(1, round(texture.get_height() * scale))
        key = (texture, width, height)
        cached = self._scaled_texture_cache.get(key)
        if cached is not None:
            self._scaled_texture_cache.move_to_end(key)
            return cached

        scaled = pygame.transform.scale(texture, (width, height)).convert_alpha()
        self._scaled_texture_cache[key] = scaled
        if len(self._scaled_texture_cache) > self._max_scaled_cache:
            self._scaled_texture_cache.popitem(last=False)
        return scaled
