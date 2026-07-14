import math as _math
import random as _random

from resources.client.game_mode import SurvivalMode
from resources.server.entity import Entity
from resources.server.location import Location, decide_x_or_loc
from resources.server.particles import SPRINT_STEP
from resources.server.world_class import World


class Player(Entity):
    def __init__(self, x, y, world):
        super().__init__(x, y, world)
        self.world: World = world
        self.entity_id = "player"
        self.loading_regions = []
        self.name = "Player_" + self.uuid.hex[:8]
        self.width = 0.3
        self.height = 1.8
        self.max_health = 20
        self.health = self.max_health
        self.food_level = 20
        self.saturation = 5.0
        self.experience = 0
        self.experience_level = 0
        # A client may already have PlayerMove packets queued when the server
        # teleports it.  Do not let one of those stale packets overwrite the
        # authoritative destination before the client has received the
        # Teleport packet.
        self._teleport_id = 0
        self._pending_teleport_id: int | None = None
        # 疾跑粒子节流：避免每帧都生成粒子造成刷屏
        self._sprint_particle_timer: int = 0
        self._last_sprint_particle_x: float | None = None
        self.gamemode = SurvivalMode
        self.spawn_point = 0

    def on_moving(self):
        rx = int(self.x // 16)
        for x in range(rx - self.world.server.view_distance, rx + self.world.server.view_distance + 1):
            if x not in self.loading_regions and x in self.world.regions:
                self.world.server.send_client_socket(self, self.world.regions[x])
        if self.sprinting:
            self._spawn_sprint_particles()
        else:
            self._last_sprint_particle_x = self.x
            self._sprint_particle_timer = 0

    def _spawn_sprint_particles(self) -> None:
        """疾跑时在脚底生成脚下方块的碎片粒子。

        每 3 帧生成一次（避免粒子过密），方向感知：
        粒子主要向玩家身后散射，模拟跑步扬尘的物理效果。
        玩家原地不动时不生成粒子。
        """
        # 玩家没有水平移动时不生成粒子
        last_x = self._last_sprint_particle_x
        self._last_sprint_particle_x = self.x
        if last_x is None:
            return
        if abs(self.x - last_x) < 0.001:
            return

        self._sprint_particle_timer += 1
        if self._sprint_particle_timer % 3 != 0:
            return

        # 获取脚下方块，空气方块不生成粒子
        foot_block_x = _math.floor(self.x + self.width / 2)
        foot_block_y = _math.floor(self.y - 0.05)
        try:
            block_below = self.world.get_block(foot_block_x, foot_block_y, 0)
        except (IndexError, AttributeError, TypeError):
            return
        if block_below is None or getattr(block_below, "block_id", None) == "air":
            return

        # 粒子生成位置：脚底，略微偏向身体中心
        base_x = self.x + self.width / 2
        foot_y = self.y

        # 根据朝向确定身后方向（粒子踢向身后）
        # facing: 0=左(RIGHT), 1=右(LEFT)
        behind_dir = -1.0 if self.facing == 0 else 1.0

        for _ in range(2):
            # 随机偏移：粒子散布在脚底附近
            offset_x = _random.uniform(-0.15, 0.15)
            offset_y = _random.uniform(0.0, 0.1)

            # 水平速度：向身后 + 随机扰动
            vel_x = behind_dir * _random.uniform(0.02, 0.08) + _random.uniform(-0.03, 0.03)
            vel_y = _random.uniform(0.01, 0.06)  # 轻微上扬

            self.world.spawn_particle(SPRINT_STEP(
                base_x + offset_x,
                foot_y + offset_y,
                0,
                count=1,
                motion=(vel_x, vel_y),
                data={"block_id": block_below.block_id},
            ))

    def teleport_to(self, x, y, world = None):
        self.x = x
        self.y = y
        if world:
            self.world = world
        self._teleport_id += 1
        self._pending_teleport_id = self._teleport_id
        self.world.server.send_client_socket(self, self, "Teleport")

    def confirm_teleport(self, teleport_id) -> bool:
        """Accept a client acknowledgement for the most recent teleport."""
        try:
            teleport_id = int(teleport_id)
        except (TypeError, ValueError):
            return False
        if teleport_id != self._pending_teleport_id:
            return False
        self._pending_teleport_id = None
        return True

    @property
    def is_awaiting_teleport_confirmation(self) -> bool:
        return self._pending_teleport_id is not None

    def is_loading_position(self, x_loc: int | Location, y = None, z = None) -> bool:
        """
        检测某个位置是否被改玩家加载
        :param x_loc: 可传入 x 坐标或 Location
        :param y: 可不填写
        :param z: 可不填写
        :return:
        """
        x, y, z = decide_x_or_loc(x_loc, y, z)
        rx = int(x // 16)
        return rx in self.loading_regions

    def __str__(self):
        return self.name
