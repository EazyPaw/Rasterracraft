import os

import logging

from resources.server.biome import get_biome_by_id

if os.environ.get('PYCRAFT_CLIENT') == '1':
    pass

from resources.server.block_class import *
from resources.server.tags import BlockTag
from resources.server.utils import client_method


class AIR(Block):
    block_id = 'air'
    name = 'tile.air.name'
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

    def on_right_click(self):
        pass

class STONE(Block):
    block_id = 'stone'
    name = 'tile.stone.stone.name'
    _texture_path = 'blocks.stone'
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class COBBLESTONE(Block):
    block_id = 'cobblestone'
    name = 'tile.stonebrick.name'
    _texture_path = 'blocks.cobblestone'
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class OBSIDIAN(Block):
    block_id = 'obsidian'
    name = 'tile.obsidian.name'
    _texture_path = 'blocks.obsidian'
    hardness = 50.0
    blast_resistance = 1200.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'diamond'

class GRANITE(Block):
    block_id = 'granite'
    name = 'tile.stone.granite.name'
    _texture_path = 'blocks.stone_granite'
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class DIORITE(Block):
    block_id = 'diorite'
    name = 'tile.stone.diorite.name'
    _texture_path = 'blocks.stone_diorite'
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class ANDESITE(Block):
    block_id = 'andesite'
    name = 'tile.stone.andesite.name'
    _texture_path = 'blocks.stone_andesite'
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class BEDROCK(Block):
    block_id = 'bedrock'
    name = 'tile.bedrock.name'
    _texture_path = 'blocks.bedrock'
    breakable = False
    hardness = -1

class DIRT(Block):
    block_id = 'dirt'
    name = 'tile.dirt.name'
    _texture_path = 'blocks.dirt'
    break_sound = 'dig.gravel'
    hardness = 0.5
    preferred_tool = 'shovel'

class COARSE_DIRT(Block):
    block_id = 'coarse_dirt'
    name = 'tile.dirt.coarse.name'
    _texture_path = 'blocks.coarse_dirt'
    break_sound = 'dig.gravel'
    hardness = 0.5
    preferred_tool = 'shovel'

class PODZOL(Block):
    block_id = 'podzol'
    name = 'tile.dirt.podzol.name'
    _texture_path = 'blocks.dirt_podzol_side'
    break_sound = 'dig.gravel'
    hardness = 0.5
    preferred_tool = 'shovel'
    Tags = [BlockTag.GRASS_BLOCKS]

class GRASS_BLOCK(Block):
    block_id = 'grass_block'
    name = 'tile.grass.name'
    light_attenuation = 5
    break_sound = 'dig.gravel'
    hardness = 0.6
    preferred_tool = 'shovel'
    _side_texture_cache = {}  # 缓存不同尺寸的侧面纹理
    Tags = [BlockTag.GRASS_BLOCKS]

    def __init__(self, snowed = False):
        super().__init__()
        self.snowed = snowed

    @client_method
    def get_texture(self, size, client: 'Client'):
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
        overlay_raw = client.resources_manager.get_texture_img("blocks.grass_side_overlay")

        if base_side is None or overlay_raw is None:
            # 如果缺少任一材质，返回默认纹理或基础纹理
            return base_side or overlay_raw

        # 2. 缩放至目标尺寸
        base_side_scaled = pygame.transform.scale(base_side, (size, size))
        overlay_scaled = pygame.transform.scale(overlay_raw, (size, size))

        # 3. 染色 overlay (使用 RGB 元组 (30, 50, 70))
        # 注意：grass_side_overlay 通常是灰度图或带有透明度变化的图
        stained_overlay = client.resources_manager.biome_stain(overlay_scaled, self.location).convert_alpha()

        # 4. 组合图层
        # 使用 stain.py 中的 overlay_surfaces 逻辑，或者直接使用 pygame 的 blit
        final_texture = base_side_scaled.convert_alpha()
        final_texture.blit(stained_overlay, (0, 0))

        # 5. 存入缓存
        self._side_texture_cache[cache_key] = final_texture.convert_alpha()

        return final_texture

    def on_update(self):
        self.snowed = isinstance(self.location.world.get_block(self.location.add(0, 1, 0)), SNOW)


