from resources.server.material_class import Material, BlockItem
from resources.server.utils import client_method


class DIRT(BlockItem):
    name_id = "dirt"
    name = "tile.dirt.name"
    target_block_id = "dirt"

class AIR(BlockItem):
    name_id = "air"
    name = "tile.air.name"
    target_block_id = "air"

class GLOWSTONE(BlockItem):
    name_id = "glowstone"
    name = "tile.lightgem.name"
    target_block_id = "glowstone"

class SAND(BlockItem):
    name_id = "sand"
    name = "tile.sand.name"
    target_block_id = "sand"


class COBBLESTONE(BlockItem):
    name_id = "cobblestone"
    name = "tile.stonebrick.name"
    target_block_id = "cobblestone"

class WATER(BlockItem):
    name_id = "water"
    name = "tile.water.name"
    target_block_id = "water"

class LAVA(BlockItem):
    name_id = "lava"
    name = "tile.lava.name"
    target_block_id = "lava"

class APPLE(Material):
    name_id = "apple"
    name = "item.apple.name"
    _texture_path = "items.apple"
    food_value = 4
    saturation_modifier = 0.3


class BREAD(Material):
    name_id = "bread"
    name = "item.bread.name"
    _texture_path = "items.bread"
    food_value = 5
    saturation_modifier = 0.6


class COOKED_BEEF(Material):
    name_id = "cooked_beef"
    name = "item.beefCooked.name"
    _texture_path = "items.beef_cooked"
    food_value = 8
    saturation_modifier = 0.8


class ROTTEN_FLESH(Material):
    name_id = "rotten_flesh"
    name = "item.rottenFlesh.name"
    _texture_path = "items.rotten_flesh"
    food_value = 4
    saturation_modifier = 0.1


class STICK(Material):
    name_id = "stick"
    name = "item.stick.name"
    _texture_path = "items.stick"


class FLINT_AND_STEEL(Material):
    name_id = "flint_and_steel"
    name = "item.flintAndSteel.name"
    _texture_path = "items.flint_and_steel"
    max_stack_size = 1
    ignites_blocks = True


class Tool(Material):
    tool_type = None
    tier = "wood"
    mining_speed = 1.0

    @client_method
    def get_anchor(self, client = None):
        """
        用于获取渲染时客户端的手持点位，第三个值为缩放倍率，第四个参数为旋转度数（角度制）
        :return:
        """
        return {'anchor':(0.3,0.7),'offset':(0, 0),'scale':0.8,'rotation':-45}


class WOODEN_PICKAXE(Tool):
    name_id = "wooden_pickaxe"
    name = "item.pickaxeWood.name"
    _texture_path = "items.wood_pickaxe"
    tool_type = "pickaxe"
    mining_speed = 2.0


class STONE_PICKAXE(WOODEN_PICKAXE):
    name_id = "stone_pickaxe"
    name = "item.pickaxeStone.name"
    _texture_path = "items.stone_pickaxe"
    tier = "stone"
    mining_speed = 4.0


class IRON_PICKAXE(WOODEN_PICKAXE):
    name_id = "iron_pickaxe"
    name = "item.pickaxeIron.name"
    _texture_path = "items.iron_pickaxe"
    tier = "iron"
    mining_speed = 6.0


class DIAMOND_PICKAXE(WOODEN_PICKAXE):
    name_id = "diamond_pickaxe"
    name = "item.pickaxeDiamond.name"
    _texture_path = "items.diamond_pickaxe"
    tier = "diamond"
    mining_speed = 8.0

class TORCH(BlockItem):
    name_id = "torch"
    name = "tile.torch.name"
    target_block_id = "torch"


class SNOWBALL(Material):
    ...


_block_item_types: dict[str, type[BlockItem]] = {}


def get_block_item(block):
    """Return a stackable inventory material for a mined block instance."""
    block_id = getattr(block, "block_id", "air")
    if block_id == "air":
        return AIR()
    item_type = _block_item_types.get(block_id)
    if item_type is None:
        item_type = type(
            f"{block_id.title().replace('_', '')}Item",
            (BlockItem,),
            {"name_id": block_id, "name": getattr(block, "name", block_id),
             "target_block_id": block_id},
        )
        _block_item_types[block_id] = item_type
    return item_type()


def get_material_by_id(material_id: str):
    """Resolve a wire-format material id, including generated block items."""
    material_id = str(material_id).removeprefix("minecraft:")
    known = {
        "air": AIR, "dirt": DIRT, "sand": SAND,
        "cobblestone": COBBLESTONE, "water": WATER, "lava": LAVA,
        "glowstone": GLOWSTONE, "apple": APPLE, "bread": BREAD,
        "cooked_beef": COOKED_BEEF, "rotten_flesh": ROTTEN_FLESH,
        "stick": STICK, "flint_and_steel": FLINT_AND_STEEL,
        "torch": TORCH,
        "wooden_pickaxe": WOODEN_PICKAXE, "stone_pickaxe": STONE_PICKAXE,
        "iron_pickaxe": IRON_PICKAXE, "diamond_pickaxe": DIAMOND_PICKAXE,
    }
    material_type = known.get(material_id)
    if material_type is not None:
        return material_type()
    from resources.server import blocks
    try:
        return get_block_item(blocks.get_block_by_id(material_id))
    except ValueError:
        # Recipes may use plural forms (e.g. "oak_planks") while block IDs
        # are singular ("oak_plank").  Try stripping a trailing 's'.
        if material_id.endswith('s'):
            try:
                return get_block_item(blocks.get_block_by_id(material_id[:-1]))
            except ValueError:
                pass
        return AIR()
