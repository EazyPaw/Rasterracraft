# Commented and arranged by ChatGPT
from copy import deepcopy

import pygame

from src.server.material_class import DamageableItem, Material, BlockItem, Food
from src.server.tags import ItemTag
from src.server.utils import client_method


_material_registry: dict[str, dict[str, type[Material]]] = {}


def register_material(
    cls=None, /, *, aliases: tuple[str, ...] = (), name_spaced_key="minecraft"
):
    if cls is None:
        return lambda c: register_material(
            c, aliases=aliases, name_spaced_key=name_spaced_key
        )
    namespace = _material_registry.setdefault(name_spaced_key, {})
    namespace[cls.name_id] = cls
    for alias in aliases:
        namespace[alias] = cls
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
    Tags = (ItemTag.COBBLESTONE,)


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
class STONE(BlockItem):
    name_id = "stone"
    name = "tile.stone.stone.name"
    target_block_id = "stone"


@register_material
class OBSIDIAN(BlockItem):
    name_id = "obsidian"
    name = "tile.obsidian.name"
    target_block_id = "obsidian"


@register_material
class GRASS_BLOCK(BlockItem):
    name_id = "grass_block"
    name = "tile.grass.name"
    target_block_id = "grass_block"


@register_material
class OAK_PLANKS(BlockItem):
    name_id = "oak_planks"
    name = "tile.wood.oak.name"
    target_block_id = "oak_planks"


@register_material
class OAK_LOG(BlockItem):
    name_id = "oak_log"
    name = "tile.log.oak.name"
    target_block_id = "oak_log"


@register_material
class CRAFTING_TABLE(BlockItem):
    name_id = "crafting_table"
    name = "tile.workbench.name"
    target_block_id = "crafting_table"


@register_material
class FURNACE(BlockItem):
    name_id = "furnace"
    name = "tile.furnace.name"
    target_block_id = "furnace"


@register_material
class CHEST(BlockItem):
    name_id = "chest"
    name = "tile.chest.name"
    target_block_id = "chest"

    @classmethod
    @client_method
    def get_texture(cls, size, client):
        # Inventory icons always use the single chest, independent of any
        # world chest that happens to occupy the player's current coordinates.
        block = cls.create_block()
        return block.get_texture(max(1, int(round(16 * size))), client=client)


class SpriteBlockItem(BlockItem):
    """Block item whose inventory icon is a dedicated item sprite."""

    texture_size = 1.0
    texture_shadow = False

    @classmethod
    @client_method
    def get_texture(cls, size, client):
        original = client.resources_manager.get_texture_img(cls._texture_path)
        if original is None:
            return None
        key = (round(float(size), 4), original)
        cache = cls.__dict__.get("_scaled_texture_cache")
        if cache is None:
            cache = {}
            cls._scaled_texture_cache = cache
        cached = cache.get(key)
        if cached is not None:
            return cached
        texture = pygame.transform.scale(
            original,
            (
                max(1, int(round(original.get_width() * size))),
                max(1, int(round(original.get_height() * size))),
            ),
        )
        cache[key] = texture
        if len(cache) > 64:
            cache.pop(next(iter(cache)))
        return texture


@register_material
class OAK_DOOR(SpriteBlockItem):
    name_id = "oak_door"
    name = "item.doorOak.name"
    target_block_id = "oak_door"
    _texture_path = "items.door_wood"


@register_material
class SPRUCE_DOOR(SpriteBlockItem):
    name_id = "spruce_door"
    name = "item.doorSpruce.name"
    target_block_id = "spruce_door"
    _texture_path = "items.door_spruce"


@register_material
class BIRCH_DOOR(SpriteBlockItem):
    name_id = "birch_door"
    name = "item.doorBirch.name"
    target_block_id = "birch_door"
    _texture_path = "items.door_birch"


@register_material
class JUNGLE_DOOR(SpriteBlockItem):
    name_id = "jungle_door"
    name = "item.doorJungle.name"
    target_block_id = "jungle_door"
    _texture_path = "items.door_jungle"


@register_material
class ACACIA_DOOR(SpriteBlockItem):
    name_id = "acacia_door"
    name = "item.doorAcacia.name"
    target_block_id = "acacia_door"
    _texture_path = "items.door_acacia"


@register_material
class DARK_OAK_DOOR(SpriteBlockItem):
    name_id = "dark_oak_door"
    name = "item.doorDarkOak.name"
    target_block_id = "dark_oak_door"
    _texture_path = "items.door_dark_oak"


@register_material(aliases=("red_bed",))
class BED(SpriteBlockItem):
    name_id = "bed"
    name = "item.bed.name"
    target_block_id = "bed"
    _texture_path = "items.bed"
    max_stack_size = 1


@register_material
class GLASS(BlockItem):
    name_id = "glass"
    name = "tile.glass.name"
    target_block_id = "glass"


@register_material
class COAL_ORE(BlockItem):
    name_id = "coal_ore"
    name = "tile.oreCoal.name"
    target_block_id = "coal_ore"


@register_material
class IRON_ORE(BlockItem):
    name_id = "iron_ore"
    name = "tile.oreIron.name"
    target_block_id = "iron_ore"


@register_material
class GOLD_ORE(BlockItem):
    name_id = "gold_ore"
    name = "tile.oreGold.name"
    target_block_id = "gold_ore"


@register_material
class DIAMOND_ORE(BlockItem):
    name_id = "diamond_ore"
    name = "tile.oreDiamond.name"
    target_block_id = "diamond_ore"


@register_material
class TNT(BlockItem):
    name_id = "tnt"
    name = "tile.tnt.name"
    target_block_id = "tnt"


class PlantBlockItem(BlockItem):
    texture_size = 1.0
    texture_shadow = False


class LeavesBlockItem(BlockItem):
    texture_shadow = False


@register_material
class GRANITE(BlockItem):
    name_id = "granite"
    name = "tile.stone.granite.name"
    target_block_id = "granite"


@register_material
class DIORITE(BlockItem):
    name_id = "diorite"
    name = "tile.stone.diorite.name"
    target_block_id = "diorite"


@register_material
class ANDESITE(BlockItem):
    name_id = "andesite"
    name = "tile.stone.andesite.name"
    target_block_id = "andesite"


@register_material
class BEDROCK(BlockItem):
    name_id = "bedrock"
    name = "tile.bedrock.name"
    target_block_id = "bedrock"


@register_material
class COARSE_DIRT(BlockItem):
    name_id = "coarse_dirt"
    name = "tile.dirt.coarse.name"
    target_block_id = "coarse_dirt"


