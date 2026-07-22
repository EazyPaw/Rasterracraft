import pygame

from resources.server.material_class import Material, BlockItem, Food
from resources.server.utils import client_method


_material_registry: dict[str, type[Material]] = {}


def register_material(cls=None, /, *, aliases: tuple[str, ...] = ()):
    """Decorator – register *cls* (and optional aliases) in ``_material_registry``.

    Usage::

        @register_material
        class APPLE(Material):
            name_id = "apple"

        @register_material(aliases=("seeds",))
        class WHEAT_SEEDS(Material):
            name_id = "wheat_seeds"
    """
    if cls is None:
        return lambda c: register_material(c, aliases=aliases)
    _material_registry[cls.name_id] = cls
    for alias in aliases:
        _material_registry[alias] = cls
    return cls


@register_material
class DIRT(BlockItem):
    name_id = "dirt"
    name = "tile.dirt.name"
    target_block_id = "dirt"

@register_material
class AIR(BlockItem):
    name_id = "air"
    name = "tile.air.name"
    target_block_id = "air"

@register_material
class GLOWSTONE(BlockItem):
    name_id = "glowstone"
    name = "tile.lightgem.name"
    target_block_id = "glowstone"

@register_material
class SAND(BlockItem):
    name_id = "sand"
    name = "tile.sand.name"
    target_block_id = "sand"


@register_material
class COBBLESTONE(BlockItem):
    name_id = "cobblestone"
    name = "tile.stonebrick.name"
    target_block_id = "cobblestone"

@register_material
class WATER(BlockItem):
    name_id = "water"
    name = "tile.water.name"
    target_block_id = "water"

@register_material
class LAVA(BlockItem):
    name_id = "lava"
    name = "tile.lava.name"
    target_block_id = "lava"

@register_material
class APPLE(Food):
    name_id = "apple"
    name = "item.apple.name"
    _texture_path = "items.apple"
    food_value = 4
    saturation_modifier = 0.3


@register_material
class BREAD(Food):
    name_id = "bread"
    name = "item.bread.name"
    _texture_path = "items.bread"
    food_value = 5
    saturation_modifier = 0.6


@register_material
class COOKED_BEEF(Food):
    name_id = "cooked_beef"
    name = "item.beefCooked.name"
    _texture_path = "items.beef_cooked"
    food_value = 8
    saturation_modifier = 0.8


@register_material
class ROTTEN_FLESH(Food):
    name_id = "rotten_flesh"
    name = "item.rottenFlesh.name"
    _texture_path = "items.rotten_flesh"
    food_value = 4
    saturation_modifier = 0.1


@register_material
class RAW_CHICKEN(Food):
    name_id = "chicken"
    name = "item.chickenRaw.name"
    _texture_path = "items.chicken_raw"
    food_value = 2
    saturation_modifier = 0.3


@register_material
class COOKED_CHICKEN(Food):
    name_id = "cooked_chicken"
    name = "item.chickenCooked.name"
    _texture_path = "items.chicken_cooked"
    food_value = 6
    saturation_modifier = 0.6


@register_material
class RAW_BEEF(Food):
    name_id = "beef"
    name = "item.beefRaw.name"
    _texture_path = "items.beef_raw"
    food_value = 3
    saturation_modifier = 0.3


@register_material
class LEATHER(Material):
    name_id = "leather"
    name = "item.leather.name"
    _texture_path = "items.leather"


@register_material
class RAW_PORKCHOP(Food):
    name_id = "porkchop"
    name = "item.porkchopRaw.name"
    _texture_path = "items.porkchop_raw"
    food_value = 3
    saturation_modifier = 0.3


@register_material
class COOKED_PORKCHOP(Food):
    name_id = "cooked_porkchop"
    name = "item.porkchopCooked.name"
    _texture_path = "items.porkchop_cooked"
    food_value = 8
    saturation_modifier = 0.8


@register_material
class RAW_MUTTON(Food):
    name_id = "mutton"
    name = "item.muttonRaw.name"
    _texture_path = "items.mutton_raw"
    food_value = 2
    saturation_modifier = 0.3


@register_material
class COOKED_MUTTON(Food):
    name_id = "cooked_mutton"
    name = "item.muttonCooked.name"
    _texture_path = "items.mutton_cooked"
    food_value = 6
    saturation_modifier = 0.8


@register_material
class FEATHER(Material):
    name_id = "feather"
    name = "item.feather.name"
    _texture_path = "items.feather"


@register_material
class EGG(Material):
    name_id = "egg"
    name = "item.egg.name"
    _texture_path = "items.egg"


class CropPlantingMaterial(Material):
    """An item that plants a crop while keeping block imports lazy."""

    crop_block_id = None

    @classmethod
    def create_crop(cls):
        from resources.server.blocks import get_block_by_id
        return get_block_by_id(cls.crop_block_id)


@register_material(aliases=("seeds",))
class WHEAT_SEEDS(CropPlantingMaterial):
    name_id = "wheat_seeds"
    name = "item.seeds.name"
    _texture_path = "items.seeds_wheat"
    crop_block_id = "wheat"


