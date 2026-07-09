from resources.server.material_class import Material, BlockItem
import resources.server.blocks as blocks


class DIRT(BlockItem):
    name_id = "dirt"
    name = "dirt"
    target_block = blocks.DIRT

class AIR(BlockItem):
    name_id = "air"
    name = "air"
    target_block = blocks.AIR

class GLOWSTONE(BlockItem):
    name_id = "glowstone"
    name = "glowstone"
    target_block = blocks.GLOWSTONE

class SAND(BlockItem):
    name_id = "sand"
    name = "sand"
    target_block = blocks.SAND

class WATER(BlockItem):
    name_id = "water"
    name = "water"
    target_block = blocks.WATER