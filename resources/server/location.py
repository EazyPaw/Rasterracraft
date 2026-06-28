import math


class Location:
    def __init__(self, world, x, y, z):
        self.world = world
        self.x = x
        self.y = y
        self.z = z

    def add(self, x_, y_, z_):
        return Location(self.world, self.x + x_, self.y + y_, self.z + z_)

    def __str__(self):
        return f"world={self.world.id_name}, x={self.x}, y={self.y}, z={self.z}"

def decide_x_or_loc(x_loc: int | Location, y: int | None = None, z: int | None  = None):
    if isinstance(x_loc, Location):
        return x_loc.x, x_loc.y, x_loc.z
    else:
        return x_loc, y, z

class Vector:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y)

    def __sub__(self, other):
        return Vector(self.x - other.x, self.y - other.y)

    def __mul__(self, other):
        if isinstance(other, Vector):
            return self.x * other.x + self.y * other.y
        else:
            return Vector(self.x * other, self.y * other)

    def add(self, x, y):
        self.x += x
        self.y += y

    def set(self, x=None, y=None):
        if x:
            self.x = x
        if y:
            self.y = y

    def angle_with_x_axis(self):
        """
        计算向量 (x, y) 与 x 轴正半轴的夹角（角度）。
        返回float: 角度，范围 [0, 360) 度
        """
        rad = math.atan2(self.y, self.x)
        deg = math.degrees(rad)
        # 将负角转换为 [0, 360) 范围
        if deg < 0:
            deg += 360.0
        return deg
