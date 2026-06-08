from abc import ABC

import pygame


class BodyPart:
    def __init__(self, offset: tuple[float, float], angle: float, target_angle: float, texture: pygame.Surface):
        self.offset = offset
        self.angle = angle
        self.texture = texture
        self.target_angle = target_angle
        self.show = True
        self.size = texture.get_size()



class EntitySkeleton(ABC):

    _instances = []

    def __init__(self, client, texture, entity):
        self.client = client
        self.texture: pygame.Surface = client.resources_manager.get_texture_img(texture)
        self.entity = entity
        self.x = 0
        self.y = 0
        self.body = {"head": BodyPart((0, 0), 0, 0, pygame.Surface((8, 8))),}
        self.last_size = None
        self.size = 1

    @classmethod
    def get_all_instances(cls):
        """返回所有实例"""
        return cls._instances

    def conv_size(self):
        if self.last_size == self.client.render.trans_scale: return
        for part in self.body.values():
            part.texture = pygame.transform.scale_by(part.texture, self.client.render.trans_scale * self.size)
        self.last_size = self.client.render.trans_scale

    def update(self):
        for part in self.body.values():
            part.angle += (part.target_angle - part.angle) * 0.1
            part.texture = pygame.transform.rotate(part.texture, part.angle)
        self.conv_size()

class PlayerSkeleton(EntitySkeleton):
    def __init__(self, client, player):
        super().__init__(client, "entity.steve", player)
        self.size = 1.5
        self.body = {
            "head_left": BodyPart((0, 1.8), 0, 0, self.texture.subsurface((16, 8, 8, 8))),
            # "head_right": BodyPart((0, 6), 0, 0, self.texture.subsurface((0, 8, 8, 8))),
            # "face": BodyPart((0, 6), 0, 0, self.texture.subsurface((8, 8, 8, 8))),
            # "body": BodyPart((0, 0), 0, 0, self.texture.subsurface((20, 20, 8, 12))),
            # "body_right": BodyPart((0, 6), 0, 0, self.texture.subsurface((0, 8, 8, 8))),
            # "right_arm": BodyPart((0, 0), 0, 0, self.texture.subsurface((40, 20, 4, 12))),
            "right_leg": BodyPart((0, 0), 0, 0, self.texture.subsurface((0, 20, 4, 12))),
            # "left_arm": BodyPart((0, 0), 0, 0, self.texture.subsurface((40, 52, 4, 12))),
            # "left_leg": BodyPart((0, 0), 0, 0, self.texture.subsurface((24, 52, 4, 12))),
        }
        self.conv_size()

    def draw(self):
        for part in self.body.values():
            if part.show:
                pos = list(self.client.render.trans_world_location((self.entity.x + part.offset[0], self.entity.y + part.offset[1])))
                pos[0] = self.client.render.block_size / 2 + pos[0] - part.size[0] * self.client.render.trans_scale * self.size / 2
                self.client.render.blit(part.texture, tuple(pos))
