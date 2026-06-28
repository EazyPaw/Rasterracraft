import logging
import json
from pathlib import Path

from abc import ABC

from resources.server.utils import client_method, hex_to_rgb


class Biome(ABC):
    biome_id = "null"
    name = "null"
    temperature = 0.5
    downfall = 0.5
    grass_color = (0, 0, 0)
    foliage_color = (0, 0, 0)
    sky_color = (255, 255, 255)
    fog_color = (0, 0, 0)

    def __init__(self):
        """
        初始化生物群系，根据温度和降水从颜色图中获取草和树叶的颜色。
        注意：__init__ 需要客户端上下文支持（_get_color_from_colormap 使用了 @client_only）。
        在纯服务端环境下，子类应覆盖 grass_color 和 foliage_color 为固定值。
        """
        cls = type(self)
        if getattr(cls, "grass_color", Biome.grass_color) != Biome.grass_color:
            self.grass_color = cls.grass_color
        else:
            try:
                self.grass_color = self._get_color_from_colormap("colormap.grass")
            except RuntimeError:
                self.grass_color = _default_grass_color(self.temperature, self.downfall)
        if getattr(cls, "foliage_color", Biome.foliage_color) != Biome.foliage_color:
            self.foliage_color = cls.foliage_color
        else:
            try:
                self.foliage_color = self._get_color_from_colormap("colormap.foliage")
            except RuntimeError:
                self.foliage_color = _default_foliage_color(self.temperature, self.downfall)



    @client_method
    def _get_color_from_colormap(self, colormap_name: str, client = None) -> tuple[int, int, int]:
        """
        从颜色图中获取对应坐标的 RGB 颜色值。
        (client 参数由 @client_only 自动注入)

        :param colormap_name: 颜色图名称（如 "colormap.grass" 或 "colormap.foliage"）
        :param client: 客户端实例（自动注入）
        :return: (R, G, B) 颜色元组
        """
        # 获取颜色图 Surface
        colormap_surface = client.resources_manager.get_texture_img(colormap_name)
        
        if colormap_surface is None:
            logging.error(f"Failed to get colormap {colormap_name}")
            return 0, 0, 0
        
        # 钳位温度值到 [0.0, 1.0]
        adj_temperature = max(0.0, min(1.0, self.temperature))
        
        # 钳位降水值到 [0.0, 1.0]
        adj_downfall = max(0.0, min(1.0, self.downfall))
        
        # 降水值乘以温度值，限制在下三角形区域
        adj_downfall *= adj_temperature
        
        # 计算颜色坐标（左上角为原点）
        x = int((1.0 - adj_temperature) * 255)
        y = int((1.0 - adj_downfall) * 255)
        
        # 确保坐标在有效范围内
        x = max(0, min(x, colormap_surface.get_width() - 1))
        y = max(0, min(y, colormap_surface.get_height() - 1))
        
        # 从 Surface 中获取像素颜色
        color = colormap_surface.get_at((x, y))
        
        # 返回 RGB 元组（忽略 Alpha 通道）
        return color.r, color.g, color.b


class Void(Biome):
    biome_id = "void"
    name = "void"
    temperature = 0.8
    downfall = 0.4

class PLAIN(Biome):
    biome_id = "plain"
    name = "plain"
    temperature = 0.8
    downfall = 0.4
    sky_color = hex_to_rgb("#78a7ff")
    fog_color = hex_to_rgb("#c0d8ff")



_BIOME_REGISTRY: dict[str, type] = None  # None = 尚未构建


_WORLDGEN_BIOME_DIR = Path(__file__).resolve().parents[2] / "data" / "minecraft" / "worldgen" / "biome"


def _int_to_rgb(value: int) -> tuple[int, int, int]:
    return (value >> 16 & 255, value >> 8 & 255, value & 255)


def _normalize_biome_id(biome_id: str | None) -> str:
    if not biome_id:
        return Void.biome_id
    return biome_id.split(":", 1)[-1]


def _default_grass_color(temperature: float, downfall: float) -> tuple[int, int, int]:
    cold = max(0.0, min(1.0, 1.0 - temperature))
    dry = max(0.0, min(1.0, 1.0 - downfall))
    return (
        int(96 + dry * 44 - cold * 20),
        int(148 + downfall * 58 - cold * 14),
        int(64 + downfall * 34 + cold * 28),
    )


def _default_foliage_color(temperature: float, downfall: float) -> tuple[int, int, int]:
    cold = max(0.0, min(1.0, 1.0 - temperature))
    dry = max(0.0, min(1.0, 1.0 - downfall))
    return (
        int(78 + dry * 30 - cold * 16),
        int(132 + downfall * 54 - cold * 10),
        int(54 + downfall * 28 + cold * 24),
    )


def _load_worldgen_biome_classes() -> dict[str, type]:
    classes: dict[str, type] = {}
    if not _WORLDGEN_BIOME_DIR.exists():
        return classes

    for biome_file in _WORLDGEN_BIOME_DIR.glob("*.json"):
        biome_id = biome_file.stem
        try:
            with biome_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logging.warning(f"Failed to load biome json {biome_file}: {exc}")
            continue

        effects = data.get("effects", {})
        temperature = data.get("temperature", Biome.temperature)
        downfall = data.get("downfall", Biome.downfall)
        attrs = {
            "biome_id": biome_id,
            "name": biome_id.replace("_", " "),
            "temperature": temperature,
            "downfall": downfall,
            "sky_color": _int_to_rgb(effects.get("sky_color", 0xFFFFFF)),
            "fog_color": _int_to_rgb(effects.get("fog_color", 0x000000)),
            "grass_color": _default_grass_color(temperature, downfall),
            "foliage_color": _default_foliage_color(temperature, downfall),
        }
        if "grass_color" in effects:
            attrs["grass_color"] = _int_to_rgb(effects["grass_color"])
        if "foliage_color" in effects:
            attrs["foliage_color"] = _int_to_rgb(effects["foliage_color"])

        class_name = "".join(part.capitalize() for part in biome_id.split("_")) or "WorldgenBiome"
        classes[biome_id] = type(class_name, (Biome,), attrs)

    return classes


def _build_biome_id_cache() -> dict[str, type]:
    """遍历 Biome 的所有子类，构建 biome_id → 子类 的映射（仅执行一次）。"""
    cache: dict[str, type] = {}

    def collect(cls):
        for subclass in cls.__subclasses__():
            bid = getattr(subclass, 'biome_id', None)
            if bid is not None:
                cache[bid] = subclass
            collect(subclass)

    collect(Biome)
    cache.update(_load_worldgen_biome_classes())
    cache.setdefault("plains", PLAIN)
    return cache


def get_biome_by_id(biome_id: str) -> Biome:
    """
    根据 biome_id 获取群系实例。

    首次调用时自动遍历 Biome 子类树构建缓存，后续调用为 O(1) 查表。
    """
    global _BIOME_REGISTRY
    if _BIOME_REGISTRY is None:
        _BIOME_REGISTRY = _build_biome_id_cache()

    normalized_id = _normalize_biome_id(biome_id)
    cls = _BIOME_REGISTRY.get(normalized_id)
    if cls is not None:
        return cls()

    logging.warning(f"Unknown biome ID: {biome_id}, using plains colors.")
    return PLAIN()
