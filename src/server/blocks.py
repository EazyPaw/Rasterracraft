# Commented and arranged by ChatGPT
import os
import random
import src.server.materials as materials

from src.server.biome import get_biome_by_id, get_precipitation_type

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

    def accepts_item_use(self, material) -> bool:
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


class STONE(Block):
    block_id = "stone"
    name = "tile.stone.stone.name"
    _texture_path = "blocks.stone"
    blast_resistance = 6.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    drops = (BlockDrop(COBBLESTONE_ITEM),)


class COBBLESTONE(Block):
    block_id = "cobblestone"
    name = "tile.stonebrick.name"
    _texture_path = "blocks.cobblestone"
    blast_resistance = 6.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True


class OBSIDIAN(Block):
    block_id = "obsidian"
    name = "tile.obsidian.name"
    _texture_path = "blocks.obsidian"
    hardness = 50.0
    blast_resistance = 1200.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "diamond"


class GRANITE(Block):
    block_id = "granite"
    name = "tile.stone.granite.name"
    _texture_path = "blocks.stone_granite"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


class DIORITE(Block):
    block_id = "diorite"
    name = "tile.stone.diorite.name"
    _texture_path = "blocks.stone_diorite"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


class ANDESITE(Block):
    block_id = "andesite"
    name = "tile.stone.andesite.name"
    _texture_path = "blocks.stone_andesite"
    preferred_tool = "pickaxe"
    requires_correct_tool = True


class BEDROCK(Block):
    block_id = "bedrock"
    name = "tile.bedrock.name"
    _texture_path = "blocks.bedrock"
    breakable = False
    hardness = -1
    blast_resistance = 3_600_000.0


class DIRT(TillableBlockMixin, Block):
    block_id = "dirt"
    name = "tile.dirt.name"
    _texture_path = "blocks.dirt"
    break_sound = "dig.gravel"
    hardness = 0.5
    preferred_tool = "shovel"


class COARSE_DIRT(Block):
    block_id = "coarse_dirt"
    name = "tile.dirt.coarse.name"
    _texture_path = "blocks.coarse_dirt"
    break_sound = "dig.gravel"
    hardness = 0.5
    preferred_tool = "shovel"


class PODZOL(Block):
    block_id = "podzol"
    name = "tile.dirt.podzol.name"
    _texture_path = "blocks.dirt_podzol_side"
    break_sound = "dig.gravel"
    hardness = 0.5
    preferred_tool = "shovel"
    Tags = [BlockTag.GRASS_BLOCKS]


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


class CARROTS(RootCrop):
    block_id = "carrots"
    _texture_path = "blocks.carrots"
    name = "tile.carrots.name"
    produce_material_type = CARROT_ITEM


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


class TALL_GRASS(DoublePlantBottomMixin, SeedDroppingGrass, GrassStain):
    block_id = "tall_grass"
    name = "tile.doublePlant.grass.name"
    _texture_path = "blocks.double_plant_grass_bottom"
    top_block_id = "tall_grass_top"


class TALL_GRASS_TOP(DoublePlantTopMixin, SeedDroppingGrass, GrassStain):
    block_id = "tall_grass_top"
    name = "tile.doublePlant.grass.name"
    _texture_path = "blocks.double_plant_grass_top"
    bottom_block_id = "tall_grass"


class LARGE_FERN(DoublePlantBottomMixin, SeedDroppingGrass, GrassStain):
    block_id = "large_fern"
    name = "tile.doublePlant.fern.name"
    _texture_path = "blocks.double_plant_fern_bottom"
    top_block_id = "large_fern_top"


class LARGE_FERN_TOP(DoublePlantTopMixin, SeedDroppingGrass, GrassStain):
    block_id = "large_fern_top"
    name = "tile.doublePlant.fern.name"
    _texture_path = "blocks.double_plant_fern_top"
    bottom_block_id = "large_fern"


class SUNFLOWER(DoublePlantBottomMixin, Plant):
    block_id = "sunflower"
    name = "tile.doublePlant.sunflower.name"
    _texture_path = "blocks.double_plant_sunflower_bottom"
    top_block_id = "sunflower_top"


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


class ROSE_BUSH(DoublePlantBottomMixin, Plant):
    block_id = "rose_bush"
    name = "tile.doublePlant.rose.name"
    _texture_path = "blocks.double_plant_rose_bottom"
    top_block_id = "rose_bush_top"


class ROSE_BUSH_TOP(DoublePlantTopMixin, Plant):
    block_id = "rose_bush_top"
    name = "tile.doublePlant.rose.name"
    _texture_path = "blocks.double_plant_rose_top"
    bottom_block_id = "rose_bush"


