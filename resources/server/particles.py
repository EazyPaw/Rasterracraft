import logging
import math
import os
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from resources.server.block_class import Block
from resources.server.location import Location, decide_x_or_loc
from resources.server.utils import client_method

if os.environ.get('PYCRAFT_CLIENT') == '1':
    import pygame

if TYPE_CHECKING:
    from resources.client.particles import ParticleManager
    from resources.client.render.renderer import Render


@dataclass(frozen=True)
class CollisionSettings:
    """粒子的碰撞参数。"""

    enabled: bool = False
    radius: float = 0.035
    drag: float = 0.65
    restitution: float = 0.12
    die_on_contact: bool = False


class Particle:
    """
    服务端和客户端共用的粒子基类。

    新增普通粒子时，像方块一样继承这个类并重写类属性即可：
        class FLAME(Particle):
            particle_id = "minecraft:flame"
            _texture_path = "particle.flame"
            lifetime_ticks = (12, 18)
            size = (0.06, 0.10)
            gravity = -0.002

    服务端实例只负责携带生成位置、数量和附加数据；客户端收到包后会用
    同一个粒子子类补齐纹理、寿命、大小，并调用被 @client_method 标注的方法。
    """

    particle_id = "minecraft:generic"
    name = "generic"
    _texture_path = "particle.generic_0"
    _texture_paths: tuple[str, ...] = ()

    lifetime_ticks: tuple[int, int] = (20, 30)
    size: tuple[float, float] = (0.08, 0.12)
    gravity: float = 0.0
    linear_acceleration: tuple[float, float] = (0.0, 0.0)
    linear_drag: float = 0.0
    collision: CollisionSettings = CollisionSettings()
    rotation_speed_range: tuple[float, float] = (-8.0, 8.0)
    animation_frame_ticks: int = 0
    animation_loop: bool = False

    def __init__(
        self,
        x_loc: float | Location = 0.0,
        y: float | None = None,
        z: int | None = None,
        *,
        count: int = 1,
        motion: tuple[float, float] = (0.0, 0.0),
        data: dict | None = None,
    ):
        x, y, z = decide_x_or_loc(x_loc, y, z)
        self.x = float(x)
        self.y = float(0.0 if y is None else y)
        self.z = int(0 if z is None else z)
        self.count = max(1, int(count))
        self.motion = (float(motion[0]), float(motion[1]))
        self.data = data or {}

        # 以下字段只在客户端粒子实体上使用。
        self.motion_x = self.motion[0]
        self.motion_y = self.motion[1]
        self.actual_size = self.size[0]
        self.lifetime = self.lifetime_ticks[0]
        self.texture = None
        self.texture_frames = ()
        self.age = 0
        self.rotation = 0.0
        self.rotation_speed = 0.0

    @classmethod
    def from_values(
        cls,
        x: float,
        y: float,
        z: int,
        *,
        count: int = 1,
        motion: tuple[float, float] = (0.0, 0.0),
        data: dict | None = None,
    ) -> 'Particle':
        """绕过子类自定义构造器，从网络包里的通用字段创建粒子。"""
        particle = cls.__new__(cls)
        Particle.__init__(particle, x, y, z, count=count, motion=motion, data=data)
        return particle

    @classmethod
    def from_packet(cls, packet: dict) -> 'Particle':
        """从服务器粒子包恢复为对应的粒子子类实例。"""
        motion = packet.get("motion") or [0.0, 0.0]
        return cls.from_values(
            float(packet.get("x", 0.0)),
            float(packet.get("y", 0.0)),
            int(packet.get("z", 0)),
            count=max(1, int(packet.get("count", 1))),
            motion=(float(motion[0]), float(motion[1])),
            data=packet.get("data") or {},
        )

    def to_packet(self) -> dict:
        """编码为网络包，保留浮点坐标，避免普通粒子被吸附到整数格。"""
        return {
            "__class__": "Particle",
            "particle_id": self.particle_id,
            "x": float(self.x),
            "y": float(self.y),
            "z": int(self.z),
            "count": int(self.count),
            "motion": [float(self.motion[0]), float(self.motion[1])],
            "data": self.data,
        }

    @property
    def alive(self) -> bool:
        """粒子是否仍在生命周期内。"""
        return self.age < self.lifetime

    @classmethod
    def get_texture_paths(cls) -> tuple[str, ...]:
        """返回该粒子可随机使用的材质列表。"""
        if cls._texture_paths:
            return cls._texture_paths
        if cls._texture_path:
            return (cls._texture_path,)
        return ()

    @classmethod
    @client_method
    def get_texture(cls, client=None):
        """获取一个粒子材质，供客户端生成粒子实体时调用。"""
        paths = cls.get_texture_paths()
        if not paths:
            return None
        return client.resources_manager.get_texture_img(random.choice(paths))

    @client_method
    def setup_client_state(
        self,
        manager: 'ParticleManager',
        *,
        texture=None,
        size_: float | None = None,
        lifetime: int | None = None,
        rotation_speed: float | None = None,
        client=None,
    ) -> bool:
        """补齐客户端渲染和模拟所需的运行时状态。"""
        texture_paths = type(self).get_texture_paths()
        if texture is None and self.animation_frame_ticks > 0 and texture_paths:
            self.texture_frames = tuple(
                client.resources_manager.get_texture_img(path)
                for path in texture_paths
            )
            texture = self.texture_frames[0]
        elif texture is None:
            texture = type(self).get_texture(client=client)
        if texture is None:
            return False

        self.texture = texture
        self.motion_x, self.motion_y = self.motion
        self.actual_size = size_ if size_ is not None else random.uniform(*self.size)
        self.lifetime = lifetime if lifetime is not None else random.randint(*self.lifetime_ticks)
        self.rotation = random.uniform(0.0, 360.0)
        self.rotation_speed = (
            rotation_speed
            if rotation_speed is not None
            else random.uniform(*self.rotation_speed_range)
        )
        self.age = 0
        return True

    @client_method
    def spawn_from_packet(self, manager: 'ParticleManager', client=None) -> None:
        """按网络包中的 count 在客户端生成粒子实体。"""
        for _ in range(self.count):
            particle = type(self).from_values(
                self.x,
                self.y,
                self.z,
                motion=self.motion,
                data=dict(self.data),
            )
            if particle.setup_client_state(manager, client=client):
                manager.add_particle(particle)

    @client_method
    def update(self, manager: 'ParticleManager', client=None) -> None:
        """更新粒子的速度、位置、碰撞和生命周期。"""
        self.age += 1
        if not self.alive:
            return

        if self.texture_frames and self.animation_frame_ticks > 0:
            frame = self.age // self.animation_frame_ticks
            if self.animation_loop:
                frame %= len(self.texture_frames)
            else:
                frame = min(frame, len(self.texture_frames) - 1)
            self.texture = self.texture_frames[frame]

        self.motion_x += self.linear_acceleration[0]
        self.motion_y += self.linear_acceleration[1] - self.gravity

        if self.linear_drag:
            drag = max(0.0, 1.0 - self.linear_drag)
            self.motion_x *= drag
            self.motion_y *= drag

        if self.collision.enabled:
            manager.move_with_collision(self)
        else:
            self.x += self.motion_x
            self.y += self.motion_y

        self.rotation = (self.rotation + self.rotation_speed) % 360.0

    @client_method
    def draw(self, manager: 'ParticleManager', render: 'Render', client=None) -> None:
        """按世界坐标和光照绘制粒子。"""
        if self.texture is None:
            return

        sx, sy = render.trans_world_location((self.x, self.y))
        margin = render.block_size
        if sx < -margin or sx > render.SCREEN_WIDTH + margin:
            return
        if sy < -margin or sy > render.SCREEN_HEIGHT + margin:
            return

        pixel_size = max(1, int(self.actual_size * render.block_size))
        texture = manager.get_scaled_texture(self.texture, pixel_size)
        tint = render.get_world_light_tint(self.x, self.y)
        texture = render.get_tinted_surface(texture, tint)
        dest = texture.get_rect(center=(sx, sy))
        render.screen.blit(texture, dest)


