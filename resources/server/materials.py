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


class RAW_CHICKEN(Material):
    name_id = "chicken"
    name = "item.chickenRaw.name"
    _texture_path = "items.chicken_raw"
    food_value = 2
    saturation_modifier = 0.3


class COOKED_CHICKEN(Material):
    name_id = "cooked_chicken"
    name = "item.chickenCooked.name"
    _texture_path = "items.chicken_cooked"
    food_value = 6
    saturation_modifier = 0.6


class RAW_BEEF(Material):
    name_id = "beef"
    name = "item.beefRaw.name"
    _texture_path = "items.beef_raw"
    food_value = 3
    saturation_modifier = 0.3


class LEATHER(Material):
    name_id = "leather"
    name = "item.leather.name"
    _texture_path = "items.leather"


class RAW_PORKCHOP(Material):
    name_id = "porkchop"
    name = "item.porkchopRaw.name"
    _texture_path = "items.porkchop_raw"
    food_value = 3
    saturation_modifier = 0.3


class COOKED_PORKCHOP(Material):
    name_id = "cooked_porkchop"
    name = "item.porkchopCooked.name"
    _texture_path = "items.porkchop_cooked"
    food_value = 8
    saturation_modifier = 0.8


class RAW_MUTTON(Material):
    name_id = "mutton"
    name = "item.muttonRaw.name"
    _texture_path = "items.mutton_raw"
    food_value = 2
    saturation_modifier = 0.3


class COOKED_MUTTON(Material):
    name_id = "cooked_mutton"
    name = "item.muttonCooked.name"
    _texture_path = "items.mutton_cooked"
    food_value = 6
    saturation_modifier = 0.8


class FEATHER(Material):
    name_id = "feather"
    name = "item.feather.name"
    _texture_path = "items.feather"


class EGG(Material):
    name_id = "egg"
    name = "item.egg.name"
    _texture_path = "items.egg"


class WHEAT_SEEDS(Material):
    name_id = "wheat_seeds"
    name = "item.seeds.name"
    _texture_path = "items.seeds_wheat"


class PUMPKIN_SEEDS(Material):
    name_id = "pumpkin_seeds"
    name = "item.seeds_pumpkin.name"
    _texture_path = "items.seeds_pumpkin"


class MELON_SEEDS(Material):
    name_id = "melon_seeds"
    name = "item.seeds_melon.name"
    _texture_path = "items.seeds_melon"


class WHEAT(Material):
    name_id = "wheat"
    name = "item.wheat.name"
    _texture_path = "items.wheat"


class CARROT(Material):
    name_id = "carrot"
    name = "item.carrots.name"
    _texture_path = "items.carrot"


class POTATO(Material):
    name_id = "potato"
    name = "item.potato.name"
    _texture_path = "items.potato"


class CARROT_ON_A_STICK(Material):
    name_id = "carrot_on_a_stick"
    name = "item.carrotOnAStick.name"
    _texture_path = "items.carrot_on_a_stick"
    max_stack_size = 1


class BUCKET(Material):
    name_id = "bucket"
    name = "item.bucket.name"
    _texture_path = "items.bucket_empty"
    max_stack_size = 16


class MILK_BUCKET(Material):
    name_id = "milk_bucket"
    name = "item.milk.name"
    _texture_path = "items.bucket_milk"
    max_stack_size = 1


class SHEARS(Material):
    name_id = "shears"
    name = "item.shears.name"
    _texture_path = "items.shears"
    max_stack_size = 1


class WHITE_WOOL(Material):
    name_id = "white_wool"
    name = "tile.cloth.white.name"
    _texture_path = "blocks.wool_colored_white"


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
        "chicken": RAW_CHICKEN, "cooked_chicken": COOKED_CHICKEN,
        "beef": RAW_BEEF, "leather": LEATHER,
        "porkchop": RAW_PORKCHOP, "cooked_porkchop": COOKED_PORKCHOP,
        "mutton": RAW_MUTTON, "cooked_mutton": COOKED_MUTTON,
        "feather": FEATHER, "egg": EGG,
        "wheat_seeds": WHEAT_SEEDS, "seeds": WHEAT_SEEDS,
        "pumpkin_seeds": PUMPKIN_SEEDS, "melon_seeds": MELON_SEEDS,
        "wheat": WHEAT, "carrot": CARROT, "potato": POTATO,
        "carrot_on_a_stick": CARROT_ON_A_STICK,
        "bucket": BUCKET, "milk_bucket": MILK_BUCKET,
        "shears": SHEARS, "white_wool": WHITE_WOOL,
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