class PEONY(DoublePlantBottomMixin, Plant):
    block_id = "peony"
    name = "tile.doublePlant.paeonia.name"
    _texture_path = "blocks.double_plant_paeonia_bottom"
    top_block_id = "peony_top"


class PEONY_TOP(DoublePlantTopMixin, Plant):
    block_id = "peony_top"
    name = "tile.doublePlant.paeonia.name"
    _texture_path = "blocks.double_plant_paeonia_top"
    bottom_block_id = "peony"


class LILAC(DoublePlantBottomMixin, Plant):
    block_id = "lilac"
    name = "tile.doublePlant.syringa.name"
    _texture_path = "blocks.double_plant_syringa_bottom"
    top_block_id = "lilac_top"


class LILAC_TOP(DoublePlantTopMixin, Plant):
    block_id = "lilac_top"
    name = "tile.doublePlant.syringa.name"
    _texture_path = "blocks.double_plant_syringa_top"
    bottom_block_id = "lilac"


class OAK_PLANK(Block):
    block_id = "oak_planks"
    name = "tile.wood.oak.name"
    _texture_path = "blocks.planks_oak"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class BIRCH_PLANK(Block):
    block_id = "birch_planks"
    name = "tile.wood.birch.name"
    _texture_path = "blocks.planks_birch"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class SPRUCE_PLANK(Block):
    block_id = "spruce_planks"
    name = "tile.wood.spruce.name"
    _texture_path = "blocks.planks_spruce"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class JUNGLE_PLANK(Block):
    block_id = "jungle_planks"
    name = "tile.wood.jungle.name"
    _texture_path = "blocks.planks_jungle"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class ACACIA_PLANK(Block):
    block_id = "acacia_planks"
    name = "tile.wood.acacia.name"
    _texture_path = "blocks.planks_acacia"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class DARK_OAK_PLANK(Block):
    block_id = "dark_oak_planks"
    name = "tile.wood.big_oak.name"
    _texture_path = "blocks.planks_big_oak"
    break_sound = "dig.wood"
    hardness = 2.0
    preferred_tool = "axe"


class CRAFTING_TABLE(Block):
    block_id = "crafting_table"
    name = "tile.workbench.name"
    _texture_path = "blocks.crafting_table_front"
    break_sound = "dig.wood"
    hardness = 2.5
    preferred_tool = "axe"


class FurnaceInventory(Inventory):
    def __init__(self, furnace):
        super().__init__(3)
        self.furnace = furnace

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
            owner = getattr(container, "furnace", None)
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


class GLOWSTONE(Block):
    block_id = "glowstone"
    name = "tile.lightgem.name"
    _texture_path = "blocks.glowstone"
    light_source = 15
    light_attenuation = 0
    break_sound = "dig.glass"
    hardness = 0.3
    preferred_tool = "pickaxe"


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


class POPPY(Plant):
    block_id = "poppy"
    name = "tile.flower2.poppy.name"
    _texture_path = "blocks.flower_rose"


class DANDELION(Plant):
    block_id = "dandelion"
    name = "tile.flower1.dandelion.name"
    _texture_path = "blocks.flower_dandelion"


class OAK_LEAVES(Leaves):
    block_id = "oak_leaves"
    name = "tile.leaves.oak.name"
    _texture_path = "blocks.leaves_oak"


class OAK_LOG(Log):
    block_id = "oak_log"
    name = "tile.log.oak.name"
    _texture_path = "blocks.log_oak"


class BIRCH_LEAVES(Leaves):
    block_id = "birch_leaves"
    name = "tile.leaves.birch.name"
    _texture_path = "blocks.leaves_birch"


class BIRCH_LOG(Log):
    block_id = "birch_log"
    name = "tile.log.birch.name"
    _texture_path = "blocks.log_birch"


class SPRUCE_LEAVES(Leaves):
    block_id = "spruce_leaves"
    name = "tile.leaves.spruce.name"
    _texture_path = "blocks.leaves_spruce"


class SPRUCE_LOG(Log):
    block_id = "spruce_log"
    name = "tile.log.spruce.name"
    _texture_path = "blocks.log_spruce"


class JUNGLE_LEAVES(Leaves):
    block_id = "jungle_leaves"
    name = "tile.leaves.jungle.name"
    _texture_path = "blocks.leaves_jungle"


class JUNGLE_LOG(Log):
    block_id = "jungle_log"
    name = "tile.log.jungle.name"
    _texture_path = "blocks.log_jungle"


