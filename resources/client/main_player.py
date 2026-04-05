from resources.server.entity import Entity

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from resources.client.client_main import Client

class ClientPlayer(Entity):
    def __init__(self, client: 'Client'):
        super().__init__(0, 1)
        self.client = client

    def collision_check(self):
        ...

    def move_right(self):
        self.x += self.speed

    def move_left(self):
        self.x -= self.speed

    def handle_gravity(self):
        if not self.on_ground:
            self.motion_y -= self.gravity

    def motion_update(self):
        self.x += self.motion_x
        self.y += self.motion_y
        if self.client.client_world.get_block(int(self.x), int(self.y) - 1, 0).solid and self.y % 1 < self.motion_y:
            self.y = int(self.y)
            self.motion_y = 0
            self.on_ground = True
