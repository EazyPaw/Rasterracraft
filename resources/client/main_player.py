import math
import uuid

from resources.server.entity import Entity
from typing import TYPE_CHECKING

from resources.client.game_mode import CreativeMode

if TYPE_CHECKING:
    from resources.client.client_main import Client

class ClientPlayer(Entity):
    def __init__(self, client: 'Client'):
        super().__init__(0, 15, client.client_world)
        self.uuid = uuid.UUID('{00000000-0000-0000-0000-000000000000}')
        self.client = client
        self.game_mode = CreativeMode(self)
        self.jump_speed = 0.8
        self.speed = 0.6
        self.damping = 0.91
        self.width = 0.99
        self.height = 0.8
        self.choosing_block = None

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        try:
            block = self.client.client_world.get_block(x, y, z)
            return block.solid
        except (IndexError, AttributeError):
            return False

    def _check_collision_at(self, x: float, y: float) -> bool:
        min_x = math.floor(x)
        max_x = math.floor(x + self.width)
        min_y = math.floor(y)
        max_y = math.floor(y + self.height)

        for block_x in range(min_x, max_x + 1):
            for block_y in range(min_y, max_y + 1):
                if self._is_block_solid(block_x, block_y):
                    return True
        return False

    # ==================== 核心移动+碰撞系统 ====================

    # 需要新增一个工具函数放在类内

    def _sweep_x(self, dx: float):
        """
        水平扫掠检测，返回 (实际移动量, 是否碰撞)
        原理：将玩家的前边缘看作一条竖直的线段，扫过 dx 距离，
             检测是否与任何固体方块相交。
        """
        if dx == 0:
            return 0.0, False

        # 玩家的 Y 范围
        y_min = self.y
        y_max = self.y + self.height

        # 根据移动方向确定前边缘的 x 坐标
        if dx > 0:
            # 向右：前边缘是右边界
            leading_x = self.x + self.width
            direction = 1
            # 可能阻挡的方块列：从当前右边缘所在列，到目标右边缘所在列
            start_cell_x = math.floor(leading_x)
            end_cell_x = math.floor(leading_x + dx)
            step = 1
        else:
            # 向左：前边缘是左边界
            leading_x = self.x
            direction = -1
            start_cell_x = math.floor(leading_x)
            end_cell_x = math.floor(leading_x + dx)  # dx 为负
            step = -1

        # 没有跨列，不可能发生碰撞
        if start_cell_x == end_cell_x:
            return dx, False

        # 遍历每一列，寻找第一个固体方块
        for cell_x in range(start_cell_x + step, end_cell_x + step, step):
            # 该列的方块占据的 X 区间：[cell_x, cell_x+1]
            # 计算前边缘撞到该方块表面所需移动的距离
            if dx > 0:
                # 方块左边界
                hit_x = cell_x  # 前边缘到达 cell_x 时碰撞
                move_to_collision = hit_x - leading_x
            else:
                # 方块右边界（向左移动时，前边缘是左边界 x，碰到方块的右边界 cell_x+1）
                hit_x = cell_x + 1
                move_to_collision = hit_x - leading_x  # 负值

            # 如果该距离已经超出本次移动范围，则不会碰到这一列
            if abs(move_to_collision) > abs(dx):
                continue

            # 检查该列在玩家 Y 区间内是否有固体方块
            # 需要的 Y 格范围
            min_y_cell = math.floor(y_min)
            max_y_cell = math.floor(y_max)
            collides = False
            for block_y in range(min_y_cell, max_y_cell + 1):
                if self._is_block_solid(cell_x, block_y):
                    collides = True
                    break

            if collides:
                # 发生碰撞，精确停在方块表面（保留微小间隙）
                if dx > 0:
                    # 右边缘贴住方块左边界
                    final_x = hit_x - self.width - 0.001
                else:
                    # 左边缘贴住方块右边界
                    final_x = hit_x + 0.001
                actual_dx = final_x - self.x
                return actual_dx, True

        # 无碰撞，可以移动全部距离
        return dx, False

    def _sweep_y(self, dy: float):
        """
        垂直扫掠检测，返回 (实际移动量, 是否碰撞)
        原理同 _sweep_x，只是改用上/下边缘水平扫描。
        """
        if dy == 0:
            return 0.0, False

        x_min = self.x
        x_max = self.x + self.width

        if dy > 0:
            # 向上：前边缘是上边界
            leading_y = self.y + self.height
            direction = 1
            start_cell_y = math.floor(leading_y)
            end_cell_y = math.floor(leading_y + dy)
            step = 1
        else:
            # 向下：前边缘是下边界
            leading_y = self.y
            direction = -1
            start_cell_y = math.floor(leading_y)
            end_cell_y = math.floor(leading_y + dy)
            step = -1

        if start_cell_y == end_cell_y:
            return dy, False

        for cell_y in range(start_cell_y + step, end_cell_y + step, step):
            if dy > 0:
                # 上方阻挡，方块下边界
                hit_y = cell_y
                move_to_collision = hit_y - leading_y
            else:
                # 下方阻挡，方块上边界
                hit_y = cell_y + 1
                move_to_collision = hit_y - leading_y

            if abs(move_to_collision) > abs(dy):
                continue

            # 检查该行在玩家 X 区间内是否有固体方块
            min_x_cell = math.floor(x_min)
            max_x_cell = math.floor(x_max)
            collides = False
            for block_x in range(min_x_cell, max_x_cell + 1):
                if self._is_block_solid(block_x, cell_y):
                    collides = True
                    break

            if collides:
                if dy > 0:
                    # 上边缘贴住方块下边界
                    final_y = hit_y - self.height - 0.001
                else:
                    # 下边缘贴住方块上边界
                    final_y = hit_y + 0.001
                actual_dy = final_y - self.y
                return actual_dy, True

        return dy, False

    def collision_check(self, steps: int = 16):
        """
        精确连续碰撞检测，不再依赖 steps 参数（保留仅为接口兼容）。
        """
        # 执行水平移动
        actual_dx, collided_x = self._sweep_x(self.motion_x)
        self.x += actual_dx
        if collided_x:
            self.motion_x = 0

        # 执行垂直移动
        actual_dy, collided_y = self._sweep_y(self.motion_y)
        self.y += actual_dy
        if collided_y:
            self.motion_y = 0

        # 地面检测 (和原逻辑相同)
        foot_check_y = self.y - 0.05
        self.on_ground = self._check_collision_at(self.x, foot_check_y)

    # ==================== 外部接口（保持不变） ====================

    def move_right(self):
        self.motion_x += self.speed

    def move_left(self):
        self.motion_x -= self.speed

    def handle_gravity(self):
        """每帧施加重力：速度向下增加（motion_y 减小）"""
        self.motion_y -= self.gravity

    def jump(self):
        if self.on_ground:
            self.motion_y = self.jump_speed

    def update_damping(self):
        self.damping = 0.91 * self.client.client_world.get_block(self.x, self.y, 0).friction

    def move_update(self):
        """
        每帧更新：
        1. 施加重力
        2. 水平阻尼（摩擦）
        3. 移动并处理碰撞
        """
        # 重力影响（持续加速下落）
        self.handle_gravity()

        self.update_damping()
        self.motion_x *= self.damping
        if abs(self.motion_x) < 0.001:
            self.motion_x = 0

        # 移动（内部会处理碰撞并可能清零速度）
        self.collision_check(steps=4)

        self.client.sent_packet(self, 'PlayerMove')

        def place_block(x, y, z):
            self.client.sent_packet(self, 'PlayerPlaceBlock', x, y, z)

