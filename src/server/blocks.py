# Commented and arranged by ChatGPT
import os

import src.server.materials as materials
from src.server.biome import get_biome_by_id, get_precipitation_type
from src.server.damange_type import IN_FIRE

if os.environ.get("PYCRAFT_CLIENT") == "1":
    pass

from src.server.block_class import *
from src.server.materials import (
    CARROT as CARROT_ITEM,
    COBBLESTONE as COBBLESTONE_ITEM,
    POISONOUS_POTATO as POISONOUS_POTATO_ITEM,
    POTATO as POTATO_ITEM,
    WHEAT as WHEAT_ITEM,
    WHEAT_SEEDS as WHEAT_SEEDS_ITEM,
)
from src.server.tags import BlockTag
from src.server.utils import client_method
from src.server.inventory import Inventory


_BLOCK_REGISTRY: dict[str, type[Block]] = {}


def register_block(cls=None, /):
    """Register a block class by its ``block_id``.

    Used as ``@register_block`` in the same way materials and entities are
    registered. Duplicate IDs fail immediately during module import instead
    of silently replacing a class in a lazy subclass scan.
    """
    if cls is None:
        return lambda block_cls: register_block(block_cls)

    block_id = getattr(cls, "block_id", None)
    if block_id is None:
        raise ValueError(f"{cls.__name__} must define block_id")
    block_id = str(block_id)
    existing = _BLOCK_REGISTRY.get(block_id)
    if existing is not None and existing is not cls:
        raise ValueError(f"Duplicate block registration: {block_id}")
    _BLOCK_REGISTRY[block_id] = cls
    return cls


@register_block
class AIR(Block):
    block_id = "air"
    name = "tile.air.name"
    _texture_path = None
    solid = False
    collision_box = EMPTY
    replaceable = True
    breakable = False
    light_attenuation = 1
    has_transparent_pixels = True  # AIR 无纹理，需手动指定

    @classmethod
    @client_method
    def get_texture(cls, size, client):
        return None


class TillableBlockMixin:
    till_sound = "item.hoe.till"

    @staticmethod
    def accepts_item_use(material) -> bool:
        return getattr(material, "tool_type", None) == "hoe"

    def on_right_click(self, player) -> bool:
        material = player.get_held_item().material
        if not self.accepts_item_use(material) or self.location is None:
            return False
        world = self.location.world
        if not isinstance(world.get_block(self.location.add(0, 1, 0)), AIR):
            return False
        location = self.location
        farmland = FARMLAND()
        world.set_block(farmland, location)
        if world.get_block(location) is not farmland:
            return False
        server = getattr(world, "server", None)
        broadcast_sound = getattr(server, "broadcast_sound", None)
        if callable(broadcast_sound):
            broadcast_sound(
                self.till_sound,
                float(location.x) + 0.5,
                float(location.y) + 0.5,
                int(location.z),
            )
        return True


@register_block
class STONE(Block):
    block_id = "stone"
    name = "tile.stone.stone.name"
    _texture_path = "blocks.stone"
    blast_resistance = 6.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    drops = (BlockDrop(COBBLESTONE_ITEM),)


@register_block
class DEEPSLATE(Block):
    """Deep underground stone used by the Water World flat preset.

    The current resource pack predates deepslate, so stone is used as a safe
    visual fallback until a dedicated texture is added.
    """

    block_id = "deepslate"
    name = "Deepslate"
    _texture_path = "blocks.stone"
    blast_resistance = 6.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    drops = (BlockDrop(COBBLESTONE_ITEM),)


@register_block
class COBBLESTONE(Block):
    block_id = "cobblestone"
    name = "tile.stonebrick.name"
    _texture_path = "blocks.cobblestone"
    blast_resistance = 6.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class OBSIDIAN(Block):
    block_id = "obsidian"
    name = "tile.obsidian.name"
    _texture_path = "blocks.obsidian"
    hardness = 50.0
    blast_resistance = 1200.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "diamond"


@register_block
class GRANITE(Block):
    block_id = "granite"
    name = "tile.stone.granite.name"
    _texture_path = "blocks.stone_granite"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class DIORITE(Block):
    block_id = "diorite"
    name = "tile.stone.diorite.name"
    _texture_path = "blocks.stone_diorite"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class ANDESITE(Block):
    block_id = "andesite"
    name = "tile.stone.andesite.name"
    _texture_path = "blocks.stone_andesite"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class BEDROCK(Block):
    block_id = "bedrock"
    name = "tile.bedrock.name"
    _texture_path = "blocks.bedrock"
    breakable = False
    hardness = -1
    blast_resistance = 3_600_000.0


@register_block
class DIRT(TillableBlockMixin, Block):
    block_id = "dirt"
    name = "tile.dirt.name"
    _texture_path = "blocks.dirt"
    break_sound = "dig.gravel"
    hardness = 0.5
    preferred_tool = "shovel"


@register_block
class COARSE_DIRT(Block):
    block_id = "coarse_dirt"
    name = "tile.dirt.coarse.name"
    _texture_path = "blocks.coarse_dirt"
    break_sound = "dig.gravel"
    hardness = 0.5
    preferred_tool = "shovel"


@register_block
class PODZOL(Block):
    block_id = "podzol"
    name = "tile.dirt.podzol.name"
    _texture_path = "blocks.dirt_podzol_side"
    break_sound = "dig.gravel"
    hardness = 0.5
    preferred_tool = "shovel"
    Tags = [BlockTag.GRASS_BLOCKS]


@register_block
class GRASS_BLOCK(TillableBlockMixin, Block):
    block_id = "grass_block"
    name = "tile.grass.name"
    light_attenuation = 5
    break_sound = "dig.gravel"
    hardness = 0.6
    preferred_tool = "shovel"
    _side_texture_cache = {}  # 缓存不同尺寸的侧面纹理
    Tags = [BlockTag.GRASS_BLOCKS, BlockTag.ANIMALS_SPAWNABLE_ON]
    drops = (BlockDrop(materials.DIRT),)

    def __init__(self, snowed=False):
        super().__init__()
        self.snowed = snowed

    @client_method
    def get_texture(self, size, client):
        """
        获取草方块侧面纹理：将染色后的 grass_side_overlay 组合到 grass_side 上。
        (client 由 @client_only 自动注入)
        """
        x = self.location.x
        y = self.location.y
        biome_id = self.location.world.get_biome(x, y)
        biome = get_biome_by_id(biome_id)
        cache_key = (size, bool(self.snowed), biome_id, biome.grass_color)

        # 检查缓存
        if cache_key in self._side_texture_cache:
            return self._side_texture_cache[cache_key]

        if self.snowed:
            tex = client.resources_manager.get_texture_img("blocks.grass_side_snowed")
            final_texture = pygame.transform.scale(tex, (size, size))
            self._side_texture_cache[cache_key] = final_texture.convert_alpha()
            return self._side_texture_cache[cache_key]

        # 1. 获取基础材质
        base_side = client.resources_manager.get_texture_img("blocks.grass_side")
        overlay_raw = client.resources_manager.get_texture_img(
            "blocks.grass_side_overlay"
        )

        if base_side is None or overlay_raw is None:
            # 如果缺少任一材质，返回默认纹理或基础纹理
            return base_side or overlay_raw

        # 2. 缩放至目标尺寸
        base_side_scaled = pygame.transform.scale(base_side, (size, size))
        overlay_scaled = pygame.transform.scale(overlay_raw, (size, size))

        # 3. 染色 overlay (使用 RGB 元组 (30, 50, 70))
        # 注意：grass_side_overlay 通常是灰度图或带有透明度变化的图
        stained_overlay = client.resources_manager.biome_stain(
            overlay_scaled, self.location
        ).convert_alpha()

        # 4. 组合图层
        # 使用 stain.py 中的 overlay_surfaces 逻辑，或者直接使用 pygame 的 blit
        final_texture = base_side_scaled.convert_alpha()
        final_texture.blit(stained_overlay, (0, 0))

        # 5. 存入缓存
        self._side_texture_cache[cache_key] = final_texture.convert_alpha()

        return final_texture

    def on_update(self):
        self.snowed = isinstance(
            self.location.world.get_block(self.location.add(0, 1, 0)), SNOW
        )


@register_block
class FARMLAND(Block):
    block_id = "farmland"
    name = "tile.farmland.name"
    _texture_path = "blocks.farmland_dry"
    _texture_cache = {}
    solid = True
    has_transparent_pixels = True
    MAX_MOISTURE = 7

    def __init__(self, moisture=0, nbt=None):
        self.moisture = max(0, min(self.MAX_MOISTURE, int(moisture)))
        super().__init__(nbt)

    def accepts_item_use(self, material) -> bool:
        return callable(getattr(material, "create_crop", None))

    def on_right_click(self, player) -> bool:
        stack = player.get_held_item()
        create_crop = getattr(stack.material, "create_crop", None)
        if stack.is_empty() or not callable(create_crop) or self.location is None:
            return False
        world = self.location.world
        crop_location = self.location.add(0, 1, 0)
        if not isinstance(world.get_block(crop_location), AIR):
            return False
        crop = create_crop()
        if not isinstance(crop, Crop):
            return False
        world.set_block(crop, crop_location)
        if world.get_block(crop_location) is not crop:
            return False
        if getattr(player.gamemode, "name_id", "survival") != "creative":
            stack.reduce_amount(1)
            player.sync_inventory()
        return True

    @client_method
    def get_texture(self, size, client):
        wet = self.moisture == self.MAX_MOISTURE
        if wet:
            base_texture = client.resources_manager.get_texture_img(
                "blocks.farmland_wet"
            )
        else:
            base_texture = client.resources_manager.get_texture_img(
                "blocks.farmland_dry"
            )
        cache_key = (int(size), wet, base_texture)
        if cache_key in self._texture_cache:
            return self._texture_cache[cache_key]
        width, height = base_texture.size
        layer_height = height * 7 // 8
        rect = pygame.Rect(0, height - layer_height, width, layer_height)
        tex = base_texture.subsurface(rect).copy()
        tex_h = size * 7 // 8
        final_texture = pygame.transform.scale(tex, (size, tex_h))
        self._texture_cache[cache_key] = final_texture.convert_alpha()
        return self._texture_cache[cache_key]

    def get_collision_box(self) -> BlockCollisionBox:
        return BlockCollisionBox.from_box(0, 0, 1, 7 / 8)

    def _has_nearby_water(self) -> bool:
        loc = self.location
        world = loc.world
        for x in range(int(loc.x) - 4, int(loc.x) + 5):
            for y in (int(loc.y), int(loc.y) + 1):
                for z in (0, 1):
                    if world.get_block(x, y, z).block_id == "water":
                        return True
        return False

    def _is_rained_on(self) -> bool:
        loc = self.location
        world = loc.world
        weather = getattr(getattr(world, "weather", None), "value", None)
        if weather != "rain":
            return False
        if (
            get_precipitation_type(
                world.get_biome(int(loc.x), int(loc.y) + 1), int(loc.y) + 1
            )
            != "rain"
        ):
            return False
        max_height = int(world.attribute.MAX_BUILD_HEIGHT)
        return not any(
            world.get_block(int(loc.x), y, int(loc.z)).solid
            for y in range(int(loc.y) + 1, max_height)
        )

    def _set_moisture(self, moisture: int) -> None:
        moisture = max(0, min(self.MAX_MOISTURE, int(moisture)))
        if moisture == self.moisture:
            return
        self.moisture = moisture
        self.notify_state_changed()

    def on_update(self):
        if self.location is None:
            return
        above = self.location.world.get_block(self.location.add(0, 1, 0))
        if above.solid:
            self.location.world.set_block(DIRT(), self.location)

    def on_random_tick(self):
        if self.location is None:
            return
        world = self.location.world
        if self._has_nearby_water() or self._is_rained_on():
            self._set_moisture(self.MAX_MOISTURE)
            return
        if self.moisture > 0:
            self._set_moisture(self.moisture - 1)
            return
        above = world.get_block(self.location.add(0, 1, 0))
        if not getattr(above, "maintains_farmland", False):
            world.set_block(DIRT(), self.location)

    def on_fallen_on(self, entity, fall_distance: float) -> bool:
        super().on_fallen_on(entity, fall_distance)
        volume = float(getattr(entity, "width", 0.0)) ** 2 * float(
            getattr(entity, "height", 0.0)
        )
        if (
            self.location is not None
            and volume > 0.512
            and random.random() < max(0.0, float(fall_distance) - 0.5)
        ):
            self.location.world.set_block(DIRT(), self.location)
            return True
        return False


@register_block
class WHEAT(Crop):
    block_id = "wheat"
    _texture_path = "blocks.wheat"
    name = "tile.crops.name"
    max_age = 7

    def get_drops(self, material):
        from src.server.item_class import ItemStack

        if not self.is_mature:
            return [ItemStack(WHEAT_SEEDS_ITEM(), 1)]
        drops = [ItemStack(WHEAT_ITEM(), 1)]
        seed_count = random.randint(0, 3)
        if seed_count:
            drops.append(ItemStack(WHEAT_SEEDS_ITEM(), seed_count))
        return drops

    def get_explosion_drops(self):
        return self.get_drops(None)


class RootCrop(Crop):
    produce_material_type = None
    max_age = 3

    def get_drops(self, material):
        from src.server.item_class import ItemStack

        amount = 1
        if self.is_mature:
            amount += sum(random.random() < 4 / 7 for _ in range(3))
        return [ItemStack(self.produce_material_type(), amount)]

    def get_explosion_drops(self):
        return self.get_drops(None)


