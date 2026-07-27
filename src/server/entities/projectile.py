# Commented and arranged by ChatGPT
from abc import ABC

from src.server.entity import Entity


class Projectile(Entity, ABC):
    _texture_path = None
