import uuid
from typing import TYPE_CHECKING

import pygame

from resources.client.entity_skeleton import PlayerSkeleton
from resources.client.game_mode import CreativeMode
from resources.server.entity import Entity
from resources.server.inventory import Inventory
from resources.server.item_class import ItemStack
from resources.server.materials import *

if TYPE_CHECKING:
    from resources.client.client_main import Client


class ClientPlayer(Entity):
    def __init__(self, client: 'Client'):
        super().__init__(0, 15, client.client_world)
        self.uuid = uuid.UUID('{00000000-0000-0000-0000-000000000000}')
        self.client = client
        self.move_speed = 0.3
        self.damping = 0.95
        self.width = 0.3
        self.height = 1.8
        self.jump_height = 0.8
        self.choosing_block = None
        self.flyable = False
        self.inventory = Inventory(36)
        self.skeleton = PlayerSkeleton(client, self)
        self.skeleton.x = self.client.render.SCREEN_WIDTH / 2
        self.skeleton.y = self.client.render.SCREEN_HEIGHT / 2
        for i in range(16):
            self.inventory.set_item(i, ItemStack(GLOWSTONE(), 64))
        self.selected_slot = 0
        self.game_mode = CreativeMode(self)

    def move_update(self):
        keys = pygame.key.get_pressed()
        self.sneaking = (keys[pygame.K_LSHIFT] or keys[pygame.K_s]) and not self.flying

        super().move_update()

        self.client.sent_packet(self, 'PlayerMove')