@register_material
class PODZOL(BlockItem):
    name_id = "podzol"
    name = "tile.dirt.podzol.name"
    target_block_id = "podzol"


@register_material
class BIRCH_PLANKS(BlockItem):
    name_id = "birch_planks"
    name = "tile.wood.birch.name"
    target_block_id = "birch_planks"


@register_material
class SPRUCE_PLANKS(BlockItem):
    name_id = "spruce_planks"
    name = "tile.wood.spruce.name"
    target_block_id = "spruce_planks"


@register_material
class JUNGLE_PLANKS(BlockItem):
    name_id = "jungle_planks"
    name = "tile.wood.jungle.name"
    target_block_id = "jungle_planks"


@register_material
class ACACIA_PLANKS(BlockItem):
    name_id = "acacia_planks"
    name = "tile.wood.acacia.name"
    target_block_id = "acacia_planks"


@register_material
class DARK_OAK_PLANKS(BlockItem):
    name_id = "dark_oak_planks"
    name = "tile.wood.big_oak.name"
    target_block_id = "dark_oak_planks"


@register_material
class BIRCH_LOG(BlockItem):
    name_id = "birch_log"
    name = "tile.log.birch.name"
    target_block_id = "birch_log"


@register_material
class SPRUCE_LOG(BlockItem):
    name_id = "spruce_log"
    name = "tile.log.spruce.name"
    target_block_id = "spruce_log"


@register_material
class JUNGLE_LOG(BlockItem):
    name_id = "jungle_log"
    name = "tile.log.jungle.name"
    target_block_id = "jungle_log"


@register_material
class ACACIA_LOG(BlockItem):
    name_id = "acacia_log"
    name = "tile.log.acacia.name"
    target_block_id = "acacia_log"


@register_material
class DARK_OAK_LOG(BlockItem):
    name_id = "dark_oak_log"
    name = "tile.log.big_oak.name"
    target_block_id = "dark_oak_log"


@register_material
class RED_SAND(BlockItem):
    name_id = "red_sand"
    name = "tile.sand.red.name"
    target_block_id = "red_sand"


@register_material
class SANDSTONE(BlockItem):
    name_id = "sandstone"
    name = "tile.sandStone.name"
    target_block_id = "sandstone"


@register_material
class RED_SANDSTONE(BlockItem):
    name_id = "red_sandstone"
    name = "tile.redSandStone.name"
    target_block_id = "red_sandstone"


@register_material
class GRAVEL(BlockItem):
    name_id = "gravel"
    name = "tile.gravel.name"
    target_block_id = "gravel"


@register_material
class CLAY(BlockItem):
    name_id = "clay"
    name = "tile.clay.name"
    target_block_id = "clay"


@register_material
class HARDENED_CLAY(BlockItem):
    name_id = "hardened_clay"
    name = "tile.clayHardened.name"
    target_block_id = "hardened_clay"


@register_material
class SNOW(BlockItem):
    name_id = "snow"
    name = "tile.snow.name"
    target_block_id = "snow"


@register_material
class SNOW_BLOCK(BlockItem):
    name_id = "snow_block"
    name = "tile.snow.name"
    target_block_id = "snow_block"


@register_material
class ICE(BlockItem):
    name_id = "ice"
    name = "tile.ice.name"
    target_block_id = "ice"


@register_material
class CACTUS(BlockItem):
    name_id = "cactus"
    name = "tile.cactus.name"
    target_block_id = "cactus"


@register_material
class EMERALD_ORE(BlockItem):
    name_id = "emerald_ore"
    name = "tile.oreEmerald.name"
    target_block_id = "emerald_ore"


@register_material
class LAPIS_ORE(BlockItem):
    name_id = "lapis_ore"
    name = "tile.oreLapis.name"
    target_block_id = "lapis_ore"


@register_material
class REDSTONE_ORE(BlockItem):
    name_id = "redstone_ore"
    name = "tile.oreRedstone.name"
    target_block_id = "redstone_ore"


@register_material
class DIAMOND_BLOCK(BlockItem):
    name_id = "diamond_block"
    name = "tile.blockDiamond.name"
    target_block_id = "diamond_block"


@register_material
class OAK_SLAB(BlockItem):
    name_id = "oak_slab"
    name = "tile.woodSlab.oak.name"
    target_block_id = "oak_slab"


@register_material
class SPRUCE_SLAB(BlockItem):
    name_id = "spruce_slab"
    name = "tile.woodSlab.spruce.name"
    target_block_id = "spruce_slab"


@register_material
class BIRCH_SLAB(BlockItem):
    name_id = "birch_slab"
    name = "tile.woodSlab.birch.name"
    target_block_id = "birch_slab"


@register_material
class JUNGLE_SLAB(BlockItem):
    name_id = "jungle_slab"
    name = "tile.woodSlab.jungle.name"
    target_block_id = "jungle_slab"


@register_material
class ACACIA_SLAB(BlockItem):
    name_id = "acacia_slab"
    name = "tile.woodSlab.acacia.name"
    target_block_id = "acacia_slab"


@register_material
class DARK_OAK_SLAB(BlockItem):
    name_id = "dark_oak_slab"
    name = "tile.woodSlab.big_oak.name"
    target_block_id = "dark_oak_slab"


@register_material
class STONE_SLAB(BlockItem):
    name_id = "stone_slab"
    name = "tile.stoneSlab.stone.name"
    target_block_id = "stone_slab"


@register_material
class COBBLESTONE_SLAB(BlockItem):
    name_id = "cobblestone_slab"
    name = "tile.stoneSlab.cobble.name"
    target_block_id = "cobblestone_slab"


@register_material
class SANDSTONE_SLAB(BlockItem):
    name_id = "sandstone_slab"
    name = "tile.stoneSlab.sand.name"
    target_block_id = "sandstone_slab"


@register_material
class RED_SANDSTONE_SLAB(BlockItem):
    name_id = "red_sandstone_slab"
    name = "tile.stoneSlab2.red_sandstone.name"
    target_block_id = "red_sandstone_slab"


@register_material
class OAK_STAIRS(BlockItem):
    name_id = "oak_stairs"
    name = "tile.stairsWood.name"
    target_block_id = "oak_stairs"


@register_material
class SPRUCE_STAIRS(BlockItem):
    name_id = "spruce_stairs"
    name = "tile.stairsWoodSpruce.name"
    target_block_id = "spruce_stairs"


@register_material
class BIRCH_STAIRS(BlockItem):
    name_id = "birch_stairs"
    name = "tile.stairsWoodBirch.name"
    target_block_id = "birch_stairs"