class TextureParticle(Particle):
    """使用普通粒子材质的基类。"""

    particle_id = None


class GENERIC(TextureParticle):
    particle_id = "minecraft:generic"
    name = "generic"
    _texture_paths = tuple(f"particle.generic_{i}" for i in range(8))


class SMOKE(TextureParticle):
    particle_id = "minecraft:smoke"
    name = "smoke"
    _texture_paths = tuple(f"particle.big_smoke_{i}" for i in range(12))
    lifetime_ticks = (28, 46)
    size = (0.12, 0.22)
    gravity = -0.001
    linear_drag = 0.02


class FLAME(TextureParticle):
    particle_id = "minecraft:flame"
    name = "flame"
    _texture_path = "particle.flame"
    lifetime_ticks = (10, 18)
    size = (0.06, 0.10)
    gravity = -0.004
    linear_drag = 0.01


class HEART(TextureParticle):
    particle_id = "minecraft:heart"
    name = "heart"
    _texture_path = "particle.heart"
    lifetime_ticks = (28, 36)
    size = (0.18, 0.24)
    gravity = -0.002
    linear_drag = 0.01


class SPLASH(TextureParticle):
    particle_id = "minecraft:splash"
    name = "splash"
    _texture_paths = tuple(f"particle.splash_{i}" for i in range(4))
    lifetime_ticks = (8, 14)
    # 旧尺寸在 64px 方块下只有 4~7px，且 splash 贴图本身透明像素较多，
    # 雨天几乎不可见。保持轻量的同时放大到可辨识的水花尺寸。
    size = (0.11, 0.20)
    # A light gravity and drag turn the rain impact motion into a short arc.
    # Weather spawning gives it enough upward speed to remain above the
    # surface for the whole animation.
    gravity = 0.01
    linear_drag = 0.025
    collision = CollisionSettings(enabled=False)
    animation_frame_ticks = 2
    animation_loop = False


