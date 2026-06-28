import os
if os.environ.get('PYCRAFT_CLIENT') == '1':
    import pygame

from resources.server.block_class import Block, Plant, GrassStain
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

    @client_method
    def get_texture(self, size, client: 'Client'):
        """
        获取草方块侧面纹理：将染色后的 grass_side_overlay 组合到 grass_side 上。
        (client 由 @client_only 自动注入)
        """
        # 检查缓存
        if size in self._side_texture_cache:
            return self._side_texture_cache[size]

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
        self._side_texture_cache[size] = final_texture.convert_alpha()

        return final_texture

class SHORT_GRASS(Plant):
    block_id = 'short_grass'
    name = 'short grass'
    _texture_path = 'blocks.tallgrass'
    _texture_cache = {}  # 缓存不同尺寸的染色纹理

    @client_method
    def get_texture(self, size, client: 'Client'):
        """
        获取短草纹理：将染色后的纹理。
        (client 由 @client_only 自动注入)
        """
        # 检查缓存
        if size in self._texture_cache:
            return self._texture_cache[size]

        # 1. 获取基础材质
        base_texture = client.resources_manager.get_texture_img("blocks.tallgrass")

        if base_texture is None:
            return None

        # 2. 缩放至目标尺寸
        texture_scaled = pygame.transform.scale(base_texture, (size, size))

        # 3. 染色纹理 (使用 RGB 元组 (30, 50, 70))
        stained_texture = client.resources_manager.biome_stain(texture_scaled, self.location).convert_alpha()

        # 4. 存入缓存
        self._texture_cache[size] = stained_texture

        return stained_texture

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

class OAK_LEAVES(Block):
    block_id = 'oak_leaves'
    name = 'oak_leaves'
    _texture_path = 'blocks.oak_leaves'

    _texture_cache = {}

    @client_method
    def get_texture(self, size, client: 'Client'):
        if size in self._texture_cache:
            return self._texture_cache[size]
        base_texture = client.resources_manager.get_texture_img("blocks.leaves_oak")

        if base_texture is None:
            return None

        texture_scaled = pygame.transform.scale(base_texture, (size, size))

        stained_texture = client.resources_manager.biome_stain(texture_scaled, self.location, "foliage").convert_alpha()

        self._texture_cache[size] = stained_texture

        return stained_texture

class OAK_LOG(Block):
    block_id = 'oak_log'
    name = 'oak_log'
    _texture_path = 'blocks.log_oak'

class BIRCH_LEAVES(Block):
    block_id = 'birch_leaves'
    name = 'birch leaves'
    _texture_path = 'blocks.leaves_birch'

class BIRCH_LOG(Block):
    block_id = 'birch_log'
    name = 'birch log'
    _texture_path = 'blocks.log_birch'

class SPRUCE_LEAVES(Block):
    block_id = 'spruce_leaves'
    name = 'spruce leaves'
    _texture_path = 'blocks.leaves_spruce'

class SPRUCE_LOG(Block):
    block_id = 'spruce_log'
    name = 'spruce log'
    _texture_path = 'blocks.log_spruce'

class JUNGLE_LEAVES(Block):
    block_id = 'jungle_leaves'
    name = 'jungle leaves'
    _texture_path = 'blocks.leaves_jungle'

class JUNGLE_LOG(Block):
    block_id = 'jungle_log'
    name = 'jungle log'
    _texture_path = 'blocks.log_jungle'

class ACACIA_LEAVES(Block):
    block_id = 'acacia_leaves'
    name = 'acacia leaves'
    _texture_path = 'blocks.leaves_acacia'

class ACACIA_LOG(Block):
    block_id = 'acacia_log'
    name = 'acacia log'
    _texture_path = 'blocks.log_acacia'

class DARK_OAK_LEAVES(Block):
    block_id = 'dark_oak_leaves'
    name = 'dark oak leaves'
    _texture_path = 'blocks.leaves_big_oak'

class DARK_OAK_LOG(Block):
    block_id = 'dark_oak_log'
    name = 'dark oak log'
    _texture_path = 'blocks.log_big_oak'

class SAND(Block):
    block_id = 'sand'
    name = 'sand'
    _texture_path = 'blocks.sand'

class RED_SAND(Block):
    block_id = 'red_sand'
    name = 'red sand'
    _texture_path = 'blocks.red_sand'

class SANDSTONE(Block):
    block_id = 'sandstone'
    name = 'sandstone'
    _texture_path = 'blocks.sandstone_normal'

class RED_SANDSTONE(Block):
    block_id = 'red_sandstone'
    name = 'red sandstone'
    _texture_path = 'blocks.red_sandstone_normal'

class GRAVEL(Block):
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

class SNOW(Block):
    block_id = 'snow'
    name = 'snow'
    _texture_path = 'blocks.snow'
    break_sound = 'dig.gravel'

class ICE(Block):
    block_id = 'ice'
    name = 'ice'
    _texture_path = 'blocks.ice'
    break_sound = 'dig.glass'

class WATER(Block):
    block_id = 'water'
    name = 'water'
    _texture_path = 'blocks.water_still'
    solid = False
    replaceable = True
    light_attenuation = 1

class SUGAR_CANE(Plant):
    block_id = 'sugar_cane'
    name = 'sugar_cane'
    _texture_path = 'blocks.reeds'

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
