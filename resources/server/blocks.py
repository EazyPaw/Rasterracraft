from resources.server.block_class import Block


class STONE(Block):
    block_id = 'stone'
    name = 'stone'
    _texture_path = 'assets/minecraft/textures/blocks/stone.png'

class AIR(Block):
    block_id = 'air'
    name = 'air'
    _texture_path = None

    @classmethod
    def get_texture(cls, size):
        return None