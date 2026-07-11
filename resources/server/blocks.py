import os

from resources.server.biome import get_biome_by_id

if os.environ.get('PYCRAFT_CLIENT') == '1':
    pass

from resources.server.block_class import *
from resources.server.tags import BlockTag
from resources.server.utils import client_method


class AIR(Block):
    block_id = 'air'
    name = 'air'
    _texture_path = None
    solid = False
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
    name = 'stone'
    _texture_path = 'blocks.stone'

class GRANITE(Block):
    block_id = 'granite'
    name = 'granite'
    _texture_path = 'blocks.stone_granite'

class DIORITE(Block):
    block_id = 'diorite'
    name = 'diorite'
    _texture_path = 'blocks.stone_diorite'

class ANDESITE(Block):
    block_id = 'andesite'
    name = 'andesite'
    _texture_path = 'blocks.stone_andesite'

class BEDROCK(Block):
    block_id = 'bedrock'
    name = 'bedrock'
    _texture_path = 'blocks.bedrock'

class DIRT(Block):
    block_id = 'dirt'
    name = 'dirt'
    _texture_path = 'blocks.dirt'
    break_sound = 'dig.gravel'

class COARSE_DIRT(Block):
    block_id = 'coarse_dirt'
    name = 'coarse dirt'
    _texture_path = 'blocks.coarse_dirt'
    break_sound = 'dig.gravel'

class PODZOL(Block):
    block_id = 'podzol'
    name = 'podzol'
    _texture_path = 'blocks.dirt_podzol_side'
    break_sound = 'dig.gravel'
    Tags = [BlockTag.GRASS_BLOCKS]

class GRASS_BLOCK(Block):
    block_id = 'grass_block'
    name = 'grass block'
    light_attenuation = 5
    break_sound = 'dig.gravel'
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
    name = 'short grass'
    _texture_path = 'blocks.tallgrass'


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
    name = 'tall grass'
    _texture_path = 'blocks.double_plant_grass_bottom'
    top_block_id = 'tall_grass_top'


class TALL_GRASS_TOP(DoublePlantTopMixin, GrassStain):
    block_id = 'tall_grass_top'
    name = 'tall grass top'
    _texture_path = 'blocks.double_plant_grass_top'
    bottom_block_id = 'tall_grass'


class LARGE_FERN(DoublePlantBottomMixin, GrassStain):
    block_id = 'large_fern'
    name = 'large fern'
    _texture_path = 'blocks.double_plant_fern_bottom'
    top_block_id = 'large_fern_top'


class LARGE_FERN_TOP(DoublePlantTopMixin, GrassStain):
    block_id = 'large_fern_top'
    name = 'large fern top'
    _texture_path = 'blocks.double_plant_fern_top'
    bottom_block_id = 'large_fern'


class SUNFLOWER(DoublePlantBottomMixin, Plant):
    block_id = 'sunflower'
    name = 'sunflower'
    _texture_path = 'blocks.double_plant_sunflower_bottom'
    top_block_id = 'sunflower_top'


class SUNFLOWER_TOP(DoublePlantTopMixin, Plant):
    block_id = 'sunflower_top'
    name = 'sunflower top'
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
    name = 'rose bush'
    _texture_path = 'blocks.double_plant_rose_bottom'
    top_block_id = 'rose_bush_top'


class ROSE_BUSH_TOP(DoublePlantTopMixin, Plant):
    block_id = 'rose_bush_top'
    name = 'rose bush top'
    _texture_path = 'blocks.double_plant_rose_top'
    bottom_block_id = 'rose_bush'


class PEONY(DoublePlantBottomMixin, Plant):
    block_id = 'peony'
    name = 'peony'
    _texture_path = 'blocks.double_plant_paeonia_bottom'
    top_block_id = 'peony_top'


class PEONY_TOP(DoublePlantTopMixin, Plant):
    block_id = 'peony_top'
    name = 'peony top'
    _texture_path = 'blocks.double_plant_paeonia_top'
    bottom_block_id = 'peony'