@register_material
class JUNGLE_STAIRS(BlockItem):
    name_id = "jungle_stairs"
    name = "tile.stairsWoodJungle.name"
    target_block_id = "jungle_stairs"


@register_material
class ACACIA_STAIRS(BlockItem):
    name_id = "acacia_stairs"
    name = "tile.stairsWoodAcacia.name"
    target_block_id = "acacia_stairs"


@register_material
class DARK_OAK_STAIRS(BlockItem):
    name_id = "dark_oak_stairs"
    name = "tile.stairsWoodDarkOak.name"
    target_block_id = "dark_oak_stairs"


@register_material
class STONE_STAIRS(BlockItem):
    name_id = "stone_stairs"
    name = "tile.stairsStone.name"
    target_block_id = "stone_stairs"


@register_material
class COBBLESTONE_STAIRS(BlockItem):
    name_id = "cobblestone_stairs"
    name = "tile.stairsStone.name"
    target_block_id = "cobblestone_stairs"


@register_material
class SANDSTONE_STAIRS(BlockItem):
    name_id = "sandstone_stairs"
    name = "tile.stairsSandStone.name"
    target_block_id = "sandstone_stairs"


@register_material
class RED_SANDSTONE_STAIRS(BlockItem):
    name_id = "red_sandstone_stairs"
    name = "tile.stairsRedSandStone.name"
    target_block_id = "red_sandstone_stairs"


@register_material
class OAK_FENCE(BlockItem):
    name_id = "oak_fence"
    name = "tile.fence.name"
    target_block_id = "oak_fence"


@register_material
class SPRUCE_FENCE(BlockItem):
    name_id = "spruce_fence"
    name = "tile.spruceFence.name"
    target_block_id = "spruce_fence"


@register_material
class BIRCH_FENCE(BlockItem):
    name_id = "birch_fence"
    name = "tile.birchFence.name"
    target_block_id = "birch_fence"


@register_material
class JUNGLE_FENCE(BlockItem):
    name_id = "jungle_fence"
    name = "tile.jungleFence.name"
    target_block_id = "jungle_fence"


@register_material
class ACACIA_FENCE(BlockItem):
    name_id = "acacia_fence"
    name = "tile.acaciaFence.name"
    target_block_id = "acacia_fence"


@register_material
class DARK_OAK_FENCE(BlockItem):
    name_id = "dark_oak_fence"
    name = "tile.darkOakFence.name"
    target_block_id = "dark_oak_fence"


@register_material
class COBBLESTONE_WALL(BlockItem):
    name_id = "cobblestone_wall"
    name = "tile.cobbleWall.normal.name"
    target_block_id = "cobblestone_wall"


@register_material
class LADDER(BlockItem):
    name_id = "ladder"
    name = "tile.ladder.name"
    target_block_id = "ladder"

@register_material
class MYCELIUM(BlockItem):
    name_id = "mycelium"
    name = "tile.mycel.name"
    target_block_id = "mycelium"


@register_material
class MUSHROOM_STEM(BlockItem):
    name_id = "mushroom_stem"
    name = "tile.mushroom.name"
    target_block_id = "mushroom_stem"


@register_material
class RED_MUSHROOM_BLOCK(BlockItem):
    name_id = "red_mushroom_block"
    name = "tile.mushroom.name"
    target_block_id = "red_mushroom_block"


@register_material
class BROWN_MUSHROOM_BLOCK(BlockItem):
    name_id = "brown_mushroom_block"
    name = "tile.mushroom.name"
    target_block_id = "brown_mushroom_block"


@register_material
class SHORT_GRASS(PlantBlockItem):
    name_id = "short_grass"
    name = "tile.tallgrass.grass.name"
    target_block_id = "short_grass"


@register_material
class TALL_GRASS(PlantBlockItem):
    name_id = "tall_grass"
    name = "tile.doublePlant.grass.name"
    target_block_id = "tall_grass"


@register_material
class LARGE_FERN(PlantBlockItem):
    name_id = "large_fern"
    name = "tile.doublePlant.fern.name"
    target_block_id = "large_fern"


@register_material
class SUNFLOWER(PlantBlockItem):
    name_id = "sunflower"
    name = "tile.doublePlant.sunflower.name"
    target_block_id = "sunflower"


@register_material
class ROSE_BUSH(PlantBlockItem):
    name_id = "rose_bush"
    name = "tile.doublePlant.rose.name"
    target_block_id = "rose_bush"


@register_material
class PEONY(PlantBlockItem):
    name_id = "peony"
    name = "tile.doublePlant.paeonia.name"
    target_block_id = "peony"


@register_material
class LILAC(PlantBlockItem):
    name_id = "lilac"
    name = "tile.doublePlant.syringa.name"
    target_block_id = "lilac"


@register_material
class POPPY(PlantBlockItem):
    name_id = "poppy"
    name = "tile.flower2.poppy.name"
    target_block_id = "poppy"


@register_material
class DANDELION(PlantBlockItem):
    name_id = "dandelion"
    name = "tile.flower1.dandelion.name"
    target_block_id = "dandelion"


@register_material
class SUGAR_CANE(PlantBlockItem):
    name_id = "sugar_cane"
    name = "tile.reeds.name"
    target_block_id = "sugar_cane"


@register_material
class FERN(PlantBlockItem):
    name_id = "fern"
    name = "tile.tallgrass.fern.name"
    target_block_id = "fern"


@register_material
class DEAD_BUSH(PlantBlockItem):
    name_id = "dead_bush"
    name = "tile.deadbush.name"
    target_block_id = "dead_bush"


@register_material
class BROWN_MUSHROOM(PlantBlockItem):
    name_id = "brown_mushroom"
    name = "tile.mushroom.name"
    target_block_id = "brown_mushroom"


@register_material
class RED_MUSHROOM(PlantBlockItem):
    name_id = "red_mushroom"
    name = "tile.mushroom.name"
    target_block_id = "red_mushroom"


@register_material
class VINE(PlantBlockItem):
    name_id = "vine"
    name = "tile.vine.name"
    target_block_id = "vine"


@register_material
class BLUE_ORCHID(PlantBlockItem):
    name_id = "blue_orchid"
    name = "tile.flower2.blueOrchid.name"
    target_block_id = "blue_orchid"


@register_material
class ALLIUM(PlantBlockItem):
    name_id = "allium"
    name = "tile.flower2.allium.name"
    target_block_id = "allium"


