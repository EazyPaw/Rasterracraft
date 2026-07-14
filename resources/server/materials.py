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


class APPLE(Material):
    name_id = "apple"
    name = "Apple"
    _texture_path = "items.apple"
    food_value = 4
    saturation_modifier = 0.3


class BREAD(Material):
    name_id = "bread"
    name = "Bread"
    _texture_path = "items.bread"
    food_value = 5
    saturation_modifier = 0.6


class COOKED_BEEF(Material):
    name_id = "cooked_beef"
    name = "Cooked Beef"
    _texture_path = "items.beef_cooked"
    food_value = 8
    saturation_modifier = 0.8


class STICK(Material):
    name_id = "stick"
    name = "Stick"
    _texture_path = "items.stick"


class Tool(Material):
    tool_type = None
    tier = "wood"
    mining_speed = 1.0


class WOODEN_PICKAXE(Tool):
    name_id = "wooden_pickaxe"
    name = "Wooden Pickaxe"
    _texture_path = "items.wood_pickaxe"
    tool_type = "pickaxe"
    mining_speed = 2.0


class STONE_PICKAXE(WOODEN_PICKAXE):
    name_id = "stone_pickaxe"
    name = "Stone Pickaxe"
    _texture_path = "items.stone_pickaxe"
    tier = "stone"
    mining_speed = 4.0


class IRON_PICKAXE(WOODEN_PICKAXE):
    name_id = "iron_pickaxe"
    name = "Iron Pickaxe"
    _texture_path = "items.iron_pickaxe"
    tier = "iron"
    mining_speed = 6.0


class DIAMOND_PICKAXE(WOODEN_PICKAXE):
    name_id = "diamond_pickaxe"
    name = "Diamond Pickaxe"
    _texture_path = "items.diamond_pickaxe"
    tier = "diamond"
    mining_speed = 8.0


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
             "target_block": type(block)},
        )
        _block_item_types[block_id] = item_type
    return item_type()


def get_material_by_id(material_id: str):
    """Resolve a wire-format material id, including generated block items."""
    material_id = str(material_id).removeprefix("minecraft:")
    known = {
        "air": AIR, "dirt": DIRT, "sand": SAND, "water": WATER,
        "glowstone": GLOWSTONE, "apple": APPLE, "bread": BREAD,
        "cooked_beef": COOKED_BEEF, "stick": STICK,
        "wooden_pickaxe": WOODEN_PICKAXE, "stone_pickaxe": STONE_PICKAXE,
        "iron_pickaxe": IRON_PICKAXE, "diamond_pickaxe": DIAMOND_PICKAXE,
    }
    material_type = known.get(material_id)
    if material_type is not None:
        return material_type()
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