class ACACIA_LEAVES(Leaves):
    block_id = "acacia_leaves"
    name = "tile.leaves.acacia.name"
    _texture_path = "blocks.leaves_acacia"


class ACACIA_LOG(Log):
    block_id = "acacia_log"
    name = "tile.log.acacia.name"
    _texture_path = "blocks.log_acacia"


class DARK_OAK_LEAVES(Leaves):
    block_id = "dark_oak_leaves"
    name = "tile.leaves.big_oak.name"
    _texture_path = "blocks.leaves_big_oak"


class DARK_OAK_LOG(Log):
    block_id = "dark_oak_log"
    name = "tile.log.big_oak.name"
    _texture_path = "blocks.log_big_oak"


class SAND(GravityBlock):
    block_id = "sand"
    name = "tile.sand.name"
    _texture_path = "blocks.sand"
    break_sound = "dig.sand"
    hardness = 0.5
    preferred_tool = "shovel"


class RED_SAND(GravityBlock):
    block_id = "red_sand"
    name = "tile.sand.red.name"
    _texture_path = "blocks.red_sand"
    break_sound = "dig.sand"
    hardness = 0.5
    preferred_tool = "shovel"


class SANDSTONE(Block):
    block_id = "sandstone"
    name = "tile.sandStone.name"
    _texture_path = "blocks.sandstone_normal"
    hardness = 0.8
    preferred_tool = "pickaxe"
    requires_correct_tool = True


class RED_SANDSTONE(Block):
    block_id = "red_sandstone"
    name = "tile.redSandStone.name"
    _texture_path = "blocks.red_sandstone_normal"
    hardness = 0.8
    preferred_tool = "pickaxe"
    requires_correct_tool = True


class GRAVEL(GravityBlock):
    block_id = "gravel"
    name = "tile.gravel.name"
    _texture_path = "blocks.gravel"
    break_sound = "dig.gravel"
    hardness = 0.6
    preferred_tool = "shovel"


class CLAY(Block):
    block_id = "clay"
    name = "tile.clay.name"
    _texture_path = "blocks.clay"
    break_sound = "dig.gravel"
    hardness = 0.6
    preferred_tool = "shovel"


class HARDENED_CLAY(Block):
    block_id = "hardened_clay"
    name = "tile.clayHardened.name"
    _texture_path = "blocks.hardened_clay"
    hardness = 1.25
    preferred_tool = "pickaxe"
    requires_correct_tool = True


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


class SNOW_BLOCK(Block):
    block_id = "snow_block"
    name = "tile.snow.name"
    _texture_path = "blocks.snow"
    break_sound = "dig.snow"
    hardness = 0.2
    preferred_tool = "shovel"


class ICE(Block):
    block_id = "ice"
    name = "tile.ice.name"
    _texture_path = "blocks.ice"
    break_sound = "dig.glass"
    friction = 0.98
    hardness = 0.5
    preferred_tool = "pickaxe"


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


class FERN(SeedDroppingGrass, GrassStain):
    block_id = "fern"
    name = "tile.tallgrass.fern.name"
    _texture_path = "blocks.fern"


class DEAD_BUSH(Plant):
    block_id = "dead_bush"
    name = "tile.deadbush.name"
    _texture_path = "blocks.deadbush"


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


class BROWN_MUSHROOM(Plant):
    block_id = "brown_mushroom"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_brown"

    def on_update(self):
        pass


class RED_MUSHROOM(Plant):
    block_id = "red_mushroom"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_red"

    def on_update(self):
        pass


class VINE(GrassStain):
    block_id = "vine"
    name = "tile.vine.name"
    _texture_path = "blocks.vine"
    light_attenuation = 1

    def on_update(self):

        pass


class COAL_ORE(Block):
    block_id = "coal_ore"
    name = "tile.oreCoal.name"
    _texture_path = "blocks.coal_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    drops = (BlockDrop(materials.COAL),)


class IRON_ORE(Block):
    block_id = "iron_ore"
    name = "tile.oreIron.name"
    _texture_path = "blocks.iron_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "stone"


class GOLD_ORE(Block):
    block_id = "gold_ore"
    name = "tile.oreGold.name"
    _texture_path = "blocks.gold_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


class DIAMOND_ORE(Block):
    block_id = "diamond_ore"
    name = "tile.oreDiamond.name"
    _texture_path = "blocks.diamond_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"
    drops = (BlockDrop(materials.DIAMOND),)


class EMERALD_ORE(Block):
    block_id = "emerald_ore"
    name = "tile.oreEmerald.name"
    _texture_path = "blocks.emerald_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


