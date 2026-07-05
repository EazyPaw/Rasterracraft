"""
装饰物生成 mixin 模块

提供树木、花草、蘑菇、仙人掌、甘蔗等地表装饰物的生成逻辑，
以及方块工厂和树木配置加载功能。
"""

import json
from pathlib import Path
from typing import Callable

from resources.server.blocks import *
from resources.server.generator.config import TreeConfig, BiomeProfile, WORLDGEN_DIR
from resources.server.generator.noise import NoiseMixin


class DecorationMixin(NoiseMixin):
    """装饰物生成 mixin。

    提供方块工厂、树木配置加载、以及树木、花草等
    地表装饰物的生成方法。
    需要宿主类提供 ``self.sea_level`` 属性。
    """

    # ---- 默认树木配置（可被 JSON 文件覆盖） ----
    default_tree_configs = {
        "oak": TreeConfig("oak_log", "oak_leaves", 4, 2, 0, 2, "blob"),
        "birch": TreeConfig("birch_log", "birch_leaves", 5, 2, 0, 2, "blob"),
        "spruce": TreeConfig("spruce_log", "spruce_leaves", 5, 2, 1, 3, "spruce"),
        "jungle_tree": TreeConfig("jungle_log", "jungle_leaves", 6, 5, 0, 2, "blob"),
        "acacia": TreeConfig("acacia_log", "acacia_leaves", 5, 2, 2, 2, "flat"),
        "dark_oak": TreeConfig("dark_oak_log", "dark_oak_leaves", 5, 2, 0, 3, "blob"),
    }

    # ------------------------------------------------------------------
    # 方块工厂（反射 Block 子类）
    # ------------------------------------------------------------------

    def _build_block_factories(self) -> dict[str, Callable[[], Block]]:
        """遍历所有 Block 子类，构建 block_id → 构造函数 的映射表。

        用于将字符串 block_id 转换为实际 Block 实例，
        支持 JSON 配置文件中以字符串形式指定的方块。

        Returns
        -------
        dict[str, Callable[[], Block]]
            键为 block_id 字符串，值为无参构造函数的字典。
        """
        factories = {}
        for cls in Block.__subclasses__():
            self._collect_block_factory(cls, factories)
        return factories

    def _collect_block_factory(self, cls, factories):
        """递归收集 Block 子类到工厂映射表中。

        Parameters
        ----------
        cls : type
            当前要处理的 Block 子类。
        factories : dict
            累积的工厂映射表。
        """
        block_id = getattr(cls, "block_id", None)
        if block_id:
            factories[block_id] = cls
        for subclass in cls.__subclasses__():
            self._collect_block_factory(subclass, factories)

    def _block(self, block_id: str):
        """通过 block_id 字符串创建对应的 Block 实例。

        若 block_id 未找到，回退到 STONE()。

        Parameters
        ----------
        block_id : str
            方块的标识名（如 ``"oak_log"``）。

        Returns
        -------
        Block
            对应的方块实例。
        """
        cls = self.block_factories.get(block_id)
        if cls is None:
            return STONE()
        return cls()

    # ------------------------------------------------------------------
    # 树木配置加载
    # ------------------------------------------------------------------

    def _load_tree_configs(self):
        """加载树木配置，合并默认值与 JSON 自定义文件。

        从 ``data/minecraft/worldgen/configured_feature/*.json``
        读取树木配置，若文件不存在或解析失败则使用默认值。

        JSON 格式兼容 Minecraft data pack 的 configured_feature 结构。

        Returns
        -------
        dict[str, TreeConfig]
            树木种类名 → TreeConfig 的映射。
        """
        configs = dict(self.default_tree_configs)
        configured_feature_dir = WORLDGEN_DIR / "configured_feature"
        for name, fallback in self.default_tree_configs.items():
            path = configured_feature_dir / f"{name}.json"
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue

            config = data.get("config", {})
            trunk = self._minecraft_name_to_block_id(
                config.get("trunk_provider", {}).get("state", {}).get("Name"),
                fallback.trunk,
            )
            leaves = self._minecraft_name_to_block_id(
                config.get("foliage_provider", {}).get("state", {}).get("Name"),
                fallback.leaves,
            )
            trunk_placer = config.get("trunk_placer", {})
            foliage_placer = config.get("foliage_placer", {})
            configs[name] = TreeConfig(
                trunk=trunk,
                leaves=leaves,
                base_height=int(trunk_placer.get("base_height", fallback.base_height)),
                height_rand_a=int(trunk_placer.get("height_rand_a", fallback.height_rand_a)),
                height_rand_b=int(trunk_placer.get("height_rand_b", fallback.height_rand_b)),
                radius=self._read_int_provider(foliage_placer.get("radius", fallback.radius)),
                shape=fallback.shape,
            )
        return configs

    def _read_int_provider(self, value) -> int:
        """解析 Minecraft JSON 中的 IntProvider 结构。

        Minecraft 的 IntProvider 可以是纯整数或嵌套对象
        （如 ``{"type": "uniform", "value": {"min_inclusive": 2, "max_inclusive": 5}}``）。

        Parameters
        ----------
        value : int | dict
            待解析的值。

        Returns
        -------
        int
            解析后的整数值，无法解析时返回 2。
        """
        if isinstance(value, int):
            return value
        if isinstance(value, dict):
            nested = value.get("value", value)
            if isinstance(nested, dict):
                return int(nested.get("max_inclusive", nested.get("min_inclusive", 2)))
        return 2

    def _minecraft_name_to_block_id(self, name, fallback):
        """将 Minecraft 命名空间 ID（如 ``"minecraft:oak_log"``）转换为内部 block_id。

        去掉命名空间前缀，只保留冒号后的部分。

        Parameters
        ----------
        name : str | None
            完整的命名空间 ID，None 或空字符串时使用回退值。
        fallback : str
            转换失败时的默认 block_id。

        Returns
        -------
        str
            内部使用的 block_id。
        """
        if not name:
            return fallback
        return str(name).split(":", 1)[-1]

    # ------------------------------------------------------------------
    # 地表装饰物（树木、花草等）
    # ------------------------------------------------------------------

    def get_structure_block(self, x: int, y: int, z: int, surface_y: int,
                            profile: BiomeProfile):
        """获取地表装饰物方块（树木、花草、蘑菇等）。

        仅在地表以上（y == surface_y + 1）的前景层（z == 0）生成，
        且地表不能低于海平面以下（否则为水下）。

        生成顺序：树木 → 仙人掌 → 甘蔗 → 蕨类 → 蘑菇 → 花 → 草丛。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        y : int
            高度坐标。
        z : int
            层索引。
        surface_y : int
            该列的地表高度。
        profile : BiomeProfile
            该列的生物群系配置。

        Returns
        -------
        Block | None
            装饰物方块，无装饰物时返回 None。
        """
        # 装饰物仅在前景层生成
        if z != 0:
            # 优先检查树木（树木可跨越多个 Y 层级）
            tree_block = self.get_tree_block(x, y, surface_y, profile)
            if tree_block is not None:
                return tree_block

        # 以下装饰物仅在地表上方一格生成
        if y != surface_y + 1:
            return None
        # 水面以下不生成地表装饰物
        if surface_y < self.sea_level:
            return None

        # 使用两个独立随机值提高生成多样性
        chance = self._rand01(x, 0, 700)       # 主随机数
        local  = self._noise1(x, 0.18, 1, 710)  # 局部噪声（用于阈值微调）

        # 仙人掌（沙漠 / 荒地）
        if profile.cactus_chance and chance < profile.cactus_chance:
            return CACTUS()
        # 甘蔗（靠近水域）
        if (profile.sugar_cane_chance
                and self.is_near_water(x, surface_y)
                and chance < profile.sugar_cane_chance):
            return SUGAR_CANE()
        # 蕨类（湿润群系，噪声适中）
        if profile.fern_chance and chance < profile.fern_chance and local > -0.4:
            return FERN()
        # 蘑菇（噪声偏低的区域）
        if profile.mushroom_chance and chance < profile.mushroom_chance and local < 0.15:
            return BROWN_MUSHROOM() if self._rand01(x, 0, 711) < 0.55 else RED_MUSHROOM()
        # 花（噪声偏高的区域）
        if profile.flower_chance and chance < profile.flower_chance and local > 0.2:
            return POPPY() if self._rand01(x, 0, 712) < 0.5 else DANDELION()
        # 草丛（最高频的装饰物）
        if profile.grass_chance and chance < profile.grass_chance:
            return SHORT_GRASS()

        return None

    # ------------------------------------------------------------------
    # 树木生成
    # ------------------------------------------------------------------

    def get_tree_block(self, x: int, y: int, surface_y: int,
                       profile: BiomeProfile):
        """获取树木方块（在给定坐标查找是否有树木部件）。

        树木生成采用"候选树干"模式：在一个横向范围内
        （``±max_tree_lookup``）搜索合理的树干位置，若当前位置
        落入某棵树的树干 / 树冠范围则返回对应方块。

        这种"反向查找"保证树木在不同列之间保持连续性，
        且无需为每棵树存储全局状态。

        Parameters
        ----------
        x : int
            当前方块的全局 X 坐标。
        y : int
            当前方块的高度坐标。
        surface_y : int
            当前列的地表高度（未直接使用，传入供子调用）。
        profile : BiomeProfile
            当前列的生物群系配置。

        Returns
        -------
        Block | None
            树木方块（树干或树叶），无树木则返回 None。
        """
        if profile.tree is None:
            return None
        # 在可能的树干位置范围内搜索
        for trunk_x in range(x - self.max_tree_lookup,
                             x + self.max_tree_lookup + 1):
            trunk_surface = self.get_surface_height(trunk_x)
            # 树干不能位于水下
            if trunk_surface < self.sea_level:
                continue
            # 确保候选树干位置的群系树木种类一致
            trunk_profile = self.get_profile(self.get_column_biome(trunk_x))
            if trunk_profile.tree != profile.tree:
                continue
            # 该位置确实有一棵树
            if not self.has_tree_at(trunk_x, trunk_surface, trunk_profile):
                continue
            # 检查当前 (x, y) 是否属于该树的树干或树冠
            block_id = self.tree_block_at(profile.tree, trunk_x, trunk_surface, x, y)
            if block_id:
                return self._block(block_id)
        return None

    def has_tree_at(self, x: int, surface_y: int, profile: BiomeProfile) -> bool:
        """判断指定位置是否应生成一棵树。

        使用基于列索引的网格化放置 + 概率 + 密度噪声三重判定：

        1. 网格间距：高密度群系（tree_chance > 0.07）间距 5，否则 7
        2. 哈希取模：确保树木在网格内均匀分布
        3. 密度噪声 × 概率：最终随机判定

        Parameters
        ----------
        x : int
            候选树干 X 坐标。
        surface_y : int
            该列的地表高度。
        profile : BiomeProfile
            该列的生物群系配置。

        Returns
        -------
        bool
            True 表示该位置应生成一棵树。
        """
        if surface_y < self.sea_level - 1:
            return False
        # 网格化放置：确保树木不会过密
        spacing = 5 if profile.tree_chance > 0.07 else 7
        if self._stable_hash(x // spacing, 810) % spacing != x % spacing:
            return False
        # 密度噪声 + 概率判定
        density = self._noise1(x, 0.035, 2, 811)
        return self._rand01(x, surface_y, 812) < profile.tree_chance * (1.25 + density)

    def tree_block_at(self, tree_name: str, trunk_x: int, ground_y: int,
                      x: int, y: int) -> str | None:
        """在给定树木的局部坐标系中，判定 (x, y) 属于树干、树叶还是空气。

        支持三种树冠形状：

        - **blob**（球冠）: 以树顶为中心，使用曼哈顿距离判定球形树冠
        - **spruce**（云杉）: 层叠尖顶形，树冠半径从下往上递减
        - **flat**（平冠）: 金合欢特有的扁平扩散形树冠

        Parameters
        ----------
        tree_name : str
            树木种类名（对应 tree_configs 的键）。
        trunk_x : int
            树干的 X 坐标（树的根位置）。
        ground_y : int
            树根处的地表高度。
        x : int
            待判定方块的全局 X 坐标。
        y : int
            待判定方块的高度坐标。

        Returns
        -------
        str | None
            方块的 block_id（trunk / leaves），坐标不在树内时返回 None。
        """
        config = self.tree_configs[tree_name]
        # 计算随机高度
        height = config.base_height
        if config.height_rand_a > 0:
            height += self._stable_hash(trunk_x, 820) % (config.height_rand_a + 1)
        if config.height_rand_b > 0:
            height += self._stable_hash(trunk_x, 821) % (config.height_rand_b + 1)

        dx = x - trunk_x
        dy = y - ground_y  # dy=1 为树干第一格

        # ---- 树干 ----
        if dx == 0 and 1 <= dy <= height:
            return config.trunk

        # ---- 树冠（不同形状） ----
        top = height + 1
        if config.shape == "spruce":
            # 云杉形：树冠从下往上逐层收窄
            leaf_start = max(2, height - 4)
            if leaf_start <= dy <= top:
                layer_radius = max(1, min(config.radius, (top - dy) // 2 + 1))
                if abs(dx) <= layer_radius and not (abs(dx) == layer_radius and dy == top):
                    return config.leaves
        elif config.shape == "flat":
            # 扁平形：金合欢风格，树冠集中在顶部
            if height - 1 <= dy <= height + 2:
                layer_radius = config.radius + (1 if dy in {height, height + 1} else 0)
                if abs(dx) <= layer_radius:
                    return config.leaves
        else:
            # 球形（blob）：橡树 / 桦树等默认形状
            center_y = height + 1
            dist = abs(dx) + abs(y - (ground_y + center_y)) * 0.75
            if dist <= config.radius + 1.1 and dy >= height - 2:
                return config.leaves

        return None

    # ------------------------------------------------------------------
    # 辅助判定
    # ------------------------------------------------------------------

    def is_near_water(self, x: int, surface_y: int) -> bool:
        """判断指定位置是否靠近水域（用于甘蔗生成判定）。

        检查 ±2 格范围内是否有任何列的地表低于海平面，
        或当前列地表高度不超过海平面 +1。

        Parameters
        ----------
        x : int
            全局 X 坐标。
        surface_y : int
            当前列的地表高度。

        Returns
        -------
        bool
            True 表示靠近水域。
        """
        for nx in range(x - 1, x + 2):
            if self.get_surface_height(nx) < self.sea_level:
                return True
        return surface_y <= self.sea_level + 1