@register_material
class AZURE_BLUET(PlantBlockItem):
    name_id = "azure_bluet"
    name = "tile.flower2.houstonia.name"
    target_block_id = "azure_bluet"


@register_material
class OXEYE_DAISY(PlantBlockItem):
    name_id = "oxeye_daisy"
    name = "tile.flower2.oxeyeDaisy.name"
    target_block_id = "oxeye_daisy"


@register_material
class OAK_LEAVES(LeavesBlockItem):
    name_id = "oak_leaves"
    name = "tile.leaves.oak.name"
    target_block_id = "oak_leaves"


@register_material
class BIRCH_LEAVES(LeavesBlockItem):
    name_id = "birch_leaves"
    name = "tile.leaves.birch.name"
    target_block_id = "birch_leaves"


@register_material
class SPRUCE_LEAVES(LeavesBlockItem):
    name_id = "spruce_leaves"
    name = "tile.leaves.spruce.name"
    target_block_id = "spruce_leaves"


@register_material
class JUNGLE_LEAVES(LeavesBlockItem):
    name_id = "jungle_leaves"
    name = "tile.leaves.jungle.name"
    target_block_id = "jungle_leaves"


@register_material
class ACACIA_LEAVES(LeavesBlockItem):
    name_id = "acacia_leaves"
    name = "tile.leaves.acacia.name"
    target_block_id = "acacia_leaves"


@register_material
class DARK_OAK_LEAVES(LeavesBlockItem):
    name_id = "dark_oak_leaves"
    name = "tile.leaves.big_oak.name"
    target_block_id = "dark_oak_leaves"



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
    consumption_effects = (("hunger", 30 * 20, 0, 0.8),)


@register_material
class RAW_CHICKEN(Food):
    name_id = "chicken"
    name = "item.chickenRaw.name"
    _texture_path = "items.chicken_raw"
    food_value = 2
    saturation_modifier = 0.3
    consumption_effects = (("hunger", 30 * 20, 0, 0.3),)


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
class BAKED_POTATO(Food):
    name_id = "baked_potato"
    name = "item.bakedPotato.name"
    _texture_path = "items.potato_baked"
    food_value = 5
    saturation_modifier = 0.6


@register_material
class GOLDEN_APPLE(Food):
    name_id = "golden_apple"
    name = "item.appleGold.name"
    _texture_path = "items.apple_golden"
    food_value = 4
    saturation_modifier = 1.2
    always_edible = True
    tooltip_color = "AQUA"
    consumption_effects = (
        ("absorption", 2 * 60 * 20, 0, 1.0),
        ("regeneration", 5 * 20, 1, 1.0),
    )


@register_material(aliases=("notch_apple",))
class ENCHANTED_GOLDEN_APPLE(Food):
    name_id = "enchanted_golden_apple"
    # Minecraft 1.8 stores this as golden_apple damage value 1, so it shares
    # the ordinary apple's name and texture while the enchantment glint
    # distinguishes it.
    name = "item.appleGold.name"
    _texture_path = "items.apple_golden"
    food_value = 4
    saturation_modifier = 1.2
    always_edible = True
    enchantment_glint = True
    tooltip_color = "LIGHT_PURPLE"
    consumption_effects = (
        ("absorption", 2 * 60 * 20, 0, 1.0),
        ("regeneration", 30 * 20, 4, 1.0),
        ("resistance", 5 * 60 * 20, 0, 1.0),
        ("fire_resistance", 5 * 60 * 20, 0, 1.0),
    )


@register_material
class COAL(Material):
    name_id = "coal"
    name = "item.coal.name"
    _texture_path = "items.coal"


@register_material
class CHARCOAL(Material):
    name_id = "charcoal"
    name = "item.charcoal.name"
    _texture_path = "items.charcoal"


@register_material
class IRON_INGOT(Material):
    name_id = "iron_ingot"
    name = "item.ingotIron.name"
    _texture_path = "items.iron_ingot"


@register_material
class GOLD_INGOT(Material):
    name_id = "gold_ingot"
    name = "item.ingotGold.name"
    _texture_path = "items.gold_ingot"


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


class ThrowableMaterial(Material):
    """通过服务端实体注册表发射，并消耗真实物品堆叠。"""

    def right_click(self, stack, holder, *, target=None, context=None) -> bool:
        if stack is None or stack.is_empty() or getattr(holder, "health", 0) <= 0:
            return False
        mode = getattr(getattr(holder, "gamemode", None), "name_id", "survival")
        if mode == "spectator":
            return False

        from src.server.entity_registry import get_entity_type

        projectile_type = get_entity_type(self.name_id)
        projectile = projectile_type.from_shooter(holder)
        holder.world.spawn_entity(projectile)
        if mode != "creative":
            stack.reduce_amount(1)
        server = getattr(holder.world, "server", None)
        if server is not None:
            server.broadcast_sound(
                "random.bow",
                float(holder.x) + float(holder.width) * 0.5,
                float(holder.y)
                + float(getattr(holder, "eye_height", holder.height * 0.85)),
                int(getattr(holder, "z", 0)),
            )
        return True


@register_material
class EGG(ThrowableMaterial):
    name_id = "egg"
    name = "item.egg.name"
    _texture_path = "items.egg"


class CropPlantingMaterial(Material):
    crop_block_id = None

    @classmethod
    def create_crop(cls):
        from src.server.blocks import get_block_by_id

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
    consumption_effects = (("poison", 5 * 20, 0, 0.6),)


@register_material
class SPIDER_EYE(Food):
    name_id = "spider_eye"
    name = "item.spiderEye.name"
    _texture_path = "items.spider_eye"
    food_value = 2
    saturation_modifier = 0.8
    consumption_effects = (("poison", 5 * 20, 0, 1.0),)


@register_material(aliases=("fish_pufferfish",))
class PUFFERFISH(Food):
    name_id = "pufferfish"
    name = "item.fish.pufferfish.raw.name"
    _texture_path = "items.fish_pufferfish_raw"
    food_value = 1
    saturation_modifier = 0.1
    consumption_effects = (
        ("poison", 60 * 20, 3, 1.0),
        ("hunger", 15 * 20, 2, 1.0),
        ("nausea", 15 * 20, 1, 1.0),
    )