class BlockParticle(Particle):
    """方块碎片粒子基类，材质来自方块本身而不是粒子贴图。"""

    particle_id = None
    _texture_path = None
    lifetime_ticks = (10, 18)
    size = (0.07, 0.12)
    gravity = 0.035
    linear_drag = 0.035
    collision = CollisionSettings(enabled=True, radius=0.035, drag=0.55, restitution=0.16)

    @client_method
    def spawn_from_packet(self, manager: 'ParticleManager', client=None) -> None:
        """从方块 ID 还原方块材质，并生成方块破碎碎片。"""
        from resources.server.blocks import get_block_by_id

        block_id = self.data.get("block_id")
        if not isinstance(block_id, str):
            logging.warning(f"Invalid Block ID {block_id}")
            return

        try:
            block = get_block_by_id(block_id)
        except ValueError:
            return

        location = Location(client.client_world, math.floor(self.x), math.floor(self.y), self.z)
        block.location = location
        manager.spawn_block_break(block, location, count=self.count)



class SPRINT_STEP(BlockParticle):
    """疾跑脚步扬起的灰尘粒子。

    使用脚下方块的碎片材质，短寿命、小尺寸、轻微上浮，
    模拟玩家疾跑时脚底扬起的尘土效果。
    重写 spawn_from_packet 以在服务端传来的实际坐标处生成粒子，
    而不是被吸附到整数方块格。
    """
    particle_id = "minecraft:sprint_step"
    name = "sprint_step"
    _texture_paths = None
    lifetime_ticks = (6, 14)
    size = (0.04, 0.09)
    gravity = 0.02
    collision = CollisionSettings(enabled=True, radius=0.025, drag=0.45, restitution=0.05)
    linear_drag = 0.025

    def __init__(
        self,
        x: float,
        y: float,
        z: float ,
        *,
        count: int = 18,
        motion: tuple[float, float] = (0.0, 0.0),
        data: dict | None = None,
    ):
        super().__init__(
            x,
            y,
            z,
            count=count,
            motion=motion,
            data=data,
        )

    @client_method
    def spawn_from_packet(self, manager: 'ParticleManager', client=None) -> None:
        """在服务端传来的实际坐标处生成方块碎片粒子。

        与 BlockParticle 不同，不会把坐标吸附到整数格——
        疾跑粒子应该在玩家脚底（浮点坐标）生成。
        """
        from resources.server.blocks import get_block_by_id

        block_id = self.data.get("block_id")
        if not isinstance(block_id, str):
            return

        try:
            block = get_block_by_id(block_id)
        except ValueError:
            return

        # 草方块等需要世界/生物群系信息的纹理必须拥有位置，否则
        # get_texture 会在访问 location.x 时失败，导致疾跑粒子整批消失。
        block.location = Location(
            client.client_world,
            math.floor(self.x),
            math.floor(self.y),
            int(self.z),
        )
        fragments = manager._get_block_fragments(block)
        if not fragments:
            return

        for _ in range(self.count):
            # 在服务端坐标基础上加微量随机偏移，让粒子看起来更自然
            px = self.x + random.uniform(-0.05, 0.05)
            py = self.y + random.uniform(-0.02, 0.04)
            particle = SPRINT_STEP.from_values(
                px, py, self.z,
                motion=self.motion,
                data=dict(self.data),
            )
            if particle.setup_client_state(manager, texture=random.choice(fragments)):
                manager.add_particle(particle)