class LAPIS_ORE(Block):
    block_id = "lapis_ore"
    name = "tile.oreLapis.name"
    _texture_path = "blocks.lapis_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "stone"


class REDSTONE_ORE(Block):
    block_id = "redstone_ore"
    name = "tile.oreRedstone.name"
    _texture_path = "blocks.redstone_ore"
    hardness = 3.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


class BLUE_ORCHID(Plant):
    block_id = "blue_orchid"
    name = "tile.flower2.blueOrchid.name"
    _texture_path = "blocks.flower_blue_orchid"


class ALLIUM(Plant):
    block_id = "allium"
    name = "tile.flower2.allium.name"
    _texture_path = "blocks.flower_allium"


class AZURE_BLUET(Plant):
    block_id = "azure_bluet"
    name = "tile.flower2.houstonia.name"
    _texture_path = "blocks.flower_houstonia"


class OXEYE_DAISY(Plant):
    block_id = "oxeye_daisy"
    name = "tile.flower2.oxeyeDaisy.name"
    _texture_path = "blocks.flower_oxeye_daisy"


class DIAMOND_BLOCK(Block):
    block_id = "diamond_block"
    name = "tile.blockDiamond.name"
    _texture_path = "blocks.diamond_block"
    hardness = 5.0
    preferred_tool = "pickaxe"
    requires_correct_tool = True
    required_tool_tier = "iron"


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


class OAK_SLAB(SLABS):
    block_id = "oak_slab"
    name = "tile.woodSlab.name"
    _texture_path = "blocks.planks_oak"


class TNT(Block):
    block_id = "tnt"
    name = "tile.tnt.name"
    _texture_path = "blocks.tnt_side"
    hardness = 0.0
    blast_resistance = 0.0
    break_sound = "dig.grass"

    def accepts_item_use(self, material) -> bool:
        return bool(getattr(material, "ignites_blocks", False))

    def prime(self, *, fuse: int = 80, igniter=None) -> bool:
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
        if server is not None:
            server.broadcast_sound("game.tnt.primed", x + 0.5, y + 0.5, z)
        return True

    def on_use(self, player, material) -> bool:
        if not getattr(material, "ignites_blocks", False):
            return False
        return self.prime(fuse=80, igniter=player)

    def on_exploded(self, power: float, source=None) -> bool:

        self.prime(fuse=random.randint(10, 30), igniter=source)
        return False


class MYCELIUM(Block):
    block_id = "mycelium"
    name = "tile.mycel.name"
    _texture_path = "blocks.mycelium_side"


class MUSHROOM_STEM(Block):
    block_id = "mushroom_stem"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_block_skin_stem"


class RED_MUSHROOM_BLOCK(Block):
    block_id = "red_mushroom_block"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_block_skin_red"


class BROWN_MUSHROOM_BLOCK(Block):
    block_id = "brown_mushroom_block"
    name = "tile.mushroom.name"
    _texture_path = "blocks.mushroom_block_skin_brown"


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


# ---- block_id → Block 子类 缓存 ----
_BLOCK_REGISTRY: dict[str, type] = None  # None = 尚未构建


def _build_block_id_cache() -> dict[str, type]:
    """遍历 Block 的所有子类，构建 block_id → 子类 的映射（仅执行一次）。"""
    cache: dict[str, type] = {}

    def collect(cls):
        for subclass in cls.__subclasses__():
            bid = getattr(subclass, "block_id", None)
            if bid is not None:
                cache[bid] = subclass
            collect(subclass)

    collect(Block)
    return cache


def get_block_by_id(block_id: str) -> Block:
    """
    根据 block_id 获取方块实例。

    首次调用时自动遍历 Block 子类树构建缓存，后续调用为 O(1) 查表。
    """
    global _BLOCK_REGISTRY
    if _BLOCK_REGISTRY is None:
        _BLOCK_REGISTRY = _build_block_id_cache()

    cls = _BLOCK_REGISTRY.get(block_id)
    if cls is not None:
        return cls()
    logging.error(f"Unknown block ID: {block_id}")
    return DIRT()


def has_block_id(block_id: str) -> bool:
    global _BLOCK_REGISTRY
    if _BLOCK_REGISTRY is None:
        _BLOCK_REGISTRY = _build_block_id_cache()
    return str(block_id) in _BLOCK_REGISTRY


def get_registered_block_ids() -> tuple[str, ...]:
    """Return every currently registered block id in definition order."""
    global _BLOCK_REGISTRY
    if _BLOCK_REGISTRY is None:
        _BLOCK_REGISTRY = _build_block_id_cache()
    return tuple(_BLOCK_REGISTRY)