@register_material
class CARROT_ON_A_STICK(DamageableItem):
    name_id = "carrot_on_a_stick"
    name = "item.carrotOnAStick.name"
    _texture_path = "items.carrot_on_a_stick"
    max_damage = 25


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
class SHEARS(DamageableItem):
    name_id = "shears"
    name = "item.shears.name"
    _texture_path = "items.shears"
    max_damage = 238

    def on_mined_block(self, stack, holder, block) -> bool:
        if getattr(block, "block_id", "") == "fire":
            return False
        return self.damage_stack(stack, 1, holder)

    def on_successful_entity_interaction(self, stack, holder, target) -> bool:
        return self.damage_stack(stack, 1, holder)


@register_material
class WHITE_WOOL(BlockItem):
    name_id = "white_wool"
    name = "tile.cloth.white.name"
    target_block_id = "white_wool"



class ColoredBlockItem(BlockItem):
    pass

class ColoredGlass(ColoredBlockItem):
    texture_shadow = False

@register_material
class WHITE_STAINED_GLASS(ColoredGlass):
    name_id = "white_stained_glass"
    name = "tile.stainedGlass.white.name"
    target_block_id = "white_stained_glass"


@register_material
class ORANGE_WOOL(ColoredBlockItem):
    name_id = "orange_wool"
    name = "tile.cloth.orange.name"
    target_block_id = "orange_wool"


@register_material
class ORANGE_STAINED_GLASS(ColoredGlass):
    name_id = "orange_stained_glass"
    name = "tile.stainedGlass.orange.name"
    target_block_id = "orange_stained_glass"


@register_material
class MAGENTA_WOOL(ColoredBlockItem):
    name_id = "magenta_wool"
    name = "tile.cloth.magenta.name"
    target_block_id = "magenta_wool"


@register_material
class MAGENTA_STAINED_GLASS(ColoredGlass):
    name_id = "magenta_stained_glass"
    name = "tile.stainedGlass.magenta.name"
    target_block_id = "magenta_stained_glass"


@register_material
class LIGHT_BLUE_WOOL(ColoredBlockItem):
    name_id = "light_blue_wool"
    name = "tile.cloth.light_blue.name"
    target_block_id = "light_blue_wool"


@register_material
class LIGHT_BLUE_STAINED_GLASS(ColoredGlass):
    name_id = "light_blue_stained_glass"
    name = "tile.stainedGlass.light_blue.name"
    target_block_id = "light_blue_stained_glass"


@register_material
class YELLOW_WOOL(ColoredBlockItem):
    name_id = "yellow_wool"
    name = "tile.cloth.yellow.name"
    target_block_id = "yellow_wool"


@register_material
class YELLOW_STAINED_GLASS(ColoredGlass):
    name_id = "yellow_stained_glass"
    name = "tile.stainedGlass.yellow.name"
    target_block_id = "yellow_stained_glass"


@register_material
class LIME_WOOL(ColoredBlockItem):
    name_id = "lime_wool"
    name = "tile.cloth.lime.name"
    target_block_id = "lime_wool"


@register_material
class LIME_STAINED_GLASS(ColoredGlass):
    name_id = "lime_stained_glass"
    name = "tile.stainedGlass.lime.name"
    target_block_id = "lime_stained_glass"


@register_material
class PINK_WOOL(ColoredBlockItem):
    name_id = "pink_wool"
    name = "tile.cloth.pink.name"
    target_block_id = "pink_wool"


@register_material
class PINK_STAINED_GLASS(ColoredGlass):
    name_id = "pink_stained_glass"
    name = "tile.stainedGlass.pink.name"
    target_block_id = "pink_stained_glass"


@register_material
class GRAY_WOOL(ColoredBlockItem):
    name_id = "gray_wool"
    name = "tile.cloth.gray.name"
    target_block_id = "gray_wool"


@register_material
class GRAY_STAINED_GLASS(ColoredGlass):
    name_id = "gray_stained_glass"
    name = "tile.stainedGlass.gray.name"
    target_block_id = "gray_stained_glass"


@register_material
class LIGHT_GRAY_WOOL(ColoredBlockItem):
    name_id = "light_gray_wool"
    name = "tile.cloth.silver.name"
    target_block_id = "light_gray_wool"


@register_material
class LIGHT_GRAY_STAINED_GLASS(ColoredGlass):
    name_id = "light_gray_stained_glass"
    name = "tile.stainedGlass.silver.name"
    target_block_id = "light_gray_stained_glass"


@register_material
class CYAN_WOOL(ColoredBlockItem):
    name_id = "cyan_wool"
    name = "tile.cloth.cyan.name"
    target_block_id = "cyan_wool"


@register_material
class CYAN_STAINED_GLASS(ColoredGlass):
    name_id = "cyan_stained_glass"
    name = "tile.stainedGlass.cyan.name"
    target_block_id = "cyan_stained_glass"


@register_material
class PURPLE_WOOL(ColoredBlockItem):
    name_id = "purple_wool"
    name = "tile.cloth.purple.name"
    target_block_id = "purple_wool"


@register_material
class PURPLE_STAINED_GLASS(ColoredGlass):
    name_id = "purple_stained_glass"
    name = "tile.stainedGlass.purple.name"
    target_block_id = "purple_stained_glass"


@register_material
class BLUE_WOOL(ColoredBlockItem):
    name_id = "blue_wool"
    name = "tile.cloth.blue.name"
    target_block_id = "blue_wool"


@register_material
class BLUE_STAINED_GLASS(ColoredGlass):
    name_id = "blue_stained_glass"
    name = "tile.stainedGlass.blue.name"
    target_block_id = "blue_stained_glass"


@register_material
class BROWN_WOOL(ColoredBlockItem):
    name_id = "brown_wool"
    name = "tile.cloth.brown.name"
    target_block_id = "brown_wool"


@register_material
class BROWN_STAINED_GLASS(ColoredGlass):
    name_id = "brown_stained_glass"
    name = "tile.stainedGlass.brown.name"
    target_block_id = "brown_stained_glass"


@register_material
class GREEN_WOOL(ColoredBlockItem):
    name_id = "green_wool"
    name = "tile.cloth.green.name"
    target_block_id = "green_wool"


@register_material
class GREEN_STAINED_GLASS(ColoredGlass):
    name_id = "green_stained_glass"
    name = "tile.stainedGlass.green.name"
    target_block_id = "green_stained_glass"


@register_material
class RED_WOOL(ColoredBlockItem):
    name_id = "red_wool"
    name = "tile.cloth.red.name"
    target_block_id = "red_wool"


@register_material
class RED_STAINED_GLASS(ColoredGlass):
    name_id = "red_stained_glass"
    name = "tile.stainedGlass.red.name"
    target_block_id = "red_stained_glass"