class BLOCK(BlockParticle):
    particle_id = "minecraft:block"
    name = "block"

    def __init__(
        self,
        block_or_x: Block | float,
        location_or_y: Location | float | None = None,
        z: int | None = None,
        *,
        count: int = 18,
        motion: tuple[float, float] = (0.0, 0.0),
        data: dict | None = None,
    ):
        if isinstance(block_or_x, Block) and isinstance(location_or_y, Location):
            # 方块碎片是例外：它表示某个格子的方块，生成位置固定到格子坐标。
            super().__init__(
                math.floor(location_or_y.x),
                math.floor(location_or_y.y),
                location_or_y.z,
                count=count,
                data={"block_id": block_or_x.block_id},
            )
            return

        super().__init__(
            block_or_x,
            location_or_y,
            z,
            count=count,
            motion=motion,
            data=data,
        )




_PARTICLE_REGISTRY: dict[str, type[Particle]] | None = None


def _build_particle_id_cache() -> dict[str, type[Particle]]:
    """遍历 Particle 子类树，构建 particle_id 到粒子子类的缓存。"""
    cache: dict[str, type[Particle]] = {}

    def collect(cls):
        for subclass in cls.__subclasses__():
            particle_id = subclass.__dict__.get("particle_id")
            if particle_id is not None:
                cache[particle_id] = subclass
            collect(subclass)

    collect(Particle)
    return cache


def get_particle_by_id(particle_id: str) -> type[Particle]:
    """根据粒子 ID 获取粒子子类。"""
    global _PARTICLE_REGISTRY
    if _PARTICLE_REGISTRY is None:
        _PARTICLE_REGISTRY = _build_particle_id_cache()

    particle_cls = _PARTICLE_REGISTRY.get(particle_id)
    if particle_cls is not None:
        return particle_cls
    raise ValueError(f"Unknown particle ID: {particle_id}")


# 兼容旧代码中的命名；新代码建议直接使用 Particle / BLOCK。
ParticleEffect = Particle
BlockBreakParticleEffect = BLOCK
