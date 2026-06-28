import uuid
import ast
import logging

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
        self.gravity = 0.08
        self.drag_vertical = 0.98  # 垂直方向阻力，每帧保留 98% 的速度
        self.jump_height = 1
        self.max_health = 10
        self.health = self.max_health
        self.on_ground = False
        self.interact_range = 3.5
        self.facing = 0  # 0: 左边 1: 右边

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

