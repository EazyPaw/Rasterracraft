import uuid


class Entity:
    def __init__(self, x, y, world):
        self.uuid = uuid.uuid4()
        self.x = x
        self.y = y
        self.world = world
        self.motion_x = 0
        self.motion_y = 0
        self.width = 1
        self.height = 1
        self.speed = 0.1
        self.gravity = 0.08
        self.jump_height = 1
        self.max_health = 10
        self.health = self.max_health
        self.on_ground = False
        self.interact_range = 3.5

    def teleport_to(self, x, y, world = None):
        self.x = x
        self.y = y
        if world:
            self.world = world

