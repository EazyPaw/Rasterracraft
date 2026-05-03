from resources.server.block_class import Block


class STONE(Block):
    block_id = 'stone'
    name = 'stone'
    _texture_path = 'blocks.stone'

class AIR(Block):
    block_id = 'air'
    name = 'air'
    _texture_path = None
    solid = False
    replaceable = True
    breakable = False
    light_attenuation = 0

    @classmethod
    def get_texture(cls, size, client):
        return None

    def on_right_click(self):
        pass

def get_block_by_id(block_id: str) -> Block:
    for subclass in Block.__subclasses__():
        if getattr(subclass, 'block_id', None) == block_id:
            return subclass()
    raise ValueError(f"Unknown block ID: {block_id}")