@register_material
class BLACK_WOOL(ColoredBlockItem):
    name_id = "black_wool"
    name = "tile.cloth.black.name"
    target_block_id = "black_wool"


@register_material
class BLACK_STAINED_GLASS(ColoredGlass):
    name_id = "black_stained_glass"
    name = "tile.stainedGlass.black.name"
    target_block_id = "black_stained_glass"



@register_material
class BRICKS(BlockItem):
    name_id = "bricks"
    name = "tile.bricks.name"
    target_block_id = "bricks"


@register_material
class BOOKSHELF(BlockItem):
    name_id = "bookshelf"
    name = "tile.bookshelf.name"
    target_block_id = "bookshelf"


@register_material
class END_STONE(BlockItem):
    name_id = "end_stone"
    name = "tile.whiteStone.name"
    target_block_id = "end_stone"


@register_material
class HAY_BLOCK(BlockItem):
    name_id = "hay_block"
    name = "tile.hayBlock.name"
    target_block_id = "hay_block"


@register_material
class NETHER_BRICKS(BlockItem):
    name_id = "nether_bricks"
    name = "tile.netherBrick.name"
    target_block_id = "nether_bricks"


@register_material
class NETHERRACK(BlockItem):
    name_id = "netherrack"
    name = "tile.netherrack.name"
    target_block_id = "netherrack"


@register_material
class PRISMARINE(BlockItem):
    name_id = "prismarine"
    name = "tile.prismarine.rough.name"
    target_block_id = "prismarine"


@register_material
class PRISMARINE_BRICKS(BlockItem):
    name_id = "prismarine_bricks"
    name = "tile.prismarine.bricks.name"
    target_block_id = "prismarine_bricks"


@register_material
class DARK_PRISMARINE(BlockItem):
    name_id = "dark_prismarine"
    name = "tile.prismarine.dark.name"
    target_block_id = "dark_prismarine"


@register_material
class QUARTZ_BLOCK(BlockItem):
    name_id = "quartz_block"
    name = "tile.quartz_block.name"
    target_block_id = "quartz_block"


@register_material
class QUARTZ_COLUMN(BlockItem):
    name_id = "quartz_column"
    name = "tile.quartz_block_lines.name"
    target_block_id = "quartz_column"


@register_material
class CHISELED_QUARTZ_BLOCK(BlockItem):
    name_id = "chiseled_quartz_block"
    name = "tile.quartz_block_chiseled.name"
    target_block_id = "chiseled_quartz_block"


@register_material
class STONE_BRICKS(BlockItem):
    name_id = "stone_bricks"
    name = "tile.stonebrick.name"
    target_block_id = "stone_bricks"


@register_material
class MOSSY_STONE_BRICKS(BlockItem):
    name_id = "mossy_stone_bricks"
    name = "tile.stonebrick.mossy.name"
    target_block_id = "mossy_stone_bricks"


@register_material
class CRACKED_STONE_BRICKS(BlockItem):
    name_id = "cracked_stone_bricks"
    name = "tile.stonebrick.cracked.name"
    target_block_id = "cracked_stone_bricks"


@register_material
class CHISELED_STONE_BRICKS(BlockItem):
    name_id = "chiseled_stone_bricks"
    name = "tile.stonebrick.chiseled.name"
    target_block_id = "chiseled_stone_bricks"


class STICK(Material):
    name_id = "stick"
    name = "item.stick.name"
    _texture_path = "items.stick"


@register_material
class FLINT_AND_STEEL(DamageableItem):
    name_id = "flint_and_steel"
    name = "item.flintAndSteel.name"
    _texture_path = "items.flint_and_steel"
    max_damage = 64
    ignites_blocks = True

    def on_successful_block_use(self, stack, holder, block) -> bool:
        return self.damage_stack(stack, 1, holder)


class Armor(DamageableItem):
    """Minecraft-style wearable armor backed by equipment attributes."""

    equipment_slot = "head"
    defense = 0.0
    toughness = 0.0
    armor_texture = "iron"

    @classmethod
    def get_default_attribute_modifiers(cls):
        modifiers = [
            {
                "type": "minecraft:armor",
                "id": f"minecraft:armor.{cls.equipment_slot}",
                "amount": cls.defense,
                "operation": "add_value",
                "slot": cls.equipment_slot,
            }
        ]
        if cls.toughness:
            modifiers.append(
                {
                    "type": "minecraft:armor_toughness",
                    "id": f"minecraft:armor_toughness.{cls.equipment_slot}",
                    "amount": cls.toughness,
                    "operation": "add_value",
                    "slot": cls.equipment_slot,
                }
            )
        return tuple(modifiers)

    def right_click(self, stack, holder, *, target=None, context=None) -> bool:
        """Equip from the selected hand when the matching armor slot is empty."""
        equipment = getattr(holder, "equipment", None)
        slot = self.equipment_slot
        if not isinstance(equipment, dict) or slot not in equipment:
            return False
        worn = equipment[slot]
        if worn is not None and not worn.is_empty():
            return False

        from src.server.item_class import ItemStack

        equipment[slot] = ItemStack(stack.material, 1, deepcopy(stack.nbt))
        stack.reduce_amount(1)
        holder._equipment_attribute_signature = None
        return True


class LeatherArmor(Armor):
    armor_texture = "leather"
    default_color = 0xA06540

    @classmethod
    def get_dye_color(cls, stack) -> int:
        color = cls.default_color
        nbt = getattr(stack, "nbt", {})
        raw_color = nbt.get("minecraft:dyed_color")
        if isinstance(raw_color, dict):
            raw_color = raw_color.get("rgb")
        if raw_color is None and isinstance(nbt.get("display"), dict):
            raw_color = nbt["display"].get("color")
        try:
            if raw_color is not None:
                color = int(raw_color) & 0xFFFFFF
        except (TypeError, ValueError):
            pass
        return color

    def get_texture_variant_key(self, stack):
        return self.get_dye_color(stack)

    @client_method
    def get_stack_texture(self, stack, size: float, client):
        """Tint the dyeable icon, then draw its undyed overlay on top."""
        base = client.resources_manager.get_texture_img(self._texture_path)
        overlay = client.resources_manager.get_texture_img(
            f"{self._texture_path}_overlay"
        )
        color = self.get_dye_color(stack)
        cache = type(self).__dict__.get("_dyed_texture_cache")
        if cache is None:
            cache = {}
            type(self)._dyed_texture_cache = cache
        key = (round(float(size), 4), color, base, overlay)
        cached = cache.get(key)
        if cached is not None:
            return cached

        combined = base.copy()
        combined.fill(
            ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF, 255),
            special_flags=pygame.BLEND_RGBA_MULT,
        )
        combined.blit(overlay, (0, 0))
        scaled = pygame.transform.scale(
            combined,
            (
                max(1, round(combined.get_width() * float(size))),
                max(1, round(combined.get_height() * float(size))),
            ),
        )
        cache[key] = scaled
        if len(cache) > 64:
            cache.pop(next(iter(cache)))
        return scaled