class SHORT_GRASS(GrassStain):
    block_id = 'short_grass'
    name = 'tile.tallgrass.grass.name'
    _texture_path = 'blocks.tallgrass'
    hardness = 0.0


class DoublePlantBottomMixin:
    top_block_id = None

    def _remove_double_plant_neighbor(self, location):
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


class TALL_GRASS(DoublePlantBottomMixin, GrassStain):
    block_id = 'tall_grass'
    name = 'tile.doublePlant.grass.name'
    _texture_path = 'blocks.double_plant_grass_bottom'
    top_block_id = 'tall_grass_top'


class TALL_GRASS_TOP(DoublePlantTopMixin, GrassStain):
    block_id = 'tall_grass_top'
    name = 'tile.doublePlant.grass.name'
    _texture_path = 'blocks.double_plant_grass_top'
    bottom_block_id = 'tall_grass'


class LARGE_FERN(DoublePlantBottomMixin, GrassStain):
    block_id = 'large_fern'
    name = 'tile.doublePlant.fern.name'
    _texture_path = 'blocks.double_plant_fern_bottom'
    top_block_id = 'large_fern_top'


class LARGE_FERN_TOP(DoublePlantTopMixin, GrassStain):
    block_id = 'large_fern_top'
    name = 'tile.doublePlant.fern.name'
    _texture_path = 'blocks.double_plant_fern_top'
    bottom_block_id = 'large_fern'


class SUNFLOWER(DoublePlantBottomMixin, Plant):
    block_id = 'sunflower'
    name = 'tile.doublePlant.sunflower.name'
    _texture_path = 'blocks.double_plant_sunflower_bottom'
    top_block_id = 'sunflower_top'


class SUNFLOWER_TOP(DoublePlantTopMixin, Plant):
    block_id = 'sunflower_top'
    name = 'tile.doublePlant.sunflower.name'
    _texture_path = 'blocks.double_plant_sunflower_top'
    _front_texture_path = 'blocks.double_plant_sunflower_front'
    bottom_block_id = 'sunflower'
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
            cls.has_transparent_pixels = client.resources_manager.has_transparent_pixels(final)
        self._texture_cache[cache_key] = final
        return final


class ROSE_BUSH(DoublePlantBottomMixin, Plant):
    block_id = 'rose_bush'
    name = 'tile.doublePlant.rose.name'
    _texture_path = 'blocks.double_plant_rose_bottom'
    top_block_id = 'rose_bush_top'


class ROSE_BUSH_TOP(DoublePlantTopMixin, Plant):
    block_id = 'rose_bush_top'
    name = 'tile.doublePlant.rose.name'
    _texture_path = 'blocks.double_plant_rose_top'
    bottom_block_id = 'rose_bush'


class PEONY(DoublePlantBottomMixin, Plant):
    block_id = 'peony'
    name = 'tile.doublePlant.paeonia.name'
    _texture_path = 'blocks.double_plant_paeonia_bottom'
    top_block_id = 'peony_top'


class PEONY_TOP(DoublePlantTopMixin, Plant):
    block_id = 'peony_top'
    name = 'tile.doublePlant.paeonia.name'
    _texture_path = 'blocks.double_plant_paeonia_top'
    bottom_block_id = 'peony'


class LILAC(DoublePlantBottomMixin, Plant):
    block_id = 'lilac'
    name = 'tile.doublePlant.syringa.name'
    _texture_path = 'blocks.double_plant_syringa_bottom'
    top_block_id = 'lilac_top'


class LILAC_TOP(DoublePlantTopMixin, Plant):
    block_id = 'lilac_top'
    name = 'tile.doublePlant.syringa.name'
    _texture_path = 'blocks.double_plant_syringa_top'
    bottom_block_id = 'lilac'

class OAK_PLANK(Block):
    block_id = 'oak_plank'
    name = 'tile.wood.oak.name'
    _texture_path = 'blocks.planks_oak'
    break_sound = 'dig.wood'
    hardness = 2.0
    preferred_tool = 'axe'

