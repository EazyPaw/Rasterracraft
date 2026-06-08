import os
if os.environ.get('PYCRAFT_CLIENT') == '1':
    import pygame

from resources.server.block_class import Block, Plant
from resources.server.tags import BlockTag


class AIR(Block):
    block_id = 'air'
    name = 'air'
    _texture_path = None
    solid = False
    replaceable = True
    breakable = False
    light_attenuation = 1

    @classmethod
    def get_texture(cls, size, client):
        return None

    def on_right_click(self):
        pass

class STONE(Block):
    block_id = 'stone'
    name = 'stone'
    _texture_path = 'blocks.stone'

class BEDROCK(Block):
    block_id = 'bedrock'
    name = 'bedrock'
    _texture_path = 'blocks.bedrock'

class DIRT(Block):
    block_id = 'dirt'
    name = 'dirt'
    _texture_path = 'blocks.dirt'
    break_sound = 'dig.gravel'

class GRASS_BLOCK(Block):
    block_id = 'grass_block'
    name = 'grass block'
    light_attenuation = 5
    break_sound = 'dig.gravel'
    _side_texture_cache = {}  # 缓存不同尺寸的侧面纹理
    Tags = [BlockTag.GRASS_BLOCKS]

    @classmethod
    def get_texture(cls, size, client: 'Client'):
        """
        获取草方块侧面纹理：将染色后的 grass_side_overlay 组合到 grass_side 上。
        """
        # 检查缓存
        if size in cls._side_texture_cache:
            return cls._side_texture_cache[size]

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
        stained_overlay = client.resources_manager.stain_grayscale(overlay_scaled, "#91bd59")

        # 4. 组合图层
        # 使用 stain.py 中的 overlay_surfaces 逻辑，或者直接使用 pygame 的 blit
        final_texture = base_side_scaled.convert_alpha()
        final_texture.blit(stained_overlay, (0, 0))

        # 5. 存入缓存
        cls._side_texture_cache[size] = final_texture.convert_alpha()

        return final_texture

class SHORT_GRASS(Plant):
    block_id = 'short_grass'
    name = 'short grass'
    _texture_path = 'blocks.tallgrass'
    _texture_cache = {}  # 缓存不同尺寸的染色纹理

    @classmethod
    def get_texture(cls, size, client: 'Client'):
        """
        获取短草纹理：将染色后的纹理。
        """
        # 检查缓存
        if size in cls._texture_cache:
            return cls._texture_cache[size]

        # 1. 获取基础材质
        base_texture = client.resources_manager.get_texture_img("blocks.tallgrass")

        if base_texture is None:
            return None

        # 2. 缩放至目标尺寸
        texture_scaled = pygame.transform.scale(base_texture, (size, size))

        # 3. 染色纹理 (使用 RGB 元组 (30, 50, 70))
        stained_texture = client.resources_manager.stain_grayscale(texture_scaled, "#91bd59").convert_alpha()

        # 4. 存入缓存
        cls._texture_cache[size] = stained_texture

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

def get_block_by_id(block_id: str) -> Block:
    def find_subclass(cls):
        """递归查找所有子类"""
        for subclass in cls.__subclasses__():
            if getattr(subclass, 'block_id', None) == block_id:
                return subclass()
            # 递归查找子类的子类
            result = find_subclass(subclass)
            if result:
                return result
        return None
    
    block = find_subclass(Block)
    if block:
        return block
    raise ValueError(f"Unknown block ID: {block_id}")