class ChainmailArmor(Armor):
    armor_texture = "chainmail"


class IronArmor(Armor):
    armor_texture = "iron"


class GoldenArmor(Armor):
    armor_texture = "gold"


class DiamondArmor(Armor):
    armor_texture = "diamond"
    toughness = 2.0


@register_material
class LEATHER_HELMET(LeatherArmor):
    name_id = "leather_helmet"
    name = "item.helmetCloth.name"
    _texture_path = "items.leather_helmet"
    equipment_slot = "head"
    defense = 1.0
    max_damage = 55


@register_material
class LEATHER_CHESTPLATE(LeatherArmor):
    name_id = "leather_chestplate"
    name = "item.chestplateCloth.name"
    _texture_path = "items.leather_chestplate"
    equipment_slot = "chest"
    defense = 3.0
    max_damage = 80


@register_material
class LEATHER_LEGGINGS(LeatherArmor):
    name_id = "leather_leggings"
    name = "item.leggingsCloth.name"
    _texture_path = "items.leather_leggings"
    equipment_slot = "legs"
    defense = 2.0
    max_damage = 75


@register_material
class LEATHER_BOOTS(LeatherArmor):
    name_id = "leather_boots"
    name = "item.bootsCloth.name"
    _texture_path = "items.leather_boots"
    equipment_slot = "feet"
    defense = 1.0
    max_damage = 65


@register_material
class CHAINMAIL_HELMET(ChainmailArmor):
    name_id = "chainmail_helmet"
    name = "item.helmetChain.name"
    _texture_path = "items.chainmail_helmet"
    equipment_slot = "head"
    defense = 2.0
    max_damage = 165


@register_material
class CHAINMAIL_CHESTPLATE(ChainmailArmor):
    name_id = "chainmail_chestplate"
    name = "item.chestplateChain.name"
    _texture_path = "items.chainmail_chestplate"
    equipment_slot = "chest"
    defense = 5.0
    max_damage = 240


@register_material
class CHAINMAIL_LEGGINGS(ChainmailArmor):
    name_id = "chainmail_leggings"
    name = "item.leggingsChain.name"
    _texture_path = "items.chainmail_leggings"
    equipment_slot = "legs"
    defense = 4.0
    max_damage = 225


@register_material
class CHAINMAIL_BOOTS(ChainmailArmor):
    name_id = "chainmail_boots"
    name = "item.bootsChain.name"
    _texture_path = "items.chainmail_boots"
    equipment_slot = "feet"
    defense = 1.0
    max_damage = 195


@register_material
class IRON_HELMET(IronArmor):
    name_id = "iron_helmet"
    name = "item.helmetIron.name"
    _texture_path = "items.iron_helmet"
    equipment_slot = "head"
    defense = 2.0
    max_damage = 165


@register_material
class IRON_CHESTPLATE(IronArmor):
    name_id = "iron_chestplate"
    name = "item.chestplateIron.name"
    _texture_path = "items.iron_chestplate"
    equipment_slot = "chest"
    defense = 6.0
    max_damage = 240


@register_material
class IRON_LEGGINGS(IronArmor):
    name_id = "iron_leggings"
    name = "item.leggingsIron.name"
    _texture_path = "items.iron_leggings"
    equipment_slot = "legs"
    defense = 5.0
    max_damage = 225


@register_material
class IRON_BOOTS(IronArmor):
    name_id = "iron_boots"
    name = "item.bootsIron.name"
    _texture_path = "items.iron_boots"
    equipment_slot = "feet"
    defense = 2.0
    max_damage = 195


@register_material
class GOLDEN_HELMET(GoldenArmor):
    name_id = "golden_helmet"
    name = "item.helmetGold.name"
    _texture_path = "items.gold_helmet"
    equipment_slot = "head"
    defense = 2.0
    max_damage = 77


@register_material
class GOLDEN_CHESTPLATE(GoldenArmor):
    name_id = "golden_chestplate"
    name = "item.chestplateGold.name"
    _texture_path = "items.gold_chestplate"
    equipment_slot = "chest"
    defense = 5.0
    max_damage = 112


@register_material
class GOLDEN_LEGGINGS(GoldenArmor):
    name_id = "golden_leggings"
    name = "item.leggingsGold.name"
    _texture_path = "items.gold_leggings"
    equipment_slot = "legs"
    defense = 3.0
    max_damage = 105


@register_material
class GOLDEN_BOOTS(GoldenArmor):
    name_id = "golden_boots"
    name = "item.bootsGold.name"
    _texture_path = "items.gold_boots"
    equipment_slot = "feet"
    defense = 1.0
    max_damage = 91


@register_material
class DIAMOND_HELMET(DiamondArmor):
    name_id = "diamond_helmet"
    name = "item.helmetDiamond.name"
    _texture_path = "items.diamond_helmet"
    equipment_slot = "head"
    defense = 3.0
    max_damage = 363


@register_material
class DIAMOND_CHESTPLATE(DiamondArmor):
    name_id = "diamond_chestplate"
    name = "item.chestplateDiamond.name"
    _texture_path = "items.diamond_chestplate"
    equipment_slot = "chest"
    defense = 8.0
    max_damage = 528


@register_material
class DIAMOND_LEGGINGS(DiamondArmor):
    name_id = "diamond_leggings"
    name = "item.leggingsDiamond.name"
    _texture_path = "items.diamond_leggings"
    equipment_slot = "legs"
    defense = 6.0
    max_damage = 495


@register_material
class DIAMOND_BOOTS(DiamondArmor):
    name_id = "diamond_boots"
    name = "item.bootsDiamond.name"
    _texture_path = "items.diamond_boots"
    equipment_slot = "feet"
    defense = 3.0
    max_damage = 429