@register_block
class CARROTS(RootCrop):
    block_id = "carrots"
    _texture_path = "blocks.carrots"
    name = "tile.carrots.name"
    produce_material_type = CARROT_ITEM


@register_block
class POTATOES(RootCrop):
    block_id = "potatoes"
    _texture_path = "blocks.potatoes"
    name = "tile.potatoes.name"
    produce_material_type = POTATO_ITEM

    def get_drops(self, material):
        from src.server.item_class import ItemStack

        drops = super().get_drops(material)
        if self.is_mature and random.random() < 0.02:
            drops.append(ItemStack(POISONOUS_POTATO_ITEM(), 1))
        return drops


class SeedDroppingGrass:
    def get_drops(self, material):
        from src.server.item_class import ItemStack

        if random.randrange(8) == 0:
            return [ItemStack(WHEAT_SEEDS_ITEM(), 1)]
        return []

    def get_explosion_drops(self):
        return self.get_drops(None)


@register_block
class SHORT_GRASS(SeedDroppingGrass, GrassStain):
    block_id = "short_grass"
    name = "tile.tallgrass.grass.name"
    _texture_path = "blocks.tallgrass"
    hardness = 0.0
    replaceable = True


class DoublePlantBottomMixin:
    top_block_id = None

    @staticmethod
    def _remove_double_plant_neighbor(location):
        world = location.world
        try:
            world.set_block(AIR(), location, send_packet=True, block_update=False)
        except TypeError:
            world.set_block(AIR(), location)

    def on_update(self):
        Plant.on_update(self)

    def on_break(self):
        if self.location is None or self.top_block_id is None:
            return
        top = self.location.world.get_block(self.location.add(0, 1, 0))
        if getattr(top, "block_id", None) == self.top_block_id:
            self._remove_double_plant_neighbor(top.location)


class DoublePlantTopMixin:
    bottom_block_id = None

    def _remove_double_plant_neighbor(self, location):
        world = location.world
        try:
            world.set_block(AIR(), location, send_packet=True, block_update=False)
        except TypeError:
            world.set_block(AIR(), location)

    def on_update(self):
        if self.location is None or self.bottom_block_id is None:
            return
        bottom = self.location.world.get_block(self.location.add(0, -1, 0))
        if getattr(bottom, "block_id", None) != self.bottom_block_id:
            self.location.world.break_block(self.location)

    def on_break(self):
        if self.location is None or self.bottom_block_id is None:
            return
        bottom = self.location.world.get_block(self.location.add(0, -1, 0))
        if getattr(bottom, "block_id", None) == self.bottom_block_id:
            self._remove_double_plant_neighbor(bottom.location)


@register_block
class TALL_GRASS(DoublePlantBottomMixin, SeedDroppingGrass, GrassStain):
    block_id = "tall_grass"
    name = "tile.doublePlant.grass.name"
    _texture_path = "blocks.double_plant_grass_bottom"
    top_block_id = "tall_grass_top"


@register_block
class TALL_GRASS_TOP(DoublePlantTopMixin, SeedDroppingGrass, GrassStain):
    block_id = "tall_grass_top"
    name = "tile.doublePlant.grass.name"
    _texture_path = "blocks.double_plant_grass_top"
    bottom_block_id = "tall_grass"


@register_block
class LARGE_FERN(DoublePlantBottomMixin, SeedDroppingGrass, GrassStain):
    block_id = "large_fern"
    name = "tile.doublePlant.fern.name"
    _texture_path = "blocks.double_plant_fern_bottom"
    top_block_id = "large_fern_top"


@register_block
class LARGE_FERN_TOP(DoublePlantTopMixin, SeedDroppingGrass, GrassStain):
    block_id = "large_fern_top"
    name = "tile.doublePlant.fern.name"
    _texture_path = "blocks.double_plant_fern_top"
    bottom_block_id = "large_fern"


@register_block
class SUNFLOWER(DoublePlantBottomMixin, Plant):
    block_id = "sunflower"
    name = "tile.doublePlant.sunflower.name"
    _texture_path = "blocks.double_plant_sunflower_bottom"
    top_block_id = "sunflower_top"


@register_block
class SUNFLOWER_TOP(DoublePlantTopMixin, Plant):
    block_id = "sunflower_top"
    name = "tile.doublePlant.sunflower.name"
    _texture_path = "blocks.double_plant_sunflower_top"
    _front_texture_path = "blocks.double_plant_sunflower_front"
    bottom_block_id = "sunflower"
    _texture_cache = {}

    @client_method
    def get_texture(self, size, client=None):
        top = client.resources_manager.get_texture_img(self._texture_path)
        front = client.resources_manager.get_texture_img(self._front_texture_path)
        if top is None:
            return super().get_texture(size, client)

        cache_key = (size, id(top), id(front) if front is not None else 0)
        if cache_key in self._texture_cache:
            return self._texture_cache[cache_key]

        final = pygame.transform.scale(top, (size, size)).convert_alpha()
        if front is not None:
            front_scaled = pygame.transform.scale(front, (size, size)).convert_alpha()
            final.blit(front_scaled, (0, 0))

        cls = type(self)
        if cls.has_transparent_pixels is None:
            cls.has_transparent_pixels = (
                client.resources_manager.has_transparent_pixels(final)
            )
        self._texture_cache[cache_key] = final
        return final


@register_block
class ROSE_BUSH(DoublePlantBottomMixin, Plant):
    block_id = "rose_bush"
    name = "tile.doublePlant.rose.name"
    _texture_path = "blocks.double_plant_rose_bottom"
    top_block_id = "rose_bush_top"


@register_block
class ROSE_BUSH_TOP(DoublePlantTopMixin, Plant):
    block_id = "rose_bush_top"
    name = "tile.doublePlant.rose.name"
    _texture_path = "blocks.double_plant_rose_top"
    bottom_block_id = "rose_bush"


@register_block
class PEONY(DoublePlantBottomMixin, Plant):
    block_id = "peony"
    name = "tile.doublePlant.paeonia.name"
    _texture_path = "blocks.double_plant_paeonia_bottom"
    top_block_id = "peony_top"


@register_block
class PEONY_TOP(DoublePlantTopMixin, Plant):
    block_id = "peony_top"
    name = "tile.doublePlant.paeonia.name"
    _texture_path = "blocks.double_plant_paeonia_top"
    bottom_block_id = "peony"


@register_block
class LILAC(DoublePlantBottomMixin, Plant):
    block_id = "lilac"
    name = "tile.doublePlant.syringa.name"
    _texture_path = "blocks.double_plant_syringa_bottom"
    top_block_id = "lilac_top"


@register_block
class LILAC_TOP(DoublePlantTopMixin, Plant):
    block_id = "lilac_top"
    name = "tile.doublePlant.syringa.name"
    _texture_path = "blocks.double_plant_syringa_top"
    bottom_block_id = "lilac"


@register_block
class OAK_PLANK(Block):
    block_id = "oak_planks"
    name = "tile.wood.oak.name"
    _texture_path = "blocks.planks_oak"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


@register_block
class BIRCH_PLANK(Block):
    block_id = "birch_planks"
    name = "tile.wood.birch.name"
    _texture_path = "blocks.planks_birch"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


@register_block
class SPRUCE_PLANK(Block):
    block_id = "spruce_planks"
    name = "tile.wood.spruce.name"
    _texture_path = "blocks.planks_spruce"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


@register_block
class JUNGLE_PLANK(Block):
    block_id = "jungle_planks"
    name = "tile.wood.jungle.name"
    _texture_path = "blocks.planks_jungle"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


@register_block
class ACACIA_PLANK(Block):
    block_id = "acacia_planks"
    name = "tile.wood.acacia.name"
    _texture_path = "blocks.planks_acacia"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


@register_block
class DARK_OAK_PLANK(Block):
    block_id = "dark_oak_planks"
    name = "tile.wood.big_oak.name"
    _texture_path = "blocks.planks_big_oak"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class WoodenFence(FENCES):
    break_sound = "dig.wood"
    hardness = 2.0
    blast_resistance = 3.0
    preferred_tool = "axe"


@register_block
class OAK_FENCE(WoodenFence):
    block_id = "oak_fence"
    name = "tile.fence.name"
    _texture_path = "blocks.planks_oak"


@register_block
class SPRUCE_FENCE(WoodenFence):
    block_id = "spruce_fence"
    name = "tile.spruceFence.name"
    _texture_path = "blocks.planks_spruce"


@register_block
class BIRCH_FENCE(WoodenFence):
    block_id = "birch_fence"
    name = "tile.birchFence.name"
    _texture_path = "blocks.planks_birch"


@register_block
class JUNGLE_FENCE(WoodenFence):
    block_id = "jungle_fence"
    name = "tile.jungleFence.name"
    _texture_path = "blocks.planks_jungle"


@register_block
class ACACIA_FENCE(WoodenFence):
    block_id = "acacia_fence"
    name = "tile.acaciaFence.name"
    _texture_path = "blocks.planks_acacia"


@register_block
class DARK_OAK_FENCE(WoodenFence):
    block_id = "dark_oak_fence"
    name = "tile.darkOakFence.name"
    _texture_path = "blocks.planks_big_oak"


@register_block
class COBBLESTONE_WALL(WALLS):
    block_id = "cobblestone_wall"
    name = "tile.cobbleWall.normal.name"
    _texture_path = "blocks.cobblestone"
    break_sound = "dig.stone"
    hardness = 2.0
    blast_resistance = 6.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True


class PairedBlock(Block):
    """Shared lifecycle for blocks represented by two world cells."""

    def get_counterpart_location(self):
        raise NotImplementedError

    def make_counterpart(self):
        raise NotImplementedError

    def get_counterpart(self):
        if self.location is None:
            return None
        location = self.get_counterpart_location()
        counterpart = self.location.world.get_block(location)
        return counterpart if self.is_matching_counterpart(counterpart) else None

    def is_matching_counterpart(self, counterpart) -> bool:
        return type(counterpart) is type(self)

    @staticmethod
    def _set_block(world, block, location, *, block_update=False):
        try:
            world.set_block(
                block,
                location,
                send_packet=True,
                block_update=block_update,
            )
        except TypeError:
            # ClientWorld has a smaller signature. This path is used by local
            # break prediction, while authoritative placement stays server-side.
            world.set_block(block, location)

    def _remove_counterpart(self) -> None:
        counterpart = self.get_counterpart()
        if counterpart is not None:
            self._set_block(
                self.location.world,
                AIR(),
                counterpart.location,
                block_update=False,
            )

    @staticmethod
    def _has_full_top_support(world, location) -> bool:
        support = world.get_block(location.add(0, -1, 0))
        shape = support.get_collision_box()
        return any(
            box.min_x <= 0 and box.max_x >= 1 and box.max_y >= 1
            for box in shape
        )

    def on_break(self):
        self._remove_counterpart()

    def place_at(self, location: Location) -> bool:
        world = location.world
        counterpart_location = self.get_counterpart_location_for(location)
        if (
            not world.get_block(location).replaceable
            or not world.get_block(counterpart_location).replaceable
            or not getattr(world, "is_chunk_loaded", lambda _rx: True)(
                int(counterpart_location.x) // 16
            )
        ):
            return False

        counterpart = self.make_counterpart()
        self._set_block(
            world,
            counterpart,
            counterpart_location,
            block_update=False,
        )
        self._set_block(world, self, location, block_update=True)
        if world.get_block(location) is self and world.get_block(
            counterpart_location
        ) is counterpart:
            return True

        if world.get_block(counterpart_location) is counterpart:
            self._set_block(world, AIR(), counterpart_location, block_update=False)
        return False

    def _discard_orphan(self) -> None:
        if self.location is not None:
            self._set_block(
                self.location.world,
                AIR(),
                self.location,
                block_update=False,
            )


