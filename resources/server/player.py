from resources.server.entity import Entity
from resources.server.world_class import World


class Player(Entity):
    def __init__(self, x, y, world):
        super().__init__(x, y, world)
        self.world: World = world
        self.loading_regions = []

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