class Tool(DamageableItem):
    tool_type = None
    tier = "wood"
    mining_speed = 1.0
    attack_damage_modifier = 0.0
    attack_speed_modifier = -3.0
    max_damage = 59

    def on_mined_block(self, stack, holder, block) -> bool:
        if float(getattr(block, "hardness", 0.0)) == 0.0:
            return False
        return self.damage_stack(stack, 1, holder)

    def on_post_hurt_enemy(self, stack, holder, target) -> bool:
        return self.damage_stack(stack, 2, holder)

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
    def get_anchor(self, client=None):
        """
        用于获取渲染时客户端的手持点位，第三个值为缩放倍率，第四个参数为旋转度数（角度制）
        :return:
        """
        return {"anchor": (0.7, 0.7), "offset": (0, 0), "scale": 1.0, "rotation": -135}


class Sword(Tool):
    tool_type = "sword"
    attack_damage_modifier = 4.0
    attack_speed_modifier = -2.4

    def right_click(self, stack, holder, *, target=None, context=None) -> bool:
        request_blocking = getattr(holder, "request_blocking", None)
        return callable(request_blocking) and bool(request_blocking(stack))

    def on_post_hurt_enemy(self, stack, holder, target) -> bool:
        return self.damage_stack(stack, 1, holder)


@register_material
class WOODEN_SWORD(Sword):
    name_id = "wooden_sword"
    name = "item.swordWood.name"
    _texture_path = "items.wood_sword"


@register_material
class GOLDEN_SWORD(WOODEN_SWORD):
    name_id = "golden_sword"
    name = "item.swordGold.name"
    _texture_path = "items.gold_sword"
    tier = "gold"
    max_damage = 32


@register_material
class STONE_SWORD(WOODEN_SWORD):
    name_id = "stone_sword"
    name = "item.swordStone.name"
    _texture_path = "items.stone_sword"
    tier = "stone"
    attack_damage_modifier = 5.0
    max_damage = 131


@register_material
class IRON_SWORD(WOODEN_SWORD):
    name_id = "iron_sword"
    name = "item.swordIron.name"
    _texture_path = "items.iron_sword"
    tier = "iron"
    attack_damage_modifier = 6.0
    max_damage = 250


@register_material
class DIAMOND_SWORD(WOODEN_SWORD):
    name_id = "diamond_sword"
    name = "item.swordDiamond.name"
    _texture_path = "items.diamond_sword"
    tier = "diamond"
    attack_damage_modifier = 7.0
    max_damage = 1561


@register_material
class WOODEN_AXE(Tool):
    name_id = "wooden_axe"
    name = "item.hatchetWood.name"
    _texture_path = "items.wood_axe"
    tool_type = "axe"
    mining_speed = 2.0
    attack_damage_modifier = 3.0


@register_material
class GOLDEN_AXE(WOODEN_AXE):
    name_id = "golden_axe"
    name = "item.hatchetGold.name"
    _texture_path = "items.gold_axe"
    tier = "gold"
    mining_speed = 12.0
    max_damage = 32


@register_material
class STONE_AXE(WOODEN_AXE):
    name_id = "stone_axe"
    name = "item.hatchetStone.name"
    _texture_path = "items.stone_axe"
    tier = "stone"
    mining_speed = 4.0
    attack_damage_modifier = 4.0
    max_damage = 131


@register_material
class IRON_AXE(WOODEN_AXE):
    name_id = "iron_axe"
    name = "item.hatchetIron.name"
    _texture_path = "items.iron_axe"
    tier = "iron"
    mining_speed = 6.0
    attack_damage_modifier = 5.0
    max_damage = 250


@register_material
class DIAMOND_AXE(WOODEN_AXE):
    name_id = "diamond_axe"
    name = "item.hatchetDiamond.name"
    _texture_path = "items.diamond_axe"
    tier = "diamond"
    mining_speed = 8.0
    attack_damage_modifier = 6.0
    max_damage = 1561


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
class GOLDEN_PICKAXE(WOODEN_PICKAXE):
    name_id = "golden_pickaxe"
    name = "item.pickaxeGold.name"
    _texture_path = "items.gold_pickaxe"
    tier = "gold"
    mining_speed = 12.0
    max_damage = 32


@register_material
class STONE_PICKAXE(WOODEN_PICKAXE):
    name_id = "stone_pickaxe"
    name = "item.pickaxeStone.name"
    _texture_path = "items.stone_pickaxe"
    tier = "stone"
    mining_speed = 4.0
    attack_damage_modifier = 2.0
    max_damage = 131


@register_material
class IRON_PICKAXE(WOODEN_PICKAXE):
    name_id = "iron_pickaxe"
    name = "item.pickaxeIron.name"
    _texture_path = "items.iron_pickaxe"
    tier = "iron"
    mining_speed = 6.0
    attack_damage_modifier = 3.0
    max_damage = 250


@register_material
class DIAMOND_PICKAXE(WOODEN_PICKAXE):
    name_id = "diamond_pickaxe"
    name = "item.pickaxeDiamond.name"
    _texture_path = "items.diamond_pickaxe"
    tier = "diamond"
    mining_speed = 8.0
    attack_damage_modifier = 4.0
    max_damage = 1561


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

    def on_successful_block_use(self, stack, holder, block) -> bool:
        return self.damage_stack(stack, 1, holder)

@register_material
class DIAMOND(Material):
    name_id = "diamond"
    name = "item.diamond.name"
    _texture_path = "items.diamond"


@register_material
class SNOWBALL(ThrowableMaterial):
    name_id = "snowball"
    name = "item.snowball.name"
    _texture_path = "items.snowball"


def get_block_item(block):
    """Return only an explicitly registered item form for ``block``."""
    block_id = getattr(block, "block_id", "air")
    material_type = _material_registry.get("minecraft", {}).get(block_id)
    if material_type is None or not issubclass(material_type, BlockItem):
        return AIR()
    return material_type()


def get_material_by_id(material_id: str):
    material_id = str(material_id)
    if ":" in material_id:
        namespace, key = material_id.split(":", 1)
    else:
        namespace, key = "minecraft", material_id
    material_type = _material_registry.get(namespace, {}).get(key)
    if material_type is not None:
        return material_type()
    return AIR()


def get_creative_inventory_materials() -> tuple[Material, ...]:
    """Build the unsplit creative catalogue from registered materials.

    Registry aliases are de-duplicated by their resulting item id. Air is
    intentionally omitted because it represents an empty stack rather than
    something the player can take. Blocks appear here only when their BlockItem
    material was explicitly registered above.
    """
    result: list[Material] = []
    seen: set[str] = set()

    def append(material: Material) -> None:
        material_id = str(getattr(material, "name_id", "air"))
        if material_id == "air" or material_id in seen:
            return
        seen.add(material_id)
        result.append(material)

    for namespace in _material_registry.values():
        for material_type in namespace.values():
            append(material_type())
    return tuple(result)