class BIRCH_PLANK(Block):
    block_id = 'birch_plank'
    name = 'tile.wood.birch.name'
    _texture_path = 'blocks.planks_birch'
    break_sound = 'dig.wood'
    hardness = 2.0
    preferred_tool = 'axe'

class SPRUCE_PLANK(Block):
    block_id = 'spruce_plank'
    name = 'tile.wood.spruce.name'
    _texture_path = 'blocks.planks_spruce'
    break_sound = 'dig.wood'
    hardness = 2.0
    preferred_tool = 'axe'

class JUNGLE_PLANK(Block):
    block_id = 'jungle_plank'
    name = 'tile.wood.jungle.name'
    _texture_path = 'blocks.planks_jungle'
    break_sound = 'dig.wood'
    hardness = 2.0
    preferred_tool = 'axe'

class ACACIA_PLANK(Block):
    block_id = 'acacia_plank'
    name = 'tile.wood.acacia.name'
    _texture_path = 'blocks.planks_acacia'
    break_sound = 'dig.wood'
    hardness = 2.0
    preferred_tool = 'axe'

class DARK_OAK_PLANK(Block):
    block_id = 'dark_oak_plank'
    name = 'tile.wood.big_oak.name'
    _texture_path = 'blocks.planks_big_oak'
    break_sound = 'dig.wood'
    hardness = 2.0
    preferred_tool = 'axe'


class CRAFTING_TABLE(Block):
    block_id = 'crafting_table'
    name = 'tile.workbench.name'
    _texture_path = 'blocks.crafting_table_front'
    break_sound = 'dig.wood'
    hardness = 2.5
    preferred_tool = 'axe'

class GLOWSTONE(Block):
    block_id = 'glowstone'
    name = 'tile.lightgem.name'
    _texture_path = 'blocks.glowstone'
    light_source = 15
    light_attenuation = 0
    break_sound = 'dig.glass'
    hardness = 0.3
    preferred_tool = 'pickaxe'

class POPPY(Plant):
    block_id = 'poppy'
    name = 'tile.flower2.poppy.name'
    _texture_path = 'blocks.flower_rose'

class DANDELION(Plant):
    block_id = 'dandelion'
    name = 'tile.flower1.dandelion.name'
    _texture_path = 'blocks.flower_dandelion'

class OAK_LEAVES(Leaves):
    block_id = 'oak_leaves'
    name = 'tile.leaves.oak.name'
    _texture_path = 'blocks.leaves_oak'

class OAK_LOG(Log):
    block_id = 'oak_log'
    name = 'tile.log.oak.name'
    _texture_path = 'blocks.log_oak'

class BIRCH_LEAVES(Leaves):
    block_id = 'birch_leaves'
    name = 'tile.leaves.birch.name'
    _texture_path = 'blocks.leaves_birch'

class BIRCH_LOG(Log):
    block_id = 'birch_log'
    name = 'tile.log.birch.name'
    _texture_path = 'blocks.log_birch'

class SPRUCE_LEAVES(Leaves):
    block_id = 'spruce_leaves'
    name = 'tile.leaves.spruce.name'
    _texture_path = 'blocks.leaves_spruce'

class SPRUCE_LOG(Log):
    block_id = 'spruce_log'
    name = 'tile.log.spruce.name'
    _texture_path = 'blocks.log_spruce'

class JUNGLE_LEAVES(Leaves):
    block_id = 'jungle_leaves'
    name = 'tile.leaves.jungle.name'
    _texture_path = 'blocks.leaves_jungle'

class JUNGLE_LOG(Log):
    block_id = 'jungle_log'
    name = 'tile.log.jungle.name'
    _texture_path = 'blocks.log_jungle'

class ACACIA_LEAVES(Leaves):
    block_id = 'acacia_leaves'
    name = 'tile.leaves.acacia.name'
    _texture_path = 'blocks.leaves_acacia'

class ACACIA_LOG(Log):
    block_id = 'acacia_log'
    name = 'tile.log.acacia.name'
    _texture_path = 'blocks.log_acacia'

class DARK_OAK_LEAVES(Leaves):
    block_id = 'dark_oak_leaves'
    name = 'tile.leaves.big_oak.name'
    _texture_path = 'blocks.leaves_big_oak'

class DARK_OAK_LOG(Log):
    block_id = 'dark_oak_log'
    name = 'tile.log.big_oak.name'
    _texture_path = 'blocks.log_big_oak'

class SAND(GravityBlock):
    block_id = 'sand'
    name = 'tile.sand.name'
    _texture_path = 'blocks.sand'
    break_sound = "dig.sand"
    hardness = 0.5
    preferred_tool = 'shovel'

class RED_SAND(GravityBlock):
    block_id = 'red_sand'
    name = 'tile.sand.red.name'
    _texture_path = 'blocks.red_sand'
    break_sound = "dig.sand"
    hardness = 0.5
    preferred_tool = 'shovel'

class SANDSTONE(Block):
    block_id = 'sandstone'
    name = 'tile.sandStone.name'
    _texture_path = 'blocks.sandstone_normal'
    hardness = 0.8
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class RED_SANDSTONE(Block):
    block_id = 'red_sandstone'
    name = 'tile.redSandStone.name'
    _texture_path = 'blocks.red_sandstone_normal'
    hardness = 0.8
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class GRAVEL(GravityBlock):
    block_id = 'gravel'
    name = 'tile.gravel.name'
    _texture_path = 'blocks.gravel'
    break_sound = 'dig.gravel'
    hardness = 0.6
    preferred_tool = 'shovel'

class CLAY(Block):
    block_id = 'clay'
    name = 'tile.clay.name'
    _texture_path = 'blocks.clay'
    break_sound = 'dig.gravel'
    hardness = 0.6
    preferred_tool = 'shovel'

class HARDENED_CLAY(Block):
    block_id = 'hardened_clay'
    name = 'tile.clayHardened.name'
    _texture_path = 'blocks.hardened_clay'
    hardness = 1.25
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class SNOW(BottomSupport):
    block_id = 'snow'
    name = 'tile.snow.name'
    _texture_path = 'blocks.snow'
    break_sound = 'dig.snow'
    solid = False
    collision_box = EMPTY
    light_attenuation = 1
    has_transparent_pixels = True
    hardness = 0.1
    preferred_tool = 'shovel'

    _texture_cache = {}

    def __init__(self, layer = 1):
        super().__init__()
        if layer > 8:
            raise Exception('layer > 8')
        self.layer = max(1, int(layer))

    def get_collision_box(self):
        # Snow layers occupy one to eight sixteenths of a block.  Keep this
        # instance-dependent so NBT/state changes are reflected immediately.
        return BlockCollisionBox.from_box(0, 0, 1, self.layer / 8)

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
    block_id = 'snow_block'
    name = 'tile.snow.name'
    _texture_path = 'blocks.snow'
    break_sound = 'dig.snow'
    hardness = 0.2
    preferred_tool = 'shovel'

class ICE(Block):
    block_id = 'ice'
    name = 'tile.ice.name'
    _texture_path = 'blocks.ice'
    break_sound = 'dig.glass'
    friction = 0.98
    hardness = 0.5
    preferred_tool = 'pickaxe'

class WATER(FluidBlock):
    block_id = 'water'
    name = 'tile.water.name'
    _texture_path = 'blocks.water_still'
    _flow_texture_path = 'blocks.water_flow'
    _texture_cache = {}
    horizontal_flow_range = 4
    flowing_sound = 'liquid.water'
    source_sound = 'liquid.water'

class LAVA(FluidBlock):
    block_id = 'lava'
    name = 'tile.lava.name'
    _texture_path = 'blocks.lava_still'
    _flow_texture_path = 'blocks.lava_flow'
    # LEVEL remains the vanilla 0..7 range; the two-level drop-off means
    # normal horizontal spreading uses 0, 2, 4, 6, then stops.
    max_level = 7
    # Vanilla lava drops two legacy levels per horizontal spread and searches
    # only two cells for a lower slope in the normal dimension.
    flow_level_step = 2
    horizontal_flow_range = 2
    light_source = 15
    can_create_source = False
    flow_speed_ticks = 30
    flowing_sound = 'liquid.lava'
    source_sound = 'liquid.lavapop'

class SUGAR_CANE(Plant):
    block_id = 'sugar_cane'
    name = 'tile.reeds.name'
    _texture_path = 'blocks.reeds'

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

class FERN(GrassStain):
    block_id = 'fern'
    name = 'tile.tallgrass.fern.name'
    _texture_path = 'blocks.fern'

class DEAD_BUSH(Plant):
    block_id = 'dead_bush'
    name = 'tile.deadbush.name'
    _texture_path = 'blocks.deadbush'


class CACTUS(Block):
    block_id = 'cactus'
    name = 'tile.cactus.name'
    _texture_path = 'blocks.cactus_side'
    break_sound = 'dig.cloth'
    hardness = 0.4
    preferred_tool = 'axe'

    def on_update(self):
        below = self.location.world.get_block(self.location.add(0, -1, 0))
        if not isinstance(below, (CACTUS, SAND, RED_SAND)):
            self.location.world.break_block(self.location)

class BROWN_MUSHROOM(Plant):
    block_id = 'brown_mushroom'
    name = 'tile.mushroom.name'
    _texture_path = 'blocks.mushroom_brown'

    def on_update(self):
        pass

class RED_MUSHROOM(Plant):
    block_id = 'red_mushroom'
    name = 'tile.mushroom.name'
    _texture_path = 'blocks.mushroom_red'

    def on_update(self):
        pass

class VINE(GrassStain):
    block_id = 'vine'
    name = 'tile.vine.name'
    _texture_path = 'blocks.vine'
    light_attenuation = 1

    def on_update(self):
        # World-generated vines are decorative foreground growth and do not
        # require bottom support like ordinary plants.
        pass

class COAL_ORE(Block):
    block_id = 'coal_ore'
    name = 'tile.oreCoal.name'
    _texture_path = 'blocks.coal_ore'
    hardness = 3.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True

class IRON_ORE(Block):
    block_id = 'iron_ore'
    name = 'tile.oreIron.name'
    _texture_path = 'blocks.iron_ore'
    hardness = 3.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'stone'

class GOLD_ORE(Block):
    block_id = 'gold_ore'
    name = 'tile.oreGold.name'
    _texture_path = 'blocks.gold_ore'
    hardness = 3.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'iron'

class DIAMOND_ORE(Block):
    block_id = 'diamond_ore'
    name = 'tile.oreDiamond.name'
    _texture_path = 'blocks.diamond_ore'
    hardness = 3.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'iron'

class EMERALD_ORE(Block):
    block_id = 'emerald_ore'
    name = 'tile.oreEmerald.name'
    _texture_path = 'blocks.emerald_ore'
    hardness = 3.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'iron'

class LAPIS_ORE(Block):
    block_id = 'lapis_ore'
    name = 'tile.oreLapis.name'
    _texture_path = 'blocks.lapis_ore'
    hardness = 3.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'stone'

class REDSTONE_ORE(Block):
    block_id = 'redstone_ore'
    name = 'tile.oreRedstone.name'
    _texture_path = 'blocks.redstone_ore'
    hardness = 3.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'iron'

class BLUE_ORCHID(Plant):
    block_id = 'blue_orchid'
    name = 'tile.flower2.blueOrchid.name'
    _texture_path = 'blocks.flower_blue_orchid'

class ALLIUM(Plant):
    block_id = 'allium'
    name = 'tile.flower2.allium.name'
    _texture_path = 'blocks.flower_allium'

class AZURE_BLUET(Plant):
    block_id = 'azure_bluet'
    name = 'tile.flower2.houstonia.name'
    _texture_path = 'blocks.flower_houstonia'

class OXEYE_DAISY(Plant):
    block_id = 'oxeye_daisy'
    name = 'tile.flower2.oxeyeDaisy.name'
    _texture_path = 'blocks.flower_oxeye_daisy'

class DIAMOND_BLOCK(Block):
    block_id = 'diamond_block'
    name = 'tile.blockDiamond.name'
    _texture_path = 'blocks.diamond_block'
    hardness = 5.0
    preferred_tool = 'pickaxe'
    requires_correct_tool = True
    required_tool_tier = 'iron'


class TORCH(ParticleEmitterBlock):
    block_id = 'torch'
    name = 'tile.torch.name'
    hardness = 0
    solid = False
    collision_box = EMPTY
    _texture_path = 'blocks.torch_on'
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
        self.facing = self.normalize_facing(direction if direction is not None else facing)
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

    def get_placement_location(self, target, *, player=None, fore_place=False,
                               context=None):
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
                place_location = Location(world, target_location.x, target_location.y, forward_z)
            elif hit_face == "left":
                self.facing = self.FACING_LEFT
                place_location = Location(world, target_location.x - 1, target_location.y, target_z)
            elif hit_face == "right":
                self.facing = self.FACING_RIGHT
                place_location = Location(world, target_location.x + 1, target_location.y, target_z)
            elif hit_face == "top":
                self.facing = self.FACING_UP
                place_location = Location(world, target_location.x, target_location.y + 1, target_z)
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
    def _get_oriented_texture(cls, texture, size, facing, client = None):
        m = client.render.block_size // 16
        size = max(1, int(round(size)))
        scaled = pygame.transform.scale(texture, (size, size)).convert_alpha()
        if facing == cls.FACING_UP:
            return scaled

        if facing == cls.FACING_BACK:
            height = max(1, int(round(size * cls._NON_UP_HEIGHT_RATIO)))
            b = pygame.transform.scale(scaled, (size, height)).convert_alpha()
            result = pygame.Surface(b.get_size(), pygame.SRCALPHA)
            result.blit(b, (0, -3*m))
            return result

        angle = cls._SIDE_TILT_ANGLE if facing == cls.FACING_LEFT else -cls._SIDE_TILT_ANGLE
        rotated = pygame.transform.rotate(scaled, angle)
        # 旋转后纹理居中，需要平移使火把根部紧贴支撑方块。
        # FACING_LEFT:  支撑方块在右侧，向右平移。正值越大越靠右。
        # FACING_RIGHT: 支撑方块在左侧，向左平移。负值越大越靠左。
        shift_x = 3*m if facing == cls.FACING_LEFT else -7.7*m
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
            cls.has_transparent_pixels = client.resources_manager.has_transparent_pixels(texture)
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
    block_id = 'oak_slab'
    name = 'tile.oak_slab.name'
    _texture_path = 'blocks.planks_oak'

class TNT(Block):
    block_id = 'tnt'
    name = 'tile.tnt.name'
    _texture_path = 'blocks.tnt_side'

class MYCELIUM(Block):
    block_id = "mycelium"
    name = 'tile.mycelium.name'
    _texture_path = 'blocks.mycelium_side'

class MUSHROOM_STEM(Block):
    block_id = "mushroom_stem"
    name = 'tile.mushroom_stem.name'
    _texture_path = 'blocks.mushroom_block_skin_stem'

class RED_MUSHROOM_BLOCK(Block):
    block_id = "red_mushroom_block"
    name = 'tile.red_mushroom_block.name'
    _texture_path = 'blocks.mushroom_block_skin_red'

class BROWN_MUSHROOM_BLOCK(Block):
    block_id = "brown_mushroom_block"
    name = 'tile.brown_mushroom_block.name'
    _texture_path = 'blocks.mushroom_block_skin_brown'

# ---- block_id → Block 子类 缓存 ----
_BLOCK_REGISTRY: dict[str, type] = None  # None = 尚未构建


def _build_block_id_cache() -> dict[str, type]:
    """遍历 Block 的所有子类，构建 block_id → 子类 的映射（仅执行一次）。"""
    cache: dict[str, type] = {}

    def collect(cls):
        for subclass in cls.__subclasses__():
            bid = getattr(subclass, 'block_id', None)
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