class LILAC(DoublePlantBottomMixin, Plant):
    block_id = 'lilac'
    name = 'lilac'
    _texture_path = 'blocks.double_plant_syringa_bottom'
    top_block_id = 'lilac_top'


class LILAC_TOP(DoublePlantTopMixin, Plant):
    block_id = 'lilac_top'
    name = 'lilac top'
    _texture_path = 'blocks.double_plant_syringa_top'
    bottom_block_id = 'lilac'

class OAK_PLANK(Block):
    block_id = 'oak_plank'
    name = 'oak plank'
    _texture_path = 'blocks.planks_oak'
    break_sound = 'dig.wood'

class GLOWSTONE(Block):
    block_id = 'glowstone'
    name = 'glowstone'
    _texture_path = 'blocks.glowstone'
    light_source = 15
    light_attenuation = 0
    break_sound = 'dig.glass'

class POPPY(Plant):
    block_id = 'poppy'
    name = 'poppy'
    _texture_path = 'blocks.flower_rose'

class DANDELION(Plant):
    block_id = 'dandelion'
    name = 'dandelion'
    _texture_path = 'blocks.flower_dandelion'

class OAK_LEAVES(Leaves):
    block_id = 'oak_leaves'
    name = 'oak_leaves'
    _texture_path = 'blocks.leaves_oak'

class OAK_LOG(Log):
    block_id = 'oak_log'
    name = 'oak_log'
    _texture_path = 'blocks.log_oak'

class BIRCH_LEAVES(Leaves):
    block_id = 'birch_leaves'
    name = 'birch leaves'
    _texture_path = 'blocks.leaves_birch'

class BIRCH_LOG(Log):
    block_id = 'birch_log'
    name = 'birch log'
    _texture_path = 'blocks.log_birch'

class SPRUCE_LEAVES(Leaves):
    block_id = 'spruce_leaves'
    name = 'spruce leaves'
    _texture_path = 'blocks.leaves_spruce'

class SPRUCE_LOG(Log):
    block_id = 'spruce_log'
    name = 'spruce log'
    _texture_path = 'blocks.log_spruce'

class JUNGLE_LEAVES(Leaves):
    block_id = 'jungle_leaves'
    name = 'jungle leaves'
    _texture_path = 'blocks.leaves_jungle'

class JUNGLE_LOG(Log):
    block_id = 'jungle_log'
    name = 'jungle log'
    _texture_path = 'blocks.log_jungle'

class ACACIA_LEAVES(Leaves):
    block_id = 'acacia_leaves'
    name = 'acacia leaves'
    _texture_path = 'blocks.leaves_acacia'

class ACACIA_LOG(Log):
    block_id = 'acacia_log'
    name = 'acacia log'
    _texture_path = 'blocks.log_acacia'

class DARK_OAK_LEAVES(Leaves):
    block_id = 'dark_oak_leaves'
    name = 'dark oak leaves'
    _texture_path = 'blocks.leaves_big_oak'

class DARK_OAK_LOG(Log):
    block_id = 'dark_oak_log'
    name = 'dark oak log'
    _texture_path = 'blocks.log_big_oak'

class SAND(GravityBlock):
    block_id = 'sand'
    name = 'sand'
    _texture_path = 'blocks.sand'
    break_sound = "dig.sand"

class RED_SAND(GravityBlock):
    block_id = 'red_sand'
    name = 'red sand'
    _texture_path = 'blocks.red_sand'
    break_sound = "dig.sand"

class SANDSTONE(Block):
    block_id = 'sandstone'
    name = 'sandstone'
    _texture_path = 'blocks.sandstone_normal'

class RED_SANDSTONE(Block):
    block_id = 'red_sandstone'
    name = 'red sandstone'
    _texture_path = 'blocks.red_sandstone_normal'

class GRAVEL(GravityBlock):
    block_id = 'gravel'
    name = 'gravel'
    _texture_path = 'blocks.gravel'
    break_sound = 'dig.gravel'

class CLAY(Block):
    block_id = 'clay'
    name = 'clay'
    _texture_path = 'blocks.clay'
    break_sound = 'dig.gravel'

class HARDENED_CLAY(Block):
    block_id = 'hardened_clay'
    name = 'hardened clay'
    _texture_path = 'blocks.hardened_clay'

class SNOW(BottomSupport):
    block_id = 'snow'
    name = 'snow'
    _texture_path = 'blocks.snow'
    break_sound = 'dig.snow'
    solid = False
    light_attenuation = 1
    has_transparent_pixels = True

    _texture_cache = {}

    def __init__(self, layer = 1):
        super().__init__()
        if layer > 8:
            raise Exception('layer > 8')
        self.layer = layer

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
    name = 'snow block'
    _texture_path = 'blocks.snow'
    break_sound = 'dig.snow'

class ICE(Block):
    block_id = 'ice'
    name = 'ice'
    _texture_path = 'blocks.ice'
    break_sound = 'dig.glass'
    friction = 0.9

class WATER(FluidBlock):
    block_id = 'water'
    name = 'water'
    _texture_path = 'blocks.water_still'
    _flow_texture_path = 'blocks.water_flow'
    _texture_cache = {}

class SUGAR_CANE(Plant):
    block_id = 'sugar_cane'
    name = 'sugar_cane'
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
    name = 'fern'
    _texture_path = 'blocks.fern'

class DEAD_BUSH(Plant):
    block_id = 'dead_bush'
    name = 'dead bush'
    _texture_path = 'blocks.deadbush'


class CACTUS(Block):
    block_id = 'cactus'
    name = 'cactus'
    _texture_path = 'blocks.cactus_side'
    break_sound = 'dig.cloth'

    def on_update(self):
        below = self.location.world.get_block(self.location.add(0, -1, 0))
        if not isinstance(below, (CACTUS, SAND, RED_SAND)):
            self.location.world.break_block(self.location)

class BROWN_MUSHROOM(Plant):
    block_id = 'brown_mushroom'
    name = 'brown mushroom'
    _texture_path = 'blocks.mushroom_brown'

    def on_update(self):
        pass

class RED_MUSHROOM(Plant):
    block_id = 'red_mushroom'
    name = 'red mushroom'
    _texture_path = 'blocks.mushroom_red'

class COAL_ORE(Block):
    block_id = 'coal_ore'
    name = 'coal ore'
    _texture_path = 'blocks.coal_ore'

class IRON_ORE(Block):
    block_id = 'iron_ore'
    name = 'iron ore'
    _texture_path = 'blocks.iron_ore'

class GOLD_ORE(Block):
    block_id = 'gold_ore'
    name = 'gold ore'
    _texture_path = 'blocks.gold_ore'

class DIAMOND_ORE(Block):
    block_id = 'diamond_ore'
    name = 'diamond ore'
    _texture_path = 'blocks.diamond_ore'

class EMERALD_ORE(Block):
    block_id = 'emerald_ore'
    name = 'emerald ore'
    _texture_path = 'blocks.emerald_ore'

class LAPIS_ORE(Block):
    block_id = 'lapis_ore'
    name = 'lapis ore'
    _texture_path = 'blocks.lapis_ore'

class REDSTONE_ORE(Block):
    block_id = 'redstone_ore'
    name = 'redstone ore'
    _texture_path = 'blocks.redstone_ore'

class BLUE_ORCHID(Plant):
    block_id = 'blue_orchid'
    name = 'blue orchid'
    _texture_path = 'blocks.flower_blue_orchid'

class ALLIUM(Plant):
    block_id = 'allium'
    name = 'allium'
    _texture_path = 'blocks.flower_allium'

class AZURE_BLUET(Plant):
    block_id = 'azure_bluet'
    name = 'azure bluet'
    _texture_path = 'blocks.flower_houstonia'

class OXEYE_DAISY(Plant):
    block_id = 'oxeye_daisy'
    name = 'oxeye daisy'
    _texture_path = 'blocks.flower_oxeye_daisy'

class DIAMOND_BLOCK(Block):
    block_id = 'diamond_block'
    name = 'tile.blockDiamond.name'
    _texture_path = 'blocks.diamond_block'





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
    raise ValueError(f"Unknown block ID: {block_id}")
