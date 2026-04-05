from resources.server.block_class import Block


class STONE(Block):
    block_id = 'stone'
    name = 'stone'
    _texture_path = 'assets/minecraft/textures/blocks/stone.png'

class AIR(Block):
    block_id = 'air'
    name = 'air'
    _texture_path = None
    solid = False

    @classmethod
    def get_texture(cls, size):
        return None

def get_block_by_id(block_id: str) -> Block:
    for subclass in Block.__subclasses__():
        if getattr(subclass, 'block_id', None) == block_id:
            return subclass()
    raise ValueError(f"Unknown block ID: {block_id}")