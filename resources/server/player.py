from resources.server.entity import Entity
from resources.server.location import Location, decide_x_or_loc
from resources.server.world_class import World


class Player(Entity):
    def __init__(self, x, y, world):
        super().__init__(x, y, world)
        self.world: World = world
        self.loading_regions = []
        self.name = "Player_" + self.uuid.hex[:8]

    def on_moving(self):
        rx = int(self.x // 16)
        for x in range(rx - self.world.server.view_distance, rx + self.world.server.view_distance + 1):
            if x not in self.loading_regions and x in self.world.regions:
                self.world.server.send_client_socket(self, self.world.regions[x])

    def teleport_to(self, x, y, world = None):
        self.x = x
        self.y = y
        self.world.server.send_client_socket(self, self, "Teleport")
        if world:
            self.world = world

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