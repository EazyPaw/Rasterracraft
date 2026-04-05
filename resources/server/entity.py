class Entity:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.motion_x = 0
        self.motion_y = 0
        self.width = 1
        self.height = 1
        self.speed = 0.1
        self.jump_speed = 0.2
        self.gravity = 0.05
        self.jump_height = 1
        self.max_health = 10
        self.health = self.max_health
        self.on_ground = False
        self.collision = {'up': False, 'down': False, 'left': False, 'right': False}