from resources.server.blocks import *


def get_block_origin(x, y, z, seed):

    if y < 10:
        return STONE()
    else:
        return AIR()