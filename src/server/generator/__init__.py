# Commented and arranged by ChatGPT
"""
世界生成器包 (World Generator Package)

本包负责程序化生成 2D Minecraft 世界的所有内容，包括：
- 地形高度图（通过多层 Perlin 噪声合成）
- 生物群系判定（基于大陆性、温度、湿度、奇异度、侵蚀度五个参数）
- 地表 / 地下方块构成（表层、亚层、填充层 + 矿石分布）
- 洞穴系统（大洞穴 + 隧道 + 虫洞三层噪声混合）
- 树木及地表装饰物（花草、蘑菇、仙人掌、甘蔗等）

核心类继承体系::

    Generator (ABC)
    ├── MinecraftLike2D    — 仿 Minecraft 主世界生成器（噪声驱动）
    ├── ClassicFlat        — 经典超平坦世界生成器
    └── bedrock_flat_generator — 仅基岩的调试用生成器

MinecraftLike2D 支持通过 JSON 文件自定义树木配置，
从 ``data/minecraft/worldgen/configured_feature/*.json`` 加载。
"""

from src.server.generator.base import Generator
from src.server.generator.config import TreeConfig, BiomeProfile, WORLDGEN_DIR
from src.server.generator.noise import NoiseMixin
from src.server.generator.terrain import TerrainMixin
from src.server.generator.decorations import DecorationMixin
from src.server.generator.minecraft_like import MinecraftLike2D
from src.server.generator.classic_flat import ClassicFlat
from src.server.generator.bedrock_flat import bedrock_flat_generator