class DoorBlock(PairedBlock):
    """Two-cell wooden door adapted from Minecraft's DoorBlock state model."""

    solid = False
    collision_box = FULL_BLOCK
    suffocating = False
    redstone_conducting = False
    light_attenuation = 1
    has_transparent_pixels = True
    break_sound = "dig.wood"
    hardness = 3.0
    blast_resistance = 3.0
    preferred_tool = "axe"
    texture_stem = "wood"
    _state_texture_cache = {}

    def __init__(self, nbt=None):
        self.half = "lower"
        self.open = False
        self.hinge = "left"
        self.facing = 1
        super().__init__(nbt)

    def write_nbt(self, nbt):
        super().write_nbt(nbt)
        self.half = self.half if self.half in ("lower", "upper") else "lower"
        self.hinge = self.hinge if self.hinge in ("left", "right") else "left"
        self.facing = 1 if self.facing >= 0 else -1
        self.open = bool(self.open)

    def get_counterpart_location_for(self, location):
        return location.add(0, 1 if self.half == "lower" else -1, 0)

    def get_counterpart_location(self):
        return self.get_counterpart_location_for(self.location)

    def is_matching_counterpart(self, counterpart) -> bool:
        return (
            type(counterpart) is type(self)
            and counterpart.half != self.half
            and counterpart.facing == self.facing
            and counterpart.hinge == self.hinge
        )

    def make_counterpart(self):
        counterpart = type(self)()
        counterpart.half = "upper" if self.half == "lower" else "lower"
        counterpart.open = self.open
        counterpart.hinge = self.hinge
        counterpart.facing = self.facing
        return counterpart

    @staticmethod
    def _has_support(world, location) -> bool:
        return PairedBlock._has_full_top_support(world, location)

    @staticmethod
    def _is_full_collision_block(block) -> bool:
        """Match Java's sturdy full-block check for hinge weighting."""
        return any(
            box.min_x <= 0
            and box.min_y <= 0
            and box.max_x >= 1
            and box.max_y >= 1
            for box in block.get_collision_box()
        )

    @staticmethod
    def _pointed_hinge(location, context, player) -> str:
        """Use the half of the placement cell the player's ray points at."""
        try:
            pointed_x = float(context.ray_origin[0]) + float(
                context.ray_direction[0]
            )
        except (AttributeError, IndexError, TypeError, ValueError):
            pointed_x = float(getattr(player, "x", location.x)) + float(
                getattr(player, "width", 0.6)
            ) * 0.5
        return "left" if pointed_x < float(location.x) + 0.5 else "right"

    def _get_hinge_for_placement(self, location, context, player) -> str:
        """Apply Java's adjacent-door/full-block rules before the click tie-break."""
        world = location.world
        left_lower = world.get_block(location.add(-1, 0, 0))
        right_lower = world.get_block(location.add(1, 0, 0))
        left_is_door = isinstance(left_lower, DoorBlock) and getattr(
            left_lower, "half", None
        ) == "lower"
        right_is_door = isinstance(right_lower, DoorBlock) and getattr(
            right_lower, "half", None
        ) == "lower"

        # A new half of a double door uses the opposite hinge. This takes
        # precedence over solid neighbours, as it does in Java DoorBlock.
        if left_is_door and not right_is_door:
            return "right"
        if right_is_door and not left_is_door:
            return "left"

        left_full = sum(
            self._is_full_collision_block(
                world.get_block(location.add(-1, vertical_offset, 0))
            )
            for vertical_offset in (0, 1)
        )
        right_full = sum(
            self._is_full_collision_block(
                world.get_block(location.add(1, vertical_offset, 0))
            )
            for vertical_offset in (0, 1)
        )
        if left_full > right_full:
            return "left"
        if right_full > left_full:
            return "right"
        return self._pointed_hinge(location, context, player)

    def get_state_for_placement(
        self,
        location,
        *,
        placement_face=None,
        player=None,
        context=None,
    ):
        world = location.world
        upper_location = location.add(0, 1, 0)
        if (
            location.y + 1 >= world.attribute.MAX_BUILD_HEIGHT
            or not world.get_block(upper_location).replaceable
            or not world.is_chunk_loaded(int(upper_location.x) // 16)
        ):
            return None
        if not world.structure_build_mode and not self._has_support(world, location):
            return None

        self.half = "lower"
        self.facing = 1 if int(getattr(player, "facing", 1)) == 1 else -1
        self.hinge = self._get_hinge_for_placement(location, context, player)

        if player is not None:
            upper = self.make_counterpart()
            intersects = getattr(player, "_block_item_intersects_entity", None)
            if callable(intersects) and intersects(upper, upper_location):
                return None
        return self

    def get_collision_box(self):
        if self.open:
            return EMPTY
        if self.hinge == "left":
            return BlockCollisionBox.from_box(0, 0, 2 / 16, 1)
        return BlockCollisionBox.from_box(14 / 16, 0, 1, 1)

    def get_texture_path(self):
        return f"blocks.door_{self.texture_stem}_{self.half}"

    @client_method
    def get_texture(self, size, client=None):
        size = max(1, int(round(size)))
        texture = client.resources_manager.get_texture_img(
            self.get_texture_path(), flip=self.facing < 0
        )
        cache_key = (
            type(self),
            texture,
            size,
            self.half,
            self.open,
            self.hinge,
            self.facing,
        )
        cached = self._state_texture_cache.get(cache_key)
        if cached is not None:
            return cached

        if self.open:
            rendered = pygame.transform.scale(texture, (size, size))
        else:
            # A closed 2-D door is the edge-on projection of the 3-D slab.
            # Preserve both authored edge columns instead of squeezing all 16
            # columns into a blurry strip. Keeping their original left/right
            # order also leaves the hinge-side column on the outer edge.
            source_width, source_height = texture.get_size()
            native_edge = pygame.Surface((2, source_height), pygame.SRCALPHA)
            native_edge.blit(texture.subsurface((0, 0, 1, source_height)), (0, 0))
            native_edge.blit(
                texture.subsurface((source_width - 1, 0, 1, source_height)),
                (1, 0),
            )
            thickness = max(1, int(round(size * 2 / 16)))
            edge = pygame.transform.scale(native_edge, (thickness, size))
            rendered = pygame.Surface((size, size), pygame.SRCALPHA)
            x = 0 if self.hinge == "left" else size - thickness
            rendered.blit(edge, (x, 0))
        self._state_texture_cache[cache_key] = rendered
        if len(self._state_texture_cache) > 96:
            self._state_texture_cache.pop(next(iter(self._state_texture_cache)))
        return rendered

    def on_right_click(self, player) -> bool:
        counterpart = self.get_counterpart()
        if counterpart is None:
            return False
        opened = not self.open
        self.open = opened
        counterpart.open = opened
        self.notify_state_changed()
        counterpart.notify_state_changed()
        server = self.get_server()
        if server is not None:
            server.broadcast_sound(
                "random.door_open" if opened else "random.door_close",
                self.location.x + 0.5,
                self.location.y + 0.5,
                self.location.z,
            )
        return True

    def on_update(self):
        if self.get_counterpart() is None:
            self._discard_orphan()
            return
        lower_location = (
            self.location if self.half == "lower" else self.location.add(0, -1, 0)
        )
        if not self.location.world.structure_build_mode and not self._has_support(
            self.location.world, lower_location
        ):
            self.location.world.break_block(self.location)


@register_block
class OAK_DOOR(DoorBlock):
    block_id = "oak_door"
    name = "item.doorOak.name"
    texture_stem = "wood"


@register_block
class SPRUCE_DOOR(DoorBlock):
    block_id = "spruce_door"
    name = "item.doorSpruce.name"
    texture_stem = "spruce"


@register_block
class BIRCH_DOOR(DoorBlock):
    block_id = "birch_door"
    name = "item.doorBirch.name"
    texture_stem = "birch"


@register_block
class JUNGLE_DOOR(DoorBlock):
    block_id = "jungle_door"
    name = "item.doorJungle.name"
    texture_stem = "jungle"


@register_block
class ACACIA_DOOR(DoorBlock):
    block_id = "acacia_door"
    name = "item.doorAcacia.name"
    texture_stem = "acacia"


@register_block
class DARK_OAK_DOOR(DoorBlock):
    block_id = "dark_oak_door"
    name = "item.doorDarkOak.name"
    texture_stem = "dark_oak"


@register_block
class BED(PairedBlock):
    """Horizontal two-cell bed with server-authoritative sleep and respawn."""

    block_id = "bed"
    name = "tile.bed.name"
    solid = False
    collision_box = BlockCollisionBox.from_box(0, 0, 1, 9 / 16)
    suffocating = False
    redstone_conducting = False
    light_attenuation = 1
    has_transparent_pixels = True
    break_sound = "dig.wood"
    hardness = 0.2
    blast_resistance = 0.2
    bounce_restitution = 0.66
    _state_texture_cache = {}

    def __init__(self, nbt=None):
        self.part = "foot"
        self.facing = 1
        super().__init__(nbt)

    def write_nbt(self, nbt):
        super().write_nbt(nbt)
        self.part = self.part if self.part in ("foot", "head") else "foot"
        self.facing = 1 if self.facing >= 0 else -1

    def get_counterpart_location_for(self, location):
        direction = self.facing if self.part == "foot" else -self.facing
        return location.add(direction, 0, 0)

    def get_counterpart_location(self):
        return self.get_counterpart_location_for(self.location)

    def is_matching_counterpart(self, counterpart) -> bool:
        return (
            type(counterpart) is type(self)
            and counterpart.part != self.part
            and counterpart.facing == self.facing
        )

    def make_counterpart(self):
        counterpart = type(self)()
        counterpart.part = "head" if self.part == "foot" else "foot"
        counterpart.facing = self.facing
        return counterpart

    @staticmethod
    def _has_support(world, location) -> bool:
        return PairedBlock._has_full_top_support(world, location)

    def get_state_for_placement(
        self,
        location,
        *,
        placement_face=None,
        player=None,
        context=None,
    ):
        world = location.world
        self.part = "foot"
        self.facing = 1 if int(getattr(player, "facing", 1)) == 1 else -1
        head_location = location.add(self.facing, 0, 0)
        if (
            not world.get_block(head_location).replaceable
            or not world.is_chunk_loaded(int(head_location.x) // 16)
        ):
            return None
        if not world.structure_build_mode and not (
            self._has_support(world, location)
            and self._has_support(world, head_location)
        ):
            return None
        if player is not None:
            head = self.make_counterpart()
            intersects = getattr(player, "_block_item_intersects_entity", None)
            if callable(intersects) and intersects(head, head_location):
                return None
        return self

    def get_texture_path(self):
        return f"blocks.bed_{'head' if self.part == 'head' else 'feet'}_side"

    @client_method
    def get_texture(self, size, client=None):
        size = max(1, int(round(size)))
        # The legacy side textures face toward positive x by default: foot leg
        # and head pillow belong on the two outer ends of the assembled bed.
        flip = self.facing < 0
        texture = client.resources_manager.get_texture_img(
            self.get_texture_path(), flip=flip
        )
        cache_key = (texture, size, self.part, self.facing)
        cached = self._state_texture_cache.get(cache_key)
        if cached is not None:
            return cached
        rendered = pygame.transform.scale(texture, (size, size))
        self._state_texture_cache[cache_key] = rendered
        if len(self._state_texture_cache) > 32:
            self._state_texture_cache.pop(next(iter(self._state_texture_cache)))
        return rendered

    def on_update(self):
        counterpart = self.get_counterpart()
        if counterpart is None:
            self._discard_orphan()
            return
        world = self.location.world
        if not world.structure_build_mode and not (
            self._has_support(world, self.location)
            and self._has_support(world, counterpart.location)
        ):
            world.break_block(self.location)

    def on_break(self):
        head = self._head()
        if head is not None and head.location is not None:
            server = getattr(head.location.world, "server", None)
            if server is not None:
                head_key = {
                    "world": str(head.location.world.id_name),
                    "x": int(head.location.x),
                    "y": int(head.location.y),
                    "z": int(head.location.z),
                }
                for sleeper in tuple(server.players):
                    if getattr(sleeper, "sleeping_bed", None) == head_key:
                        sleeper.stop_sleeping(reposition=False)
        super().on_break()

    def _head(self):
        if self.part == "head":
            return self
        counterpart = self.get_counterpart()
        return counterpart if counterpart is not None else None

    def _nearby_monster(self) -> bool:
        if self.location is None:
            return False
        for entity in tuple(getattr(self.location.world, "entities", {}).values()):
            if getattr(entity, "removed", False) or getattr(entity, "health", 1) <= 0:
                continue
            if getattr(entity, "entity_id", None) != "zombie":
                continue
            if int(getattr(entity, "z", 0)) != int(self.location.z):
                continue
            if (
                abs(float(entity.x) - float(self.location.x)) <= 8
                and abs(float(entity.y) - float(self.location.y)) <= 5
            ):
                return True
        return False

    def on_right_click(self, player) -> bool:
        head = self._head()
        if head is None or head.location is None:
            return False
        world = head.location.world
        server = getattr(world, "server", None)
        foot = head.get_counterpart()
        if foot is None or any(
            not world.get_block(location.add(0, 1, 0)).replaceable
            for location in (foot.location, head.location)
        ):
            if server is not None:
                server.send_chat_to_player(
                    player, "This bed is obstructed."
                )
            return True

        player.spawn_point = {
            "world": str(world.id_name),
            "x": int(head.location.x),
            "y": int(head.location.y),
            "z": int(head.location.z),
        }
        if server is not None:
            server.send_chat_to_player(player, "Respawn point set.", (85, 255, 85))

        time_of_day = int(world.world_time) % 24000
        if not 12542 <= time_of_day <= 23459:
            if server is not None:
                server.send_chat_to_player(player, "You can only sleep at night.")
            return True

        if (
            getattr(getattr(player, "gamemode", None), "name_id", "survival")
            != "creative"
            and self._nearby_monster()
        ):
            if server is not None:
                server.send_chat_to_player(
                    player, "You may not rest now; there are monsters nearby."
                )
            return True

        bed_key = {
            "world": str(world.id_name),
            "x": int(head.location.x),
            "y": int(head.location.y),
            "z": int(head.location.z),
        }
        if server is not None and any(
            other is not player
            and getattr(other, "sleeping", False)
            and getattr(other, "sleeping_bed", None) == bed_key
            for other in tuple(server.players)
        ):
            server.send_chat_to_player(player, "This bed is occupied.")
            return True

        start_sleeping = getattr(player, "start_sleeping", None)
        if callable(start_sleeping) and start_sleeping(head) and server is not None:
            sleeping = sum(
                1
                for other in tuple(server.players)
                if other.world is world
                and other.health > 0
                and getattr(other, "sleeping", False)
            )
            eligible = sum(
                1
                for other in tuple(server.players)
                if other.world is world and other.health > 0
            )
            server.send_chat_to_player(
                player, f"Sleeping ({sleeping}/{eligible} players).", (85, 255, 85)
            )
        return True

    def get_respawn_position(self, player):
        head = self._head()
        if head is None or head.location is None:
            return None
        world = head.location.world
        foot = head.get_counterpart()
        if foot is None:
            return None
        bed_locations = (foot.location, head.location)

        for location in (
            foot.location.add(-head.facing, 0, 0),
            head.location.add(head.facing, 0, 0),
        ):
            if (
                world.get_block(location).replaceable
                and world.get_block(location.add(0, 1, 0)).replaceable
                and self._has_support(world, location)
            ):
                return float(location.x) + 0.2, float(location.y), int(location.z)

        for location in bed_locations:
            if (
                world.get_block(location.add(0, 1, 0)).replaceable
                and world.get_block(location.add(0, 2, 0)).replaceable
            ):
                return (
                    float(location.x) + 0.2,
                    float(location.y) + 9 / 16,
                    int(location.z),
                )
        return None


@register_block
class CRAFTING_TABLE(Block):
    block_id = "crafting_table"
    name = "tile.workbench.name"
    _texture_path = "blocks.crafting_table_front"
    break_sound = "dig.wood"
    hardness = 2.5
    preferred_tool = "axe"

    def on_right_click(self, player) -> bool:
        server = getattr(getattr(self.location, "world", None), "server", None)
        if server is None:
            return False
        player.sync_inventory()
        server.send_client_socket(
            player,
            {"__class__": "CraftingTableOpen", "width": 3, "height": 3},
            "Forward",
        )
        return True


class FurnaceInventory(Inventory):
    def __init__(self, furnace):
        super().__init__(3)
        self.furnace = furnace
        self.owner_block = furnace

    def can_place(self, slot, stack) -> bool:
        from src.server.smelting import find_smelting_recipe, is_fuel

        slot = int(slot)
        if stack is None or stack.is_empty():
            return True
        if slot == 0:
            recipe = find_smelting_recipe(stack)
            return recipe is not None and recipe.create_result() is not None
        if slot == 1:
            return is_fuel(stack)
        return False

    def on_changed(self) -> None:
        self.furnace.on_inventory_changed()

    def on_take(self, slot: int, amount: int, player=None) -> None:
        if int(slot) == 2 and amount > 0:
            self.furnace.on_output_taken(int(amount), player)


@register_block
class FURNACE(Block):
    block_id = "furnace"
    name = "tile.furnace.name"
    _texture_path = "blocks.furnace_front_off"
    break_sound = "dig.stone"
    hardness = 3.5
    blast_resistance = 3.5
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    lit = False
    _state_texture_cache = {}

    def __init__(self, nbt=None):
        self.inventory = FurnaceInventory(self)
        self.burn_time = 0
        self.burn_time_total = 0
        self.cook_time = 0
        self.cook_time_total = 200
        self.stored_experience = 0.0
        self.stored_output_items = 0
        self._viewers = set()
        super().__init__()
        if nbt:
            self.write_nbt(nbt)

    @property
    def container_id(self) -> str:
        if self.location is None:
            return "furnace:unplaced"
        return "furnace:{},{},{}".format(
            int(self.location.x),
            int(self.location.y),
            int(self.location.z),
        )

    def parse_nbt(self) -> dict:
        from src.server.inventory import serialize_inventory

        return {
            "items": serialize_inventory(self.inventory),
            "burn_time": max(0, int(self.burn_time)),
            "burn_time_total": max(0, int(self.burn_time_total)),
            "cook_time": max(0, int(self.cook_time)),
            "cook_time_total": max(1, int(self.cook_time_total)),
            "stored_experience": max(0.0, float(self.stored_experience)),
            "stored_output_items": max(0, int(self.stored_output_items)),
            "lit": bool(self.lit),
        }

    def write_nbt(self, nbt):
        import ast
        from src.server.inventory import restore_inventory

        if isinstance(nbt, str):
            nbt = ast.literal_eval(nbt)
        if not isinstance(nbt, dict):
            return
        restore_inventory(self.inventory, nbt.get("items", []))
        for key in (
            "burn_time",
            "burn_time_total",
            "cook_time",
            "cook_time_total",
            "stored_output_items",
        ):
            try:
                value = int(nbt.get(key, getattr(self, key)))
            except (TypeError, ValueError):
                continue
            setattr(
                self, key, max(1, value) if key == "cook_time_total" else max(0, value)
            )
        try:
            self.stored_experience = max(
                0.0,
                float(nbt.get("stored_experience", self.stored_experience)),
            )
        except (TypeError, ValueError):
            pass
        self.lit = bool(nbt.get("lit", self.burn_time > 0))

    def get_texture_path(self) -> str:
        return "blocks.furnace_front_on" if self.lit else "blocks.furnace_front_off"

    @client_method
    def get_texture(self, size, client):
        size = max(1, int(round(size)))
        path = self.get_texture_path()
        original = client.resources_manager.get_texture_img(path)
        if original is None:
            return None
        key = (path, size, original)
        texture = self._state_texture_cache.get(key)
        if texture is None:
            texture = pygame.transform.scale(original, (size, size))
            self._state_texture_cache[key] = texture
            if len(self._state_texture_cache) > 16:
                self._state_texture_cache.pop(next(iter(self._state_texture_cache)))
        if self.has_transparent_pixels is None:
            self.has_transparent_pixels = (
                client.resources_manager.has_transparent_pixels(original)
            )
        return texture

    def get_light_state(self) -> tuple[bool, int, int]:
        return bool(self.solid), int(self.light_attenuation), 13 if self.lit else 0

    def on_load(self) -> None:
        if self.location is not None:
            register = getattr(self.location.world, "register_ticking_block", None)
            if callable(register):
                register(self)

    def on_unload(self) -> None:
        if self.location is not None:
            unregister = getattr(self.location.world, "unregister_ticking_block", None)
            if callable(unregister):
                unregister(self)
        self.close_all_viewers()

    def _state_packet(self, packet_class="FurnaceUpdate") -> dict:
        from src.server.inventory import serialize_inventory

        packet = {
            "__class__": packet_class,
            "container": self.container_id,
            "slots": serialize_inventory(self.inventory),
            "burn_time": max(0, int(self.burn_time)),
            "burn_time_total": max(0, int(self.burn_time_total)),
            "cook_time": max(0, int(self.cook_time)),
            "cook_time_total": max(1, int(self.cook_time_total)),
            "lit": bool(self.lit),
        }
        if self.location is not None:
            packet["x"] = int(self.location.x)
            packet["y"] = int(self.location.y)
            packet["z"] = int(self.location.z)
        return packet

    def sync_viewers(self, packet_class="FurnaceUpdate") -> None:
        if self.location is None:
            return
        server = getattr(self.location.world, "server", None)
        if server is None:
            return
        packet = self._state_packet(packet_class)
        for player in tuple(self._viewers):
            if player.get_inventory_container(self.container_id) is not self.inventory:
                self._viewers.discard(player)
                continue
            server.send_client_socket(player, packet, "Forward")

    def open_for(self, player) -> None:
        for container_id, container in tuple(player.open_inventory_containers.items()):
            owner = getattr(
                container,
                "owner_block",
                getattr(container, "furnace", None),
            )
            if owner is not None and owner is not self:
                owner.close_for(player)
        player.register_inventory_container(self.container_id, self.inventory)
        self._viewers.add(player)
        server = getattr(self.location.world, "server", None)
        if server is not None:
            server.send_client_socket(
                player,
                self._state_packet("FurnaceOpen"),
                "Forward",
            )

    def close_for(self, player) -> None:
        if player.open_inventory_containers.get(self.container_id) is self.inventory:
            player.unregister_inventory_container(self.container_id)
        self._viewers.discard(player)

    def close_all_viewers(self) -> None:
        for player in tuple(self._viewers):
            self.close_for(player)
            server = getattr(getattr(self.location, "world", None), "server", None)
            if server is not None:
                server.send_client_socket(
                    player,
                    {"__class__": "FurnaceClosed", "container": self.container_id},
                    "Forward",
                )

    def on_right_click(self, player) -> bool:
        self.open_for(player)
        return True

    def _mark_contents_dirty(self) -> None:
        if self.location is None:
            return
        world = self.location.world
        world.mark_chunk_dirty(int(self.location.x) // 16)
        world.invalidate_chunk_packet(int(self.location.x) // 16)

    def on_inventory_changed(self) -> None:
        self._mark_contents_dirty()
        self.sync_viewers()

    def _set_lit(self, lit: bool) -> None:
        lit = bool(lit)
        if self.lit == lit:
            return
        self.lit = lit
        if self.location is not None:
            world = self.location.world
            world.schedule_light_recalculation(int(self.location.x) // 16)
        self.notify_state_changed()

    def _can_smelt(self, recipe) -> bool:
        if recipe is None:
            return False
        result = recipe.create_result()
        if result is None:
            return False
        output = self.inventory[2]
        if output.is_empty():
            return True
        return (
            output.is_stackable_with(result, require_full_fit=False)
            and output.amount + result.amount <= output.max_stack_size
        )

    def _consume_fuel(self) -> int:
        from src.server.item_class import EmptyItemStack, ItemStack
        from src.server.materials import get_material_by_id
        from src.server.smelting import get_fuel_burn_time

        fuel = self.inventory[1]
        burn_time = get_fuel_burn_time(fuel)
        if burn_time <= 0:
            return 0
        fuel_id = fuel.material.name_id
        fuel.reduce_amount(1)
        if fuel.is_empty():
            if fuel_id == "lava_bucket":
                self.inventory[1] = ItemStack(get_material_by_id("bucket"), 1)
            else:
                self.inventory[1] = EmptyItemStack()
        self.burn_time = burn_time
        self.burn_time_total = burn_time
        return burn_time

    def _finish_smelt(self, recipe) -> None:
        from src.server.item_class import EmptyItemStack

        result = recipe.create_result()
        if result is None:
            return
        source = self.inventory[0]
        output = self.inventory[2]
        source.reduce_amount(1)
        if source.is_empty():
            self.inventory[0] = EmptyItemStack()
        if output.is_empty():
            self.inventory[2] = result
        else:
            output.amount += result.amount
        self.stored_experience += float(recipe.experience) * result.amount
        self.stored_output_items += result.amount

    def tick_server(self) -> None:
        from src.server.smelting import find_smelting_recipe

        old_state = (
            self.burn_time,
            self.burn_time_total,
            self.cook_time,
            self.cook_time_total,
            self.lit,
        )
        if self.burn_time > 0:
            self.burn_time -= 1

        recipe = find_smelting_recipe(self.inventory[0])
        can_smelt = self._can_smelt(recipe)
        if recipe is not None:
            self.cook_time_total = recipe.cooking_time

        if self.burn_time <= 0 and can_smelt:
            self._consume_fuel()

        if self.burn_time > 0 and can_smelt:
            self.cook_time += 1
            if self.cook_time >= self.cook_time_total:
                self.cook_time = 0
                self._finish_smelt(recipe)
        else:
            self.cook_time = max(0, self.cook_time - 2)

        self._set_lit(self.burn_time > 0)
        new_state = (
            self.burn_time,
            self.burn_time_total,
            self.cook_time,
            self.cook_time_total,
            self.lit,
        )
        if old_state != new_state:
            self._mark_contents_dirty()
            self.sync_viewers()

    @staticmethod
    def _rounded_experience(value: float) -> int:
        base = int(value)
        return base + (1 if random.random() < value - base else 0)

    def on_output_taken(self, amount: int, player=None) -> None:
        amount = min(max(0, int(amount)), self.stored_output_items)
        if amount <= 0 or self.stored_output_items <= 0:
            return
        share = self.stored_experience * amount / self.stored_output_items
        self.stored_experience = max(0.0, self.stored_experience - share)
        self.stored_output_items -= amount
        experience = self._rounded_experience(share)
        if experience > 0 and player is not None:
            player.add_experience(experience)
        self._mark_contents_dirty()

    def on_break(self):
        if self.location is None:
            return
        from src.server.entities.item import Item
        from src.server.item_class import EmptyItemStack

        world = self.location.world
        for index in range(len(self.inventory)):
            stack = self.inventory[index]
            if stack.is_empty():
                continue
            world.spawn_entity(
                Item(
                    self.location.x + 0.5,
                    self.location.y + 0.45,
                    world,
                    stack,
                    int(self.location.z),
                )
            )
            self.inventory[index] = EmptyItemStack()
        experience = self._rounded_experience(self.stored_experience)
        if experience > 0:
            world.spawn_experience(
                self.location.x + 0.5,
                self.location.y + 0.5,
                int(self.location.z),
                experience,
            )
        self.stored_experience = 0.0
        self.stored_output_items = 0
        self.close_all_viewers()


@register_block
class GLOWSTONE(Block):
    block_id = "glowstone"
    name = "tile.lightgem.name"
    _texture_path = "blocks.glowstone"
    light_source = 15
    light_attenuation = 0
    break_sound = "dig.glass"
    hardness = 0.3
    preferred_tool = "pickaxe"


@register_block
class GLASS(Block):
    block_id = "glass"
    name = "tile.glass.name"
    _texture_path = "blocks.glass"
    break_sound = "dig.glass"
    hardness = 0.3
    light_attenuation = 1
    suffocating = False
    redstone_conducting = False
    drops = ()


@register_block
class POPPY(Plant):
    block_id = "poppy"
    name = "tile.flower2.poppy.name"
    _texture_path = "blocks.flower_rose"


@register_block
class DANDELION(Plant):
    block_id = "dandelion"
    name = "tile.flower1.dandelion.name"
    _texture_path = "blocks.flower_dandelion"


@register_block
class OAK_LEAVES(Leaves):
    block_id = "oak_leaves"
    name = "tile.leaves.oak.name"
    _texture_path = "blocks.leaves_oak"


@register_block
class OAK_LOG(Log):
    block_id = "oak_log"
    name = "tile.log.oak.name"
    _texture_path = "blocks.log_oak"


@register_block
class BIRCH_LEAVES(Leaves):
    block_id = "birch_leaves"
    name = "tile.leaves.birch.name"
    _texture_path = "blocks.leaves_birch"


@register_block
class BIRCH_LOG(Log):
    block_id = "birch_log"
    name = "tile.log.birch.name"
    _texture_path = "blocks.log_birch"


@register_block
class SPRUCE_LEAVES(Leaves):
    block_id = "spruce_leaves"
    name = "tile.leaves.spruce.name"
    _texture_path = "blocks.leaves_spruce"


@register_block
class SPRUCE_LOG(Log):
    block_id = "spruce_log"
    name = "tile.log.spruce.name"
    _texture_path = "blocks.log_spruce"


@register_block
class JUNGLE_LEAVES(Leaves):
    block_id = "jungle_leaves"
    name = "tile.leaves.jungle.name"
    _texture_path = "blocks.leaves_jungle"


@register_block
class JUNGLE_LOG(Log):
    block_id = "jungle_log"
    name = "tile.log.jungle.name"
    _texture_path = "blocks.log_jungle"


@register_block
class ACACIA_LEAVES(Leaves):
    block_id = "acacia_leaves"
    name = "tile.leaves.acacia.name"
    _texture_path = "blocks.leaves_acacia"


@register_block
class ACACIA_LOG(Log):
    block_id = "acacia_log"
    name = "tile.log.acacia.name"
    _texture_path = "blocks.log_acacia"


@register_block
class DARK_OAK_LEAVES(Leaves):
    block_id = "dark_oak_leaves"
    name = "tile.leaves.big_oak.name"
    _texture_path = "blocks.leaves_big_oak"


@register_block
class DARK_OAK_LOG(Log):
    block_id = "dark_oak_log"
    name = "tile.log.big_oak.name"
    _texture_path = "blocks.log_big_oak"


@register_block
class SAND(GravityBlock):
    block_id = "sand"
    name = "tile.sand.name"
    _texture_path = "blocks.sand"
    break_sound = "dig.sand"
    hardness = 0.5
    preferred_tool = "shovel"


@register_block
class RED_SAND(GravityBlock):
    block_id = "red_sand"
    name = "tile.sand.red.name"
    _texture_path = "blocks.red_sand"
    break_sound = "dig.sand"
    hardness = 0.5
    preferred_tool = "shovel"


@register_block
class SANDSTONE(Block):
    block_id = "sandstone"
    name = "tile.sandStone.name"
    _texture_path = "blocks.sandstone_normal"
    hardness = 0.8
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class RED_SANDSTONE(Block):
    block_id = "red_sandstone"
    name = "tile.redSandStone.name"
    _texture_path = "blocks.red_sandstone_normal"
    hardness = 0.8
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class GRAVEL(GravityBlock):
    block_id = "gravel"
    name = "tile.gravel.name"
    _texture_path = "blocks.gravel"
    break_sound = "dig.gravel"
    hardness = 0.6
    preferred_tool = "shovel"


@register_block
class CLAY(Block):
    block_id = "clay"
    name = "tile.clay.name"
    _texture_path = "blocks.clay"
    break_sound = "dig.gravel"
    hardness = 0.6
    preferred_tool = "shovel"


@register_block
class HARDENED_CLAY(Block):
    block_id = "hardened_clay"
    name = "tile.clayHardened.name"
    _texture_path = "blocks.hardened_clay"
    hardness = 1.25
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class SNOW(BottomSupport):
    block_id = "snow"
    name = "tile.snow.name"
    _texture_path = "blocks.snow"
    break_sound = "dig.snow"
    solid = False
    collision_box = EMPTY
    light_attenuation = 1
    has_transparent_pixels = True
    hardness = 0.1
    preferred_tool = "shovel"

    _texture_cache = {}

    def __init__(self, layer=1):
        super().__init__()
        if layer > 8:
            raise Exception("layer > 8")
        self.layer = max(1, int(layer))

    def get_collision_box(self):

        collision_height = (self.layer - 1) / 8
        if collision_height <= 0:
            return EMPTY
        return BlockCollisionBox.from_box(0, 0, 1, collision_height)

    @client_method
    def get_texture(self, size, client):
        if (size, self.layer) in self._texture_cache:
            return self._texture_cache[(size, self.layer)]
        base_texture = client.resources_manager.get_texture_img(self._texture_path)

        width, height = base_texture.size
        layer_height = int(height * self.layer / 8)
        rect = pygame.Rect((0, height - layer_height, width, layer_height))

        tex = base_texture.subsurface(rect).copy()

        # 缩放为实际雪层尺寸（宽=bs，高=根据层数）
        tex_h = int(size * 0.125 * self.layer)
        final_texture = pygame.transform.scale(tex, (size, tex_h))

        self._texture_cache[(size, self.layer)] = final_texture.convert_alpha()

        return final_texture


@register_block
class SNOW_BLOCK(Block):
    block_id = "snow_block"
    name = "tile.snow.name"
    _texture_path = "blocks.snow"
    break_sound = "dig.snow"
    hardness = 0.2
    preferred_tool = "shovel"


@register_block
class ICE(Block):
    block_id = "ice"
    name = "tile.ice.name"
    _texture_path = "blocks.ice"
    break_sound = "dig.glass"
    friction = 0.98
    hardness = 0.5
    preferred_tool = "pickaxe"


@register_block
class WATER(FluidBlock):
    block_id = "water"
    name = "tile.water.name"
    _texture_path = "blocks.water_still"
    _flow_texture_path = "blocks.water_flow"
    _texture_cache = {}
    _scaled_atlas_cache = {}
    _precomposed_texture_cache = {}
    horizontal_flow_range = 4
    flowing_sound = "liquid.water"
    source_sound = "liquid.water"


@register_block
class LAVA(FluidBlock):
    block_id = "lava"
    name = "tile.lava.name"
    _texture_path = "blocks.lava_still"
    _flow_texture_path = "blocks.lava_flow"
    _texture_cache = {}
    _scaled_atlas_cache = {}
    _precomposed_texture_cache = {}

    max_level = 7

    flow_level_step = 2
    horizontal_flow_range = 2
    light_source = 15
    can_create_source = False
    flow_speed_ticks = 30
    flowing_sound = "liquid.lava"
    source_sound = "liquid.lavapop"
    entity_horizontal_drag = 0.5
    entity_vertical_drag = 0.5
    # 1.8.9 applies water currents through handleMaterialAcceleration, while
    # lava travel only uses its movement acceleration, drag and gravity.
    entity_current_push = 0.0


@register_block
class SUGAR_CANE(Plant):
    block_id = "sugar_cane"
    name = "tile.reeds.name"
    _texture_path = "blocks.reeds"

    def on_update(self):
        below = self.location.world.get_block(self.location.add(0, -1, 0))
        if getattr(below, "block_id", None) == self.block_id:
            return
        if not isinstance(below, (DIRT, SAND, RED_SAND, GRASS_BLOCK)):
            self.location.world.break_block(self.location)
            return
        for dx in (-1, 1):
            neighbor = self.location.world.get_block(
                self.location.x + dx, self.location.y - 1, self.location.z
            )
            if isinstance(neighbor, (WATER, ICE)):
                return
        self.location.world.break_block(self.location)


@register_block
class FERN(SeedDroppingGrass, GrassStain):
    block_id = "fern"
    name = "tile.tallgrass.fern.name"
    _texture_path = "blocks.fern"


@register_block
class DEAD_BUSH(Plant):
    block_id = "dead_bush"
    name = "tile.deadbush.name"
    _texture_path = "blocks.deadbush"


@register_block
class CACTUS(Block):
    block_id = "cactus"
    name = "tile.cactus.name"
    _texture_path = "blocks.cactus_side"
    break_sound = "dig.cloth"
    hardness = 0.4
    preferred_tool = "axe"

    def on_update(self):
        below = self.location.world.get_block(self.location.add(0, -1, 0))
        if not isinstance(below, (CACTUS, SAND, RED_SAND)):
            self.location.world.break_block(self.location)


@register_block
class BROWN_MUSHROOM(Plant):
    block_id = "brown_mushroom"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_brown"

    def on_update(self):
        pass


@register_block
class RED_MUSHROOM(Plant):
    block_id = "red_mushroom"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_red"

    def on_update(self):
        pass


@register_block
class VINE(GrassStain):
    block_id = "vine"
    name = "tile.vine.name"
    _texture_path = "blocks.vine"
    light_attenuation = 1

    def on_update(self):

        pass


@register_block
class COAL_ORE(Block):
    block_id = "coal_ore"
    name = "tile.oreCoal.name"
    _texture_path = "blocks.coal_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    drops = (BlockDrop(materials.COAL),)


@register_block
class IRON_ORE(Block):
    block_id = "iron_ore"
    name = "tile.oreIron.name"
    _texture_path = "blocks.iron_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "stone"


@register_block
class GOLD_ORE(Block):
    block_id = "gold_ore"
    name = "tile.oreGold.name"
    _texture_path = "blocks.gold_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


@register_block
class DIAMOND_ORE(Block):
    block_id = "diamond_ore"
    name = "tile.oreDiamond.name"
    _texture_path = "blocks.diamond_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"
    drops = (BlockDrop(materials.DIAMOND),)


@register_block
class EMERALD_ORE(Block):
    block_id = "emerald_ore"
    name = "tile.oreEmerald.name"
    _texture_path = "blocks.emerald_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


@register_block
class LAPIS_ORE(Block):
    block_id = "lapis_ore"
    name = "tile.oreLapis.name"
    _texture_path = "blocks.lapis_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "stone"


@register_block
class REDSTONE_ORE(Block):
    block_id = "redstone_ore"
    name = "tile.oreRedstone.name"
    _texture_path = "blocks.redstone_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


@register_block
class BLUE_ORCHID(Plant):
    block_id = "blue_orchid"
    name = "tile.flower2.blueOrchid.name"
    _texture_path = "blocks.flower_blue_orchid"


@register_block
class ALLIUM(Plant):
    block_id = "allium"
    name = "tile.flower2.allium.name"
    _texture_path = "blocks.flower_allium"


@register_block
class AZURE_BLUET(Plant):
    block_id = "azure_bluet"
    name = "tile.flower2.houstonia.name"
    _texture_path = "blocks.flower_houstonia"


@register_block
class OXEYE_DAISY(Plant):
    block_id = "oxeye_daisy"
    name = "tile.flower2.oxeyeDaisy.name"
    _texture_path = "blocks.flower_oxeye_daisy"


@register_block
class DIAMOND_BLOCK(Block):
    block_id = "diamond_block"
    name = "tile.blockDiamond.name"
    _texture_path = "blocks.diamond_block"
    hardness = 5.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


@register_block
class TORCH(ParticleEmitterBlock):
    block_id = "torch"
    name = "tile.torch.name"
    hardness = 0
    solid = False
    collision_box = EMPTY
    _texture_path = "blocks.torch_on"
    light_source = 15
    break_sound = "dig.wood"
    has_transparent_pixels = True

    FACING_UP = "up"
    FACING_BACK = "back"
    FACING_LEFT = "left"
    FACING_RIGHT = "right"
    FACING_FORWARD = FACING_BACK  # 深度层中的“向前”安装形态
    FACINGS = (FACING_UP, FACING_BACK, FACING_LEFT, FACING_RIGHT)
    # 短名称便于放置逻辑和未来的墙挂方块直接复用。
    UP, BACK, LEFT, RIGHT = FACINGS
    _FACING_ALIASES = {
        "upright": FACING_UP,
        "forward": FACING_BACK,
        "front": FACING_BACK,
        "behind": FACING_BACK,
        "backward": FACING_BACK,
        "rear": FACING_BACK,
    }
    # 侧向/向后的火把共用一个纵向长度，保持斜视角下的视觉基准一致。
    _NON_UP_HEIGHT_RATIO = 0.85
    _SIDE_TILT_ANGLE = 22.5
    _oriented_texture_cache = {}
    particle_id = "minecraft:flame"
    particle_interval_ticks = 4
    particle_count = 1

    def __init__(self, facing="up", nbt=None, *, direction=None):
        # 允许 TORCH(nbt_dict) 保持 Block 的旧式构造习惯；direction 是
        # 面向未来 API 的别名，存档仍统一使用 facing 字段。
        if isinstance(facing, dict) and nbt is None:
            nbt, facing = facing, "up"
        self.facing = self.normalize_facing(
            direction if direction is not None else facing
        )
        super().__init__(nbt)
        self.facing = self.normalize_facing(self.facing)

    @classmethod
    def normalize_facing(cls, facing) -> str:
        facing = str(facing).lower() if facing is not None else cls.FACING_UP
        facing = cls._FACING_ALIASES.get(facing, facing)
        if facing not in cls.FACINGS:
            raise ValueError(f"Unknown torch facing: {facing}")
        return facing

    def apply_placement_nbt(self, nbt: dict) -> None:
        """应用客户端允许提交的放置状态，避免写入运行时内部字段。"""
        if isinstance(nbt, dict) and "facing" in nbt:
            self.facing = self.normalize_facing(nbt["facing"])

    @property
    def direction(self) -> str:
        return self.facing

    @direction.setter
    def direction(self, value):
        self.facing = self.normalize_facing(value)

    @property
    def orientation(self) -> str:
        return self.facing

    @orientation.setter
    def orientation(self, value):
        self.facing = self.normalize_facing(value)

    def get_particle_position(self) -> tuple[float, float, int]:
        if self.location is None:
            return 0.0, 0.0, 0
        offsets = {
            self.FACING_UP: (0.00, 0.7),
            self.FACING_BACK: (0.00, 0.70),
            self.FACING_LEFT: (0.30, 0.75),
            self.FACING_RIGHT: (-0.30, 0.75),
        }
        dx, dy = offsets[self.facing]
        return self.location.x + 0.5 + dx, self.location.y + dy, self.location.z

    def get_support_offset(self) -> tuple[int, int, int]:
        """根据火把朝向选择地面、深度面或左右墙面支撑。"""
        if self.facing == self.FACING_BACK:
            # z=0 是前景层，向前的火把由同格 z=1 背景方块支撑；
            # 反向使用时也允许 z=1 火把依赖 z=0 方块。
            return (0, 0, 1 if self.location is None or self.location.z == 0 else -1)
        if self.facing == self.FACING_LEFT:
            return (1, 0, 0)
        if self.facing == self.FACING_RIGHT:
            return (-1, 0, 0)
        return super().get_support_offset()

    def get_placement_location(
        self, target, *, player=None, fore_place=False, context=None
    ):
        """按射线命中面选择火把形态；支撑与可替换性仍由自身校验。"""
        target_location = getattr(target, "location", None)
        if target_location is None or not self.is_full_block(target):
            return None
        world = target_location.world
        fore_place = bool(fore_place or getattr(context, "fore_place", False))

        # 前景模式下点击背景块，明确表示要把火把插入同格前景层。
        if fore_place and target_location.z == 1:
            self.facing = self.FACING_FORWARD
            place_location = target_location.add(0, 0, -1)
        # 前景模式点击前景块时，优先将火把放在其上方；这避免把“前景
        # 放置”误解成永远覆盖/插入同一格。
        elif fore_place and target_location.z == 0:
            above = target_location.add(0, 1, 0)
            if not world.get_block(above).replaceable:
                return None
            self.facing = self.FACING_UP
            place_location = above
        else:
            hit_face = getattr(context, "hit_face", None) or "top"
            target_z = getattr(context, "target_z", target_location.z)
            if hit_face == "bottom":
                # 底面命中代表“向前插入”。两层世界中，前景/背景目标
                # 自动选择另一层，仍由 can_survive 检查实际支撑。
                self.facing = self.FACING_FORWARD
                forward_z = 0 if target_location.z == 1 else 1
                place_location = Location(
                    world, target_location.x, target_location.y, forward_z
                )
            elif hit_face == "left":
                self.facing = self.FACING_LEFT
                place_location = Location(
                    world, target_location.x - 1, target_location.y, target_z
                )
            elif hit_face == "right":
                self.facing = self.FACING_RIGHT
                place_location = Location(
                    world, target_location.x + 1, target_location.y, target_z
                )
            elif hit_face == "top":
                self.facing = self.FACING_UP
                place_location = Location(
                    world, target_location.x, target_location.y + 1, target_z
                )
            else:
                return None

        if not world.get_block(place_location).replaceable:
            if target_location.z == 1:
                self.facing = self.FACING_FORWARD
                return target_location.add(0, 0, -1)
            return None

        self.location = place_location
        if not self.can_survive():
            self.location = None
            return None
        return place_location

    @classmethod
    @client_method
    def _get_oriented_texture(cls, texture, size, facing, client=None):
        m = client.render.block_size // 16
        size = max(1, int(round(size)))
        scaled = pygame.transform.scale(texture, (size, size)).convert_alpha()
        if facing == cls.FACING_UP:
            return scaled

        if facing == cls.FACING_BACK:
            height = max(1, int(round(size * cls._NON_UP_HEIGHT_RATIO)))
            b = pygame.transform.scale(scaled, (size, height)).convert_alpha()
            result = pygame.Surface(b.get_size(), pygame.SRCALPHA)
            result.blit(b, (0, -3 * m))
            return result

        angle = (
            cls._SIDE_TILT_ANGLE if facing == cls.FACING_LEFT else -cls._SIDE_TILT_ANGLE
        )
        rotated = pygame.transform.rotate(scaled, angle)
        # 旋转后纹理居中，需要平移使火把根部紧贴支撑方块。
        # FACING_LEFT:  支撑方块在右侧，向右平移。正值越大越靠右。
        # FACING_RIGHT: 支撑方块在左侧，向左平移。负值越大越靠左。
        shift_x = 3 * m if facing == cls.FACING_LEFT else -7.7 * m
        result = pygame.Surface(rotated.get_size(), pygame.SRCALPHA)
        result.blit(rotated, (shift_x, 0))
        return result

    @client_method
    def get_texture(self, size, client=None):
        texture = client.resources_manager.get_texture_img(self._texture_path)
        if texture is None:
            return None
        cls = type(self)
        if cls.has_transparent_pixels is None:
            cls.has_transparent_pixels = (
                client.resources_manager.has_transparent_pixels(texture)
            )
        size = max(1, int(round(size)))
        cache = cls.__dict__.get("_oriented_texture_cache")
        if cache is None:
            cache = {}
            cls._oriented_texture_cache = cache
        # Surface 对象本身作为键可同时兼容静态纹理缓存和动画纹理换帧，
        # 不依赖 id 复用行为。
        key = (texture, size, self.facing)
        oriented = cache.get(key)
        if oriented is None:
            oriented = cls._get_oriented_texture(texture, size, self.facing)
            cache[key] = oriented
            if len(cache) > 32:
                cache.pop(next(iter(cache)))
        return oriented


class WoodenSlab(SLABS):
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class StoneSlab(SLABS):
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class OAK_SLAB(WoodenSlab):
    block_id = "oak_slab"
    name = "tile.woodSlab.oak.name"
    _texture_path = "blocks.planks_oak"


@register_block
class SPRUCE_SLAB(WoodenSlab):
    block_id = "spruce_slab"
    name = "tile.woodSlab.spruce.name"
    _texture_path = "blocks.planks_spruce"


@register_block
class BIRCH_SLAB(WoodenSlab):
    block_id = "birch_slab"
    name = "tile.woodSlab.birch.name"
    _texture_path = "blocks.planks_birch"


@register_block
class JUNGLE_SLAB(WoodenSlab):
    block_id = "jungle_slab"
    name = "tile.woodSlab.jungle.name"
    _texture_path = "blocks.planks_jungle"


@register_block
class ACACIA_SLAB(WoodenSlab):
    block_id = "acacia_slab"
    name = "tile.woodSlab.acacia.name"
    _texture_path = "blocks.planks_acacia"


@register_block
class DARK_OAK_SLAB(WoodenSlab):
    block_id = "dark_oak_slab"
    name = "tile.woodSlab.big_oak.name"
    _texture_path = "blocks.planks_big_oak"


@register_block
class STONE_SLAB(StoneSlab):
    block_id = "stone_slab"
    name = "tile.stoneSlab.stone.name"
    _texture_path = "blocks.stone"
    blast_resistance = 6.0


@register_block
class COBBLESTONE_SLAB(StoneSlab):
    block_id = "cobblestone_slab"
    name = "tile.stoneSlab.cobble.name"
    _texture_path = "blocks.cobblestone"
    blast_resistance = 6.0


@register_block
class SANDSTONE_SLAB(StoneSlab):
    block_id = "sandstone_slab"
    name = "tile.stoneSlab.sand.name"
    _texture_path = "blocks.sandstone_normal"
    hardness = 0.8


@register_block
class RED_SANDSTONE_SLAB(SANDSTONE_SLAB):
    block_id = "red_sandstone_slab"
    name = "tile.stoneSlab2.red_sandstone.name"
    _texture_path = "blocks.red_sandstone_normal"


class WoodenStairs(STAIRS):
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class StoneStairs(STAIRS):
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class OAK_STAIRS(WoodenStairs):
    block_id = "oak_stairs"
    name = "tile.stairsWood.name"
    _texture_path = "blocks.planks_oak"


@register_block
class SPRUCE_STAIRS(WoodenStairs):
    block_id = "spruce_stairs"
    name = "tile.stairsWoodSpruce.name"
    _texture_path = "blocks.planks_spruce"


@register_block
class BIRCH_STAIRS(WoodenStairs):
    block_id = "birch_stairs"
    name = "tile.stairsWoodBirch.name"
    _texture_path = "blocks.planks_birch"


@register_block
class JUNGLE_STAIRS(WoodenStairs):
    block_id = "jungle_stairs"
    name = "tile.stairsWoodJungle.name"
    _texture_path = "blocks.planks_jungle"


@register_block
class ACACIA_STAIRS(WoodenStairs):
    block_id = "acacia_stairs"
    name = "tile.stairsWoodAcacia.name"
    _texture_path = "blocks.planks_acacia"


@register_block
class DARK_OAK_STAIRS(WoodenStairs):
    block_id = "dark_oak_stairs"
    name = "tile.stairsWoodDarkOak.name"
    _texture_path = "blocks.planks_big_oak"


@register_block
class STONE_STAIRS(StoneStairs):
    block_id = "stone_stairs"
    name = "tile.stairsStone.name"
    _texture_path = "blocks.stone"
    blast_resistance = 6.0


@register_block
class COBBLESTONE_STAIRS(StoneStairs):
    block_id = "cobblestone_stairs"
    name = "tile.stairsStone.name"
    _texture_path = "blocks.cobblestone"
    blast_resistance = 6.0


@register_block
class SANDSTONE_STAIRS(StoneStairs):
    block_id = "sandstone_stairs"
    name = "tile.stairsSandStone.name"
    _texture_path = "blocks.sandstone_normal"
    hardness = 0.8


@register_block
class RED_SANDSTONE_STAIRS(SANDSTONE_STAIRS):
    block_id = "red_sandstone_stairs"
    name = "tile.stairsRedSandStone.name"
    _texture_path = "blocks.red_sandstone_normal"


@register_block
class TNT(Block):
    block_id = "tnt"
    name = "tile.tnt.name"
    _texture_path = "blocks.tnt_side"
    hardness = 0.0
    blast_resistance = 0.0
    break_sound = "dig.grass"

    def accepts_item_use(self, material) -> bool:
        return bool(getattr(material, "ignites_blocks", False))

    def prime(
        self, *, fuse: int = 80, igniter=None, play_sound: bool = True
    ) -> bool:
        if self.location is None:
            return False
        world = self.location.world

        if world.get_block(self.location) is not self:
            return False
        from src.server.entities.primed_tnt import PrimedTNT

        x, y, z = self.location.x, self.location.y, self.location.z
        world.set_block(AIR(), self.location)
        primed = PrimedTNT(x + 0.01, y, z, world, fuse=fuse, owner=igniter)
        world.spawn_entity(primed)
        server = getattr(world, "server", None)
        if server is not None and play_sound:
            server.broadcast_sound("game.tnt.primed", x + 0.5, y + 0.5, z)
        return True

    def on_use(self, player, material) -> bool:
        if not getattr(material, "ignites_blocks", False):
            return False
        return self.prime(fuse=80, igniter=player)

    def on_exploded(self, power: float, source=None) -> bool:

        self.prime(
            fuse=random.randint(10, 30), igniter=source, play_sound=False
        )
        return False


@register_block
class MYCELIUM(Block):
    block_id = "mycelium"
    name = "tile.mycel.name"
    _texture_path = "blocks.mycelium_side"


@register_block
class MUSHROOM_STEM(Block):
    block_id = "mushroom_stem"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_block_skin_stem"


@register_block
class RED_MUSHROOM_BLOCK(Block):
    block_id = "red_mushroom_block"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_block_skin_red"


@register_block
class BROWN_MUSHROOM_BLOCK(Block):
    block_id = "brown_mushroom_block"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_block_skin_brown"


@register_block
class FIRE(Block):
    block_id = "fire"
    name = "tile.fire.name"
    _texture_path = "blocks.fire_layer_0"
    light_source = 15
    solid = False
    collision_box = EMPTY
    replaceable = True
    suffocating = False
    redstone_conducting = False
    blast_resistance = 0.0
    drops = ()

    def get_collision_box(self):
        return EMPTY

    def on_entity_inside(self, entity) -> None:
        # Client movement prediction also invokes block hooks. Health and fire
        # state remain server-authoritative and arrive through entity packets.
        if getattr(getattr(entity, "world", None), "server", None) is None:
            return
        ignite = getattr(entity, "set_seconds_on_fire", None)
        if callable(ignite):
            ignite(8.0)
        damage = getattr(entity, "apply_damage", None)
        if callable(damage):
            damage(1.0, IN_FIRE, source=None)

class ColoredWool(Block):
    break_sound = "dig.cloth"


@register_block
class WHITE_WOOL(ColoredWool):
    block_id = "white_wool"
    name = "tile.cloth.white.name"
    _texture_path = "blocks.wool_colored_white"


class ColoredStainedGlass(Block):
    break_sound = "dig.glass"
    hardness = 0.3
    light_attenuation = 1
    suffocating = False
    redstone_conducting = False
    drops = ()

@register_block
class WHITE_STAINED_GLASS(ColoredStainedGlass):
    block_id = "white_stained_glass"
    name = "tile.stainedGlass.white.name"
    _texture_path = "blocks.glass_white"


@register_block
class ORANGE_WOOL(ColoredWool):
    block_id = "orange_wool"
    name = "tile.cloth.orange.name"
    _texture_path = "blocks.wool_colored_orange"


@register_block
class ORANGE_STAINED_GLASS(ColoredStainedGlass):
    block_id = "orange_stained_glass"
    name = "tile.stainedGlass.orange.name"
    _texture_path = "blocks.glass_orange"


@register_block
class MAGENTA_WOOL(ColoredWool):
    block_id = "magenta_wool"
    name = "tile.cloth.magenta.name"
    _texture_path = "blocks.wool_colored_magenta"


@register_block
class MAGENTA_STAINED_GLASS(ColoredStainedGlass):
    block_id = "magenta_stained_glass"
    name = "tile.stainedGlass.magenta.name"
    _texture_path = "blocks.glass_magenta"


@register_block
class LIGHT_BLUE_WOOL(ColoredWool):
    block_id = "light_blue_wool"
    name = "tile.cloth.light_blue.name"
    _texture_path = "blocks.wool_colored_light_blue"


@register_block
class LIGHT_BLUE_STAINED_GLASS(ColoredStainedGlass):
    block_id = "light_blue_stained_glass"
    name = "tile.stainedGlass.light_blue.name"
    _texture_path = "blocks.glass_light_blue"


@register_block
class YELLOW_WOOL(ColoredWool):
    block_id = "yellow_wool"
    name = "tile.cloth.yellow.name"
    _texture_path = "blocks.wool_colored_yellow"


@register_block
class YELLOW_STAINED_GLASS(ColoredStainedGlass):
    block_id = "yellow_stained_glass"
    name = "tile.stainedGlass.yellow.name"
    _texture_path = "blocks.glass_yellow"


@register_block
class LIME_WOOL(ColoredWool):
    block_id = "lime_wool"
    name = "tile.cloth.lime.name"
    _texture_path = "blocks.wool_colored_lime"


@register_block
class LIME_STAINED_GLASS(ColoredStainedGlass):
    block_id = "lime_stained_glass"
    name = "tile.stainedGlass.lime.name"
    _texture_path = "blocks.glass_lime"


@register_block
class PINK_WOOL(ColoredWool):
    block_id = "pink_wool"
    name = "tile.cloth.pink.name"
    _texture_path = "blocks.wool_colored_pink"


@register_block
class PINK_STAINED_GLASS(ColoredStainedGlass):
    block_id = "pink_stained_glass"
    name = "tile.stainedGlass.pink.name"
    _texture_path = "blocks.glass_pink"


@register_block
class GRAY_WOOL(ColoredWool):
    block_id = "gray_wool"
    name = "tile.cloth.gray.name"
    _texture_path = "blocks.wool_colored_gray"


@register_block
class GRAY_STAINED_GLASS(ColoredStainedGlass):
    block_id = "gray_stained_glass"
    name = "tile.stainedGlass.gray.name"
    _texture_path = "blocks.glass_gray"


@register_block
class LIGHT_GRAY_WOOL(ColoredWool):
    block_id = "light_gray_wool"
    name = "tile.cloth.silver.name"
    _texture_path = "blocks.wool_colored_silver"


@register_block
class LIGHT_GRAY_STAINED_GLASS(ColoredStainedGlass):
    block_id = "light_gray_stained_glass"
    name = "tile.stainedGlass.silver.name"
    _texture_path = "blocks.glass_silver"


@register_block
class CYAN_WOOL(ColoredWool):
    block_id = "cyan_wool"
    name = "tile.cloth.cyan.name"
    _texture_path = "blocks.wool_colored_cyan"


@register_block
class CYAN_STAINED_GLASS(ColoredStainedGlass):
    block_id = "cyan_stained_glass"
    name = "tile.stainedGlass.cyan.name"
    _texture_path = "blocks.glass_cyan"


@register_block
class PURPLE_WOOL(ColoredWool):
    block_id = "purple_wool"
    name = "tile.cloth.purple.name"
    _texture_path = "blocks.wool_colored_purple"


@register_block
class PURPLE_STAINED_GLASS(ColoredStainedGlass):
    block_id = "purple_stained_glass"
    name = "tile.stainedGlass.purple.name"
    _texture_path = "blocks.glass_purple"


@register_block
class BLUE_WOOL(ColoredWool):
    block_id = "blue_wool"
    name = "tile.cloth.blue.name"
    _texture_path = "blocks.wool_colored_blue"


@register_block
class BLUE_STAINED_GLASS(ColoredStainedGlass):
    block_id = "blue_stained_glass"
    name = "tile.stainedGlass.blue.name"
    _texture_path = "blocks.glass_blue"


@register_block
class BROWN_WOOL(ColoredWool):
    block_id = "brown_wool"
    name = "tile.cloth.brown.name"
    _texture_path = "blocks.wool_colored_brown"


@register_block
class BROWN_STAINED_GLASS(ColoredStainedGlass):
    block_id = "brown_stained_glass"
    name = "tile.stainedGlass.brown.name"
    _texture_path = "blocks.glass_brown"


@register_block
class GREEN_WOOL(ColoredWool):
    block_id = "green_wool"
    name = "tile.cloth.green.name"
    _texture_path = "blocks.wool_colored_green"


@register_block
class GREEN_STAINED_GLASS(ColoredStainedGlass):
    block_id = "green_stained_glass"
    name = "tile.stainedGlass.green.name"
    _texture_path = "blocks.glass_green"


@register_block
class RED_WOOL(ColoredWool):
    block_id = "red_wool"
    name = "tile.cloth.red.name"
    _texture_path = "blocks.wool_colored_red"


@register_block
class RED_STAINED_GLASS(ColoredStainedGlass):
    block_id = "red_stained_glass"
    name = "tile.stainedGlass.red.name"
    _texture_path = "blocks.glass_red"


@register_block
class BLACK_WOOL(ColoredWool):
    block_id = "black_wool"
    name = "tile.cloth.black.name"
    _texture_path = "blocks.wool_colored_black"


@register_block
class BLACK_STAINED_GLASS(ColoredStainedGlass):
    block_id = "black_stained_glass"
    name = "tile.stainedGlass.black.name"
    _texture_path = "blocks.glass_black"




@register_block
class BRICKS(Block):
    block_id = "bricks"
    name = "tile.bricks.name"
    _texture_path = "blocks.brick"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class BOOKSHELF(Block):
    block_id = "bookshelf"
    name = "tile.bookshelf.name"
    _texture_path = "blocks.bookshelf"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class END_STONE(Block):
    block_id = "end_stone"
    name = "tile.whiteStone.name"
    _texture_path = "blocks.end_stone"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class HAY_BLOCK(Block):
    block_id = "hay_block"
    name = "tile.hayBlock.name"
    _texture_path = "blocks.hay_block_side"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class NETHER_BRICKS(Block):
    block_id = "nether_bricks"
    name = "tile.netherBrick.name"
    _texture_path = "blocks.nether_brick"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class NETHERRACK(Block):
    block_id = "netherrack"
    name = "tile.netherrack.name"
    _texture_path = "blocks.netherrack"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class PRISMARINE(Block):
    block_id = "prismarine"
    name = "tile.prismarine.rough.name"
    _texture_path = "blocks.prismarine_rough"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class PRISMARINE_BRICKS(Block):
    block_id = "prismarine_bricks"
    name = "tile.prismarine.bricks.name"
    _texture_path = "blocks.prismarine_bricks"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class DARK_PRISMARINE(Block):
    block_id = "dark_prismarine"
    name = "tile.prismarine.dark.name"
    _texture_path = "blocks.prismarine_dark"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class QUARTZ_BLOCK(Block):
    block_id = "quartz_block"
    name = "tile.quartz_block.name"
    _texture_path = "blocks.quartz_block_side"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class QUARTZ_COLUMN(Block):
    block_id = "quartz_column"
    name = "tile.quartz_block_lines.name"
    _texture_path = "blocks.quartz_block_lines"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class CHISELED_QUARTZ_BLOCK(Block):
    block_id = "chiseled_quartz_block"
    name = "tile.quartz_block_chiseled.name"
    _texture_path = "blocks.quartz_block_chiseled"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class STONE_BRICKS(Block):
    block_id = "stone_bricks"
    name = "tile.stonebrick.name"
    _texture_path = "blocks.stonebrick"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class MOSSY_STONE_BRICKS(Block):
    block_id = "mossy_stone_bricks"
    name = "tile.stonebrick.mossy.name"
    _texture_path = "blocks.stonebrick_mossy"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class CRACKED_STONE_BRICKS(Block):
    block_id = "cracked_stone_bricks"
    name = "tile.stonebrick.cracked.name"
    _texture_path = "blocks.stonebrick_cracked"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


@register_block
class CHISELED_STONE_BRICKS(Block):
    block_id = "chiseled_stone_bricks"
    name = "tile.stonebrick.chiseled.name"
    _texture_path = "blocks.stonebrick_carved"
    preferred_tool = "pickaxe"
    requires_correct_tool = True




class ChestInventory(Inventory):
    def __init__(self, chest):
        super().__init__(27)
        self.chest = chest
        self.owner_block = chest

    def on_changed(self) -> None:
        self.chest.on_inventory_changed()


class CombinedChestInventory(Inventory):
    """Live 54-slot view over two independently persisted chest halves."""

    def __init__(self, left_chest, right_chest):
        self.left_chest = left_chest
        self.right_chest = right_chest
        self.chest = left_chest
        self.owner_block = left_chest
        self.owner_blocks = (left_chest, right_chest)
        self.max_slots = 54
        self.selected_slot = 0

    def __len__(self):
        return self.max_slots

    def __iter__(self):
        yield from self.left_chest.inventory
        yield from self.right_chest.inventory

    def __getitem__(self, slot):
        slot = int(slot)
        if not 0 <= slot < self.max_slots:
            raise IndexError("Inventory index out of range")
        if slot < 27:
            return self.left_chest.inventory[slot]
        return self.right_chest.inventory[slot - 27]

    def __setitem__(self, slot, value):
        slot = int(slot)
        if not 0 <= slot < self.max_slots:
            raise IndexError("Inventory index out of range")
        if slot < 27:
            self.left_chest.inventory[slot] = value
        else:
            self.right_chest.inventory[slot - 27] = value

    def is_full(self) -> bool:
        return all(not stack.is_empty() for stack in self)

    def get_first_empty_slot(self) -> int:
        return next((slot for slot, stack in enumerate(self) if stack.is_empty()), -1)

    def can_place(self, slot, stack) -> bool:
        slot = int(slot)
        if slot < 27:
            return self.left_chest.inventory.can_place(slot, stack)
        return self.right_chest.inventory.can_place(slot - 27, stack)

    def contains_chest(self, chest) -> bool:
        return chest is self.left_chest or chest is self.right_chest

    def on_changed(self) -> None:
        self.owner_block.on_inventory_changed()


@register_block
class CHEST(Block):
    block_id = "chest"
    name = "tile.chest.name"
    _texture_path = "entity.chest.normal"
    break_sound = "dig.wood"
    hardness = 2.5
    blast_resistance = 2.5
    preferred_tool = "axe"
    collision_box = BlockCollisionBox.from_box(1 / 16, 0, 15 / 16, 14 / 16)
    suffocating = False
    redstone_conducting = False
    light_attenuation = 1
    has_transparent_pixels = True
    _closed_texture_cache = {}
    closed_packet_class = "ChestClosed"

    # Minecraft 1.21.4 ChestModel#createSingleBodyLayer supplies the cuboid
    # sizes/offsets. ModelPart.Cube maps their SOUTH faces to these atlas
    # rectangles; its vertex order flips both axes for a 2-D front projection.
    _LID_UV = pygame.Rect(42, 14, 14, 5)
    _BOTTOM_UV = pygame.Rect(42, 33, 14, 10)
    _LOCK_UV = pygame.Rect(4, 1, 2, 4)
    # The bundled legacy resource pack stores both 15-wide halves in one
    # 128x64 atlas. Combining the two 1.21.4 half-models produces a 30-wide
    # front face and keeps the lock split across the inner block boundary.
    _DOUBLE_LID_UV = pygame.Rect(58, 14, 30, 5)
    _DOUBLE_BOTTOM_UV = pygame.Rect(58, 33, 30, 10)
    _DOUBLE_LOCK_UV = pygame.Rect(4, 1, 2, 4)

    def __init__(self, nbt=None):
        self.inventory = ChestInventory(self)
        self._viewers = set()
        # Pairing is persistent block state, matching vanilla's
        # SINGLE/LEFT/RIGHT property. ``False`` identifies saves written by
        # the earlier adjacency-derived implementation so an existing double
        # chest can be migrated without losing its relationship.
        self.pair_offset = 0
        self._pair_state_explicit = False
        super().__init__()
        if nbt:
            self.write_nbt(nbt)

    def _adjacent_chests(self) -> tuple["CHEST", ...]:
        if self.location is None:
            return ()
        world = self.location.world
        result = []
        for dx in (-1, 1):
            neighbor = world.get_block(self.location.add(dx, 0, 0))
            if isinstance(neighbor, CHEST):
                result.append(neighbor)
        return tuple(result)

    def get_pair(self):
        if self.location is None:
            return None
        if self._pair_state_explicit:
            if self.pair_offset not in (-1, 1):
                return None
            partner = self.location.world.get_block(
                self.location.add(self.pair_offset, 0, 0)
            )
            if not isinstance(partner, CHEST):
                return None
            if partner._pair_state_explicit:
                return (
                    partner
                    if partner.pair_offset == -self.pair_offset
                    else None
                )
            # Mixed old/new chunk saves are possible at a chunk boundary.
            explicit_claimants = [
                chest
                for chest in partner._adjacent_chests()
                if chest._pair_state_explicit
                and chest.pair_offset
                == int(partner.location.x - chest.location.x)
            ]
            return partner if explicit_claimants == [self] else None

        # Legacy saves had no explicit state because the old implementation
        # inferred a double chest solely from adjacency. Ignore newly placed,
        # explicitly-single neighbors so adding a third chest cannot dissolve
        # the original pair before the next save migrates it.
        explicit_claimants = [
            chest
            for chest in self._adjacent_chests()
            if chest._pair_state_explicit
            and chest.pair_offset == int(self.location.x - chest.location.x)
        ]
        if len(explicit_claimants) == 1:
            return explicit_claimants[0]
        legacy_neighbors = [
            chest
            for chest in self._adjacent_chests()
            if not chest._pair_state_explicit
        ]
        return legacy_neighbors[0] if len(legacy_neighbors) == 1 else None

    def _set_pair(self, partner) -> None:
        offset = int(partner.location.x - self.location.x)
        if offset not in (-1, 1):
            raise ValueError("chest partners must be horizontally adjacent")
        self.pair_offset = offset
        partner.pair_offset = -offset
        self._pair_state_explicit = True
        partner._pair_state_explicit = True

    @staticmethod
    def _notify_state_changed(chest) -> None:
        if chest.location is None:
            return
        world = chest.location.world
        rx = int(chest.location.x) // 16
        mark_chunk_dirty = getattr(world, "mark_chunk_dirty", None)
        if callable(mark_chunk_dirty):
            mark_chunk_dirty(rx)
        invalidate_chunk_packet = getattr(world, "invalidate_chunk_packet", None)
        if callable(invalidate_chunk_packet):
            invalidate_chunk_packet(rx)
        mark_render_chunk_dirty = getattr(world, "_mark_render_chunk_dirty", None)
        if callable(mark_render_chunk_dirty):
            mark_render_chunk_dirty(rx)
        server = getattr(world, "server", None)
        if server is None:
            return
        for player in tuple(getattr(server, "players", ())):
            is_loading = getattr(player, "is_loading_position", None)
            if callable(is_loading) and is_loading(
                int(chest.location.x),
                int(chest.location.y),
                int(chest.location.z),
            ):
                server.send_client_socket(player, chest, "BlockUpdate")

    def _unlink_pair(self) -> None:
        partner = self.get_pair()
        self.pair_offset = 0
        self._pair_state_explicit = True
        if partner is not None:
            partner.pair_offset = 0
            partner._pair_state_explicit = True
            self._notify_state_changed(partner)
        # Do not publish a BlockUpdate for ``self`` here. Both callers unlink
        # because this half is about to be replaced; World.break_block sends a
        # BreakBlock packet before World.set_block invokes on_unload, so a
        # later chest update would resurrect this position as a client ghost.

    def _ordered_chests(self) -> tuple["CHEST", ...]:
        pair = self.get_pair()
        if pair is None:
            return (self,)
        return tuple(sorted((self, pair), key=lambda chest: chest.location.x))

    def get_chest_type(self) -> str:
        pair = self.get_pair()
        if pair is None:
            return "single"
        return "left" if self.location.x < pair.location.x else "right"

    def _menu_inventory(self):
        chests = self._ordered_chests()
        if len(chests) == 1:
            return self.inventory
        return CombinedChestInventory(chests[0], chests[1])

    def _all_viewers(self) -> set:
        viewers = set()
        for chest in self._ordered_chests():
            viewers.update(chest._viewers)
        return viewers

    def get_collision_box(self):
        chest_type = self.get_chest_type()
        if chest_type == "left":
            return BlockCollisionBox.from_box(1 / 16, 0, 1, 14 / 16)
        if chest_type == "right":
            return BlockCollisionBox.from_box(0, 0, 15 / 16, 14 / 16)
        return self.collision_box

    def place_at(self, location, *, force_single=False) -> bool:
        # Only an explicitly single neighbor is eligible. A chest beside an
        # existing double chest is therefore placed normally but stays single;
        # the next chest can pair with it, allowing arbitrarily long rows.
        candidates = [
            neighbor
            for neighbor in (
                location.world.get_block(location.add(-1, 0, 0)),
                location.world.get_block(location.add(1, 0, 0)),
            )
            if isinstance(neighbor, CHEST) and neighbor.get_pair() is None
        ]
        partner = None if force_single or not candidates else candidates[0]
        if partner is not None:
            partner.close_all_viewers()

        self.pair_offset = 0
        self._pair_state_explicit = True
        if not super().place_at(location):
            return False
        if partner is not None:
            self._set_pair(partner)
            self._notify_state_changed(partner)
            self._notify_state_changed(self)
        return True

    @property
    def container_id(self) -> str:
        if self.location is None:
            return "chest:unplaced"
        # Both halves must expose one stable id. Otherwise opening the right
        # half and later syncing/closing through the left half would address
        # two different containers.
        primary = self._ordered_chests()[0]
        return "chest:{},{},{}".format(
            int(primary.location.x),
            int(primary.location.y),
            int(primary.location.z),
        )

    def parse_nbt(self) -> dict:
        from src.server.inventory import serialize_inventory

        pair = self.get_pair()
        pair_offset = (
            int(pair.location.x - self.location.x)
            if pair is not None and self.location is not None
            else 0
        )
        return {
            "items": serialize_inventory(self.inventory),
            "pair_offset": pair_offset,
        }

    def write_nbt(self, nbt):
        import ast
        from src.server.inventory import restore_inventory

        if isinstance(nbt, str):
            nbt = ast.literal_eval(nbt)
        if isinstance(nbt, dict):
            restore_inventory(self.inventory, nbt.get("items", []))
            if "pair_offset" in nbt:
                try:
                    pair_offset = int(nbt["pair_offset"])
                except (TypeError, ValueError, OverflowError):
                    pair_offset = 0
                self.pair_offset = pair_offset if pair_offset in (-1, 1) else 0
                self._pair_state_explicit = True

    def get_texture_path(self) -> str:
        if self.get_chest_type() == "single":
            return self._texture_path
        return "entity.chest.normal_double"

    @client_method
    def get_texture(self, size, client):
        size = max(1, int(round(size)))
        chest_type = self.get_chest_type()
        atlas = client.resources_manager.get_texture_img(self.get_texture_path())
        if atlas is None:
            return None
        cache_key = (atlas, size, chest_type)
        cached = self._closed_texture_cache.get(cache_key)
        if cached is not None:
            return cached

        required_width = 56 if chest_type == "single" else 88
        if atlas.get_width() < required_width or atlas.get_height() < 43:
            texture = pygame.transform.scale(atlas, (size, size))
        else:
            def front(rect):
                face = atlas.subsurface(rect).copy()
                return pygame.transform.flip(face, True, True)

            if chest_type == "single":
                native = pygame.Surface((16, 16), pygame.SRCALPHA)
                # Model-space y grows upward here: the bottom occupies y=0..10,
                # the lid y=9..14, and the lock y=7..11. Draw bottom first so the
                # overlapping lid and lock remain the front-most parts.
                native.blit(front(self._BOTTOM_UV), (1, 6))
                native.blit(front(self._LID_UV), (1, 2))
                native.blit(front(self._LOCK_UV), (7, 5))
            else:
                double_native = pygame.Surface((32, 16), pygame.SRCALPHA)
                double_native.blit(front(self._DOUBLE_BOTTOM_UV), (1, 6))
                double_native.blit(front(self._DOUBLE_LID_UV), (1, 2))
                double_native.blit(front(self._DOUBLE_LOCK_UV), (15, 5))
                source_x = 0 if chest_type == "left" else 16
                native = double_native.subsurface((source_x, 0, 16, 16)).copy()
            texture = pygame.transform.scale(native, (size, size))

        self._closed_texture_cache[cache_key] = texture
        if len(self._closed_texture_cache) > 16:
            self._closed_texture_cache.pop(next(iter(self._closed_texture_cache)))
        return texture

    def _state_packet(self, packet_class="ChestUpdate") -> dict:
        from src.server.inventory import serialize_inventory

        menu_inventory = self._menu_inventory()
        packet = {
            "__class__": packet_class,
            "container": self.container_id,
            "slots": serialize_inventory(menu_inventory),
            "rows": len(menu_inventory) // 9,
        }
        if self.location is not None:
            packet.update(
                x=int(self.location.x),
                y=int(self.location.y),
                z=int(self.location.z),
            )
        return packet

    def sync_viewers(self, packet_class="ChestUpdate") -> None:
        if self.location is None:
            return
        server = getattr(self.location.world, "server", None)
        if server is None:
            return
        packet = self._state_packet(packet_class)
        for player in tuple(self._all_viewers()):
            container = player.get_inventory_container(self.container_id)
            contains_chest = getattr(container, "contains_chest", None)
            if container is not self.inventory and not (
                callable(contains_chest) and contains_chest(self)
            ):
                for chest in self._ordered_chests():
                    chest._viewers.discard(player)
                continue
            server.send_client_socket(player, packet, "Forward")

    def _is_blocked(self) -> bool:
        for chest in self._ordered_chests():
            above = chest.location.world.get_block(chest.location.add(0, 1, 0))
            if getattr(above, "redstone_conducting", False) and not getattr(
                above, "replaceable", False
            ):
                return True
        return False

    def open_for(self, player) -> bool:
        if self.location is None or self._is_blocked():
            return False
        container_id = self.container_id
        for open_id, container in tuple(player.open_inventory_containers.items()):
            if open_id == container_id:
                continue
            owner = getattr(
                container,
                "owner_block",
                getattr(container, "furnace", None),
            )
            if owner is not None and owner is not self:
                owner.close_for(player)
        was_closed = not self._all_viewers()
        player.register_inventory_container(container_id, self._menu_inventory())
        for chest in self._ordered_chests():
            chest._viewers.add(player)
        server = getattr(self.location.world, "server", None)
        if server is not None:
            broadcast_sound = getattr(server, "broadcast_sound", None)
            if was_closed and callable(broadcast_sound):
                broadcast_sound(
                    "random.chestopen",
                    self.location.x + 0.5,
                    self.location.y + 0.5,
                    self.location.z,
                )
            server.send_client_socket(
                player,
                self._state_packet("ChestOpen"),
                "Forward",
            )
        return True

    def close_for(self, player) -> None:
        container_id = self.container_id
        chests = self._ordered_chests()
        was_viewing = any(player in chest._viewers for chest in chests)
        container = player.open_inventory_containers.get(container_id)
        contains_chest = getattr(container, "contains_chest", None)
        if container in tuple(chest.inventory for chest in chests) or (
            callable(contains_chest) and contains_chest(self)
        ):
            player.unregister_inventory_container(container_id)
        for chest in chests:
            chest._viewers.discard(player)
        if was_viewing and not self._all_viewers() and self.location is not None:
            server = getattr(self.location.world, "server", None)
            broadcast_sound = getattr(server, "broadcast_sound", None)
            if callable(broadcast_sound):
                broadcast_sound(
                    "random.chestclosed",
                    self.location.x + 0.5,
                    self.location.y + 0.5,
                    self.location.z,
                )

    def close_all_viewers(self) -> None:
        container_id = self.container_id
        for player in tuple(self._all_viewers()):
            self.close_for(player)
            server = getattr(getattr(self.location, "world", None), "server", None)
            if server is not None:
                server.send_client_socket(
                    player,
                    {
                        "__class__": self.closed_packet_class,
                        "container": container_id,
                    },
                    "Forward",
                )

    def on_right_click(self, player) -> bool:
        return self.open_for(player)

    def on_inventory_changed(self) -> None:
        if self.location is None:
            return
        world = self.location.world
        chests = self._ordered_chests()
        for chest in chests:
            rx = int(chest.location.x) // 16
            world.mark_chunk_dirty(rx)
            world.invalidate_chunk_packet(rx)
        chests[0].sync_viewers()

    def on_unload(self) -> None:
        self.close_all_viewers()
        self._unlink_pair()

    def on_break(self):
        if self.location is None:
            return
        from src.server.entities.item import Item
        from src.server.item_class import EmptyItemStack

        world = self.location.world
        self.close_all_viewers()
        self._unlink_pair()
        # ClientWorld performs a predicted local break using the same block
        # class. It only needs the partner's visual state updated; inventory
        # drops and persistence remain server-authoritative.
        if getattr(world, "server", None) is None:
            return
        for index in range(len(self.inventory)):
            stack = self.inventory[index]
            if stack.is_empty():
                continue
            world.spawn_entity(
                Item(
                    self.location.x + 0.5,
                    self.location.y + 0.45,
                    world,
                    stack,
                    int(self.location.z),
                )
            )
            self.inventory[index] = EmptyItemStack()

@register_block
class LADDER(Block):
    block_id = "ladder"
    name = "tile.ladder.name"
    _texture_path = "blocks.ladder"
    solid = False
    collision_box = EMPTY
    climbable = True
    suffocating = False
    redstone_conducting = False
    light_attenuation = 1


def get_block_by_id(block_id: str) -> Block:
    """Return a new block instance registered under ``block_id``."""
    cls = _BLOCK_REGISTRY.get(str(block_id))
    if cls is not None:
        return cls()
    logging.error(f"Unknown block ID: {block_id}")
    return DIRT()


def has_block_id(block_id: str) -> bool:
    return str(block_id) in _BLOCK_REGISTRY


def get_registered_block_ids() -> tuple[str, ...]:
    """Return every currently registered block id in definition order."""
    return tuple(_BLOCK_REGISTRY)
