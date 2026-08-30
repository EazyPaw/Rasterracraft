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
class BAKED_POTATO(Food):
    name_id = "baked_potato"
    name = "item.bakedPotato.name"
    _texture_path = "items.potato_baked"
    food_value = 5
    saturation_modifier = 0.6


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


@register_material
class EGG(Material):
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
        return {"anchor": (0.7, 0.7), "offset": (0, 0), "scale": 0.8, "rotation": -135}


class Sword(Tool):
    tool_type = "sword"
    attack_damage_modifier = 4.0
    attack_speed_modifier = -2.4

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
class SNOWBALL(Material):
    name_id = "snowball"
    name = "item.snowball.name"
    _texture_path = "items.snowball"

    def right_click(self, stack, holder, *, target=None, context=None) -> bool:
        if stack is None or stack.is_empty() or getattr(holder, "health", 0) <= 0:
            return False
        if (
            getattr(getattr(holder, "gamemode", None), "name_id", "survival")
            == "spectator"
        ):
            return False

        from src.server.entities.snow_ball import SnowBall

        projectile = SnowBall.from_shooter(holder)
        holder.world.spawn_entity(projectile)
        mode = getattr(getattr(holder, "gamemode", None), "name_id", "survival")
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



_block_item_types: dict[str, type[BlockItem]] = {}


def get_block_item(block):
    block_id = getattr(block, "block_id", "air")
    if block_id == "air":
        return AIR()
    item_type = _block_item_types.get(block_id)
    if item_type is None:
        item_type = type(
            f"{block_id.title().replace('_', '')}Item",
            (BlockItem,),
            {
                "name_id": block_id,
                "name": getattr(block, "name", block_id),
                "target_block_id": block_id,
            },
        )
        _block_item_types[block_id] = item_type
    return item_type()


def get_material_by_id(material_id: str):
    material_id = str(material_id)
    if ":" in material_id:
        namespace, key = material_id.split(":", 1)
    else:
        namespace, key = "minecraft", material_id
    material_type = _material_registry.get(namespace, {}).get(key)
    if material_type is not None:
        return material_type()
    from src.server import blocks

    if blocks.has_block_id(key):
        return get_block_item(blocks.get_block_by_id(key))

    if key.endswith("s") and blocks.has_block_id(key[:-1]):
        return get_block_item(blocks.get_block_by_id(key[:-1]))
    return AIR()


def get_creative_inventory_materials() -> tuple[Material, ...]:
    """Build the unsplit creative catalogue from registered items and blocks.

    Registry aliases and blocks which already have a dedicated item are de-duplicated
    by their resulting item id. Air is intentionally omitted because it represents an
    empty stack rather than something the player can take.
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

    from src.server import blocks

    for block_id in blocks.get_registered_block_ids():
        append(get_material_by_id(block_id))
    return tuple(result)
