import ast
import logging
import math
import uuid

from resources.server.location import Vector
from resources.server.utils import is_safe_value


class Entity:
    def __init__(self, x, y, world):
        self.uuid = uuid.uuid4()
        self.x = x
        self.y = y
        self.world = world
        self.motion = Vector(0, 0)
        self.width = 1
        self.height = 1
        self.move_speed = 0.1
        self.damping = 0.95
        self.gravity = 0.08
        self.drag_vertical = 0.98  # 垂直方向阻力，每帧保留 98% 的速度
        self.jump_height = 1
        self.max_health = 10
        self.health = self.max_health
        self.on_ground = False
        self.flying = False
        self.sneaking = False
        self.interact_range = 3.5
        self.facing = 0  # 0: 左边 1: 右边
        self.sprinting = False

    def teleport_to(self, x, y, world = None):
        self.x = x
        self.y = y
        if world:
            self.world = world

    def get_safe_attributes(self):
        """
        获取当前实例的所有安全属性，返回一个字典。
        """
        safe_data = {}
        # 使用 vars(self) 获取实例变量（适用于普通类，不处理 __slots__）
        for key, value in vars(self).items():
            if is_safe_value(value):
                safe_data[key] = value
        return safe_data

    def parse_nbt(self) -> str:
        nbt = self.get_safe_attributes()
        return str(nbt)

    def write_nbt(self, nbt: str):
        nbt = ast.literal_eval(nbt)
        for key, value in nbt.items():
            if hasattr(self, key):
                current_attr = getattr(self, key)
                current_type = type(current_attr)
                if type(value) is current_type:  # 严格类型相等
                    setattr(self, key, value)
                else:
                    logging.warning(f"There exists a incorrect type nbt, expect {type(current_attr)}, but got {type(value)}.")
            else:
                logging.warning(f"Entity {self.uuid} has no attribute {key}.")

    def _is_block_solid(self, x: int, y: int, z: int = 0) -> bool:
        try:
            block = self.world.get_block(x, y, z)
            return block.solid
        except (IndexError, AttributeError, TypeError):
            return False

    def _get_block_at(self, x: float, y: float, z: int = 0):
        try:
            return self.world.get_block(math.floor(x), math.floor(y), z)
        except (IndexError, AttributeError, TypeError):
            return None

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

    def _prevent_edge_fall(self, dx: float) -> float:
        if dx == 0 or not self.on_ground or not self.sneaking:
            return dx

        foot_y = self.y - 0.05

        if dx > 0:
            check_x = self.x + dx + self.width
            if self._check_collision_at(check_x, foot_y):
                return dx
            block_edge = math.floor(self.x + self.width) + 1.0
            safe_dx = block_edge - self.width - self.x - 0.001
            return max(0.0, safe_dx)

        check_x = self.x + dx
        if self._check_collision_at(check_x, foot_y):
            return dx
        block_edge = math.floor(self.x)
        safe_dx = block_edge + 1.0 - self.x + 0.001
        return min(0.0, safe_dx)

    def _sweep_x(self, dx: float):
        if dx == 0:
            return 0.0, False

        y_min = self.y
        y_max = self.y + self.height

        if dx > 0:
            leading_x = self.x + self.width
            start_cell_x = math.floor(leading_x)
            end_cell_x = math.floor(leading_x + dx)
            step = 1
        else:
            leading_x = self.x
            start_cell_x = math.floor(leading_x)
            end_cell_x = math.floor(leading_x + dx)
            step = -1

        if start_cell_x == end_cell_x:
            return dx, False

        for cell_x in range(start_cell_x + step, end_cell_x + step, step):
            if dx > 0:
                hit_x = cell_x
                move_to_collision = hit_x - leading_x
            else:
                hit_x = cell_x + 1
                move_to_collision = hit_x - leading_x

            if abs(move_to_collision) > abs(dx):
                continue

            min_y_cell = math.floor(y_min)
            max_y_cell = math.floor(y_max)
            collides = False
            for block_y in range(min_y_cell, max_y_cell + 1):
                if self._is_block_solid(cell_x, block_y):
                    collides = True
                    break

            if collides:
                if dx > 0:
                    final_x = hit_x - self.width - 0.001
                else:
                    final_x = hit_x + 0.001
                actual_dx = final_x - self.x
                return actual_dx, True

        return dx, False

    def _sweep_y(self, dy: float):
        if dy == 0:
            return 0.0, False

        x_min = self.x
        x_max = self.x + self.width

        if dy > 0:
            leading_y = self.y + self.height
            start_cell_y = math.floor(leading_y)
            end_cell_y = math.floor(leading_y + dy)
            step = 1
        else:
            leading_y = self.y
            start_cell_y = math.floor(leading_y)
            end_cell_y = math.floor(leading_y + dy)
            step = -1

        if start_cell_y == end_cell_y:
            return dy, False

        for cell_y in range(start_cell_y + step, end_cell_y + step, step):
            if dy > 0:
                hit_y = cell_y
                move_to_collision = hit_y - leading_y
            else:
                hit_y = cell_y + 1
                move_to_collision = hit_y - leading_y

            if abs(move_to_collision) > abs(dy):
                continue

            min_x_cell = math.floor(x_min)
            max_x_cell = math.floor(x_max)
            collides = False
            for block_x in range(min_x_cell, max_x_cell + 1):
                if self._is_block_solid(block_x, cell_y):
                    collides = True
                    break

            if collides:
                if dy > 0:
                    final_y = hit_y - self.height - 0.001
                else:
                    final_y = hit_y + 0.001
                actual_dy = final_y - self.y
                return actual_dy, True

        return dy, False

    def collision_check(self, steps: int = 16):
        actual_dx, collided_x = self._sweep_x(self.motion.x)
        actual_dx = self._prevent_edge_fall(actual_dx)
        self.x += actual_dx
        if collided_x:
            self.motion.x = 0

        actual_dy, collided_y = self._sweep_y(self.motion.y)
        self.y += actual_dy
        if collided_y:
            self.motion.y = 0

        foot_check_y = self.y - 0.05
        self.on_ground = self._check_collision_at(self.x, foot_check_y)

    def move_right(self):
        speed_mult = 0.3 if self.sneaking else 1.0
        if self.sprinting:
            speed_mult *= 1.3
        if self.flying:
            speed_mult *= 2
        self.motion.x += self.move_speed * speed_mult

    def move_left(self):
        speed_mult = 0.3 if self.sneaking else 1.0
        if self.sprinting:
            speed_mult *= 1.3
        if self.flying:
            speed_mult *= 2
        self.motion.x -= self.move_speed * speed_mult

    def handle_gravity(self):
        self.motion.y -= self.gravity

    def jump(self):
        if self.on_ground:
            self.motion.y = self.jump_height
        elif self.flying:
            self.motion += Vector(0, self.jump_height * 1.5)

    def handle_shift(self):
        if self.flying:
            self.motion -= Vector(0, self.jump_height * 1.5)

    def switch_sprint(self, mode = None):
        if mode is None:
            self.sprinting = not self.sprinting
        else:
            self.sprinting = mode
        print(self.sprinting)

    def update_damping(self):
        if self.flying:
            self.damping = 0.91 * 0.6
            return

        block_below = self._get_block_at(self.x, self.y - 0.05)
        if block_below is None or block_below.block_id == 'air':
            self.damping = 0.91 * 0.6
        else:
            self.damping = 0.91 * block_below.friction

    def move_update(self):
        if self.flying:
            self.motion.y *= 0.5
            if abs(self.motion.y) < 0.1:
                self.motion.y = 0
        else:
            self.handle_gravity()

        if self.on_ground:
            self.flying = False

        self.motion.y *= self.drag_vertical

        self.update_damping()
        self.motion.x *= self.damping
        if abs(self.motion.x) < 0.001:
            self.motion.x = 0

        self.collision_check(steps=4)