@register_material
class PUMPKIN_SEEDS(Material):
    name_id = "pumpkin_seeds"
    name = "item.seeds_pumpkin.name"
    _texture_path = "items.seeds_pumpkin"


@register_material
class MELON_SEEDS(Material):
    name_id = "melon_seeds"
    name = "item.seeds_melon.name"
    _texture_path = "items.seeds_melon"


@register_material
class WHEAT(Material):
    name_id = "wheat"
    name = "item.wheat.name"
    _texture_path = "items.wheat"


@register_material
class CARROT(CropPlantingMaterial, Food):
    name_id = "carrot"
    name = "item.carrots.name"
    _texture_path = "items.carrot"
    crop_block_id = "carrots"
    food_value = 3
    saturation_modifier = 0.6


@register_material
class POTATO(CropPlantingMaterial, Food):
    name_id = "potato"
    name = "item.potato.name"
    _texture_path = "items.potato"
    crop_block_id = "potatoes"
    food_value = 1
    saturation_modifier = 0.3


@register_material
class POISONOUS_POTATO(Food):
    name_id = "poisonous_potato"
    name = "item.potatoPoisonous.name"
    _texture_path = "items.potato_poisonous"
    food_value = 2
    saturation_modifier = 0.3


@register_material
class CARROT_ON_A_STICK(Material):
    name_id = "carrot_on_a_stick"
    name = "item.carrotOnAStick.name"
    _texture_path = "items.carrot_on_a_stick"
    max_stack_size = 1


@register_material
class BUCKET(Material):
    name_id = "bucket"
    name = "item.bucket.name"
    _texture_path = "items.bucket_empty"
    max_stack_size = 16


@register_material
class MILK_BUCKET(Material):
    name_id = "milk_bucket"
    name = "item.milk.name"
    _texture_path = "items.bucket_milk"
    max_stack_size = 1


@register_material
class SHEARS(Material):
    name_id = "shears"
    name = "item.shears.name"
    _texture_path = "items.shears"
    max_stack_size = 1


@register_material
class WHITE_WOOL(Material):
    name_id = "white_wool"
    name = "tile.cloth.white.name"
    _texture_path = "blocks.wool_colored_white"


@register_material
class STICK(Material):
    name_id = "stick"
    name = "item.stick.name"
    _texture_path = "items.stick"


@register_material
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
    attack_damage_modifier = 0.0
    attack_speed_modifier = -3.0

    @classmethod
    def get_default_attribute_modifiers(cls):
        return (
            {
                "type": "minecraft:attack_damage",
                "id": "minecraft:base_attack_damage",
                "amount": cls.attack_damage_modifier,
                "operation": "add_value",
                "slot": "mainhand",
            },
            {
                "type": "minecraft:attack_speed",
                "id": "minecraft:base_attack_speed",
                "amount": cls.attack_speed_modifier,
                "operation": "add_value",
                "slot": "mainhand",
            },
        )

    @client_method
    def get_anchor(self, client = None):
        """
        用于获取渲染时客户端的手持点位，第三个值为缩放倍率，第四个参数为旋转度数（角度制）
        :return:
        """
        return {'anchor':(0.7,0.7),'offset':(0, 0),'scale':0.8,'rotation':-135}


@register_material
class WOODEN_PICKAXE(Tool):
    name_id = "wooden_pickaxe"
    name = "item.pickaxeWood.name"
    _texture_path = "items.wood_pickaxe"
    tool_type = "pickaxe"
    mining_speed = 2.0
    attack_damage_modifier = 1.0
    attack_speed_modifier = -2.8


@register_material
class STONE_PICKAXE(WOODEN_PICKAXE):
    name_id = "stone_pickaxe"
    name = "item.pickaxeStone.name"
    _texture_path = "items.stone_pickaxe"
    tier = "stone"
    mining_speed = 4.0
    attack_damage_modifier = 2.0


@register_material
class IRON_PICKAXE(WOODEN_PICKAXE):
    name_id = "iron_pickaxe"
    name = "item.pickaxeIron.name"
    _texture_path = "items.iron_pickaxe"
    tier = "iron"
    mining_speed = 6.0
    attack_damage_modifier = 3.0


@register_material
class DIAMOND_PICKAXE(WOODEN_PICKAXE):
    name_id = "diamond_pickaxe"
    name = "item.pickaxeDiamond.name"
    _texture_path = "items.diamond_pickaxe"
    tier = "diamond"
    mining_speed = 8.0
    attack_damage_modifier = 4.0

@register_material
class TORCH(BlockItem):
    name_id = "torch"
    name = "tile.torch.name"
    target_block_id = "torch"

@register_material
class WOODEN_HOE(Tool):
    name_id = "wooden_hoe"
    name = "item.hoeWood.name"
    _texture_path = "items.wood_hoe"
    tier = "wood"
    tool_type = "hoe"
    mining_speed = 2.0


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
    """Resolve a wire-format material id, including generated block items.

    Material subclasses decorated with :func:`register_material` are looked up
    automatically — no hand-maintained dictionary is needed.
    """
    material_id = str(material_id).removeprefix("minecraft:")
    material_type = _material_registry.get(material_id)
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
