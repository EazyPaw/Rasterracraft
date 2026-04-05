from resources.server.world_class import World


class Player:
    def __init__(self, x, y, world):
        self.x = x
        self.y = y
        self.world: World = world