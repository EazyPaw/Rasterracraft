"""Shared superflat settings, preset data, and preset-code parsing.

The client customization screens and the server generator intentionally use
this module as their single source of truth.  Layer order is bottom-to-top,
matching Minecraft's textual preset format.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from src.server import biome
from src.server.blocks import has_block_id


MAX_PRESET_CODE_LENGTH = 1230
MAX_WORLD_HEIGHT = 256

_BLOCK_ALIASES = {
    "grass": "grass_block",
    "snow_layer": "snow",
    "flowing_water": "water",
}
_LEGACY_BIOMES = {
    "0": "ocean",
    "1": "plains",
    "2": "desert",
    "3": "windswept_hills",
    "10": "frozen_ocean",
    "12": "snowy_plains",
    "24": "deep_ocean",
}
_IDENTIFIER = re.compile(r"^[a-z0-9_.-]+:[a-z0-9_./-]+$")


@dataclass(frozen=True, slots=True)
class FlatLayer:
    """One bottom-to-top layer in a superflat world."""

    height: int
    block_id: str

    def __post_init__(self) -> None:
        if not 1 <= int(self.height) <= MAX_WORLD_HEIGHT:
            raise ValueError("Layer height must be between 1 and 256")
        object.__setattr__(self, "height", int(self.height))
        object.__setattr__(self, "block_id", normalize_block_id(self.block_id))

    def to_code(self) -> str:
        identifier = f"minecraft:{self.block_id}"
        return identifier if self.height == 1 else f"{self.height}*{identifier}"

    def to_dict(self) -> dict[str, object]:
        return {"height": self.height, "block": self.block_id}


@dataclass(frozen=True, slots=True)
class SuperflatSettings:
    """Serializable settings consumed by :class:`ClassicFlat`."""

    layers: tuple[FlatLayer, ...]
    biome_id: str = "plains"
    structures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        layers = tuple(self.layers)
        if not layers:
            raise ValueError("A superflat world needs at least one layer")
        if sum(layer.height for layer in layers) > MAX_WORLD_HEIGHT:
            raise ValueError("Superflat layers exceed the 256 block build height")
        object.__setattr__(self, "layers", layers)
        object.__setattr__(self, "biome_id", normalize_biome_id(self.biome_id))
        object.__setattr__(
            self,
            "structures",
            tuple(
                dict.fromkeys(
                    str(value).strip()
                    for value in self.structures
                    if str(value).strip()
                )
            ),
        )

    @property
    def code(self) -> str:
        layers = ",".join(layer.to_code() for layer in self.layers)
        return f"{layers};minecraft:{self.biome_id}"

    def to_dict(self) -> dict[str, object]:
        return {
            "layers": [layer.to_dict() for layer in self.layers],
            "biome": self.biome_id,
            # Structures are currently metadata-only placeholders.
            "structures": list(self.structures),
            "preset_code": self.code,
        }

    @classmethod
    def from_dict(cls, value: object) -> "SuperflatSettings":
        if isinstance(value, SuperflatSettings):
            return value
        if isinstance(value, str):
            return parse_superflat_code(value)
        if not isinstance(value, dict):
            return DEFAULT_SUPERFLAT_SETTINGS

        raw_layers = value.get("layers")
        if isinstance(raw_layers, (list, tuple)):
            layers: list[FlatLayer] = []
            for entry in raw_layers:
                if not isinstance(entry, dict):
                    raise ValueError("Invalid superflat layer entry")
                layers.append(
                    FlatLayer(
                        int(entry.get("height", 1)),
                        str(entry.get("block", "air")),
                    )
                )
            raw_structures = value.get("structures", ())
            structures = raw_structures if isinstance(raw_structures, (list, tuple)) else ()
            return cls(
                tuple(layers),
                str(value.get("biome", "plains")),
                tuple(structures),
            )

        code = value.get("preset_code")
        if isinstance(code, str):
            parsed = parse_superflat_code(code)
            raw_structures = value.get("structures", parsed.structures)
            structures = (
                raw_structures
                if isinstance(raw_structures, (list, tuple))
                else parsed.structures
            )
            return cls(
                parsed.layers,
                parsed.biome_id,
                tuple(structures),
            )
        return DEFAULT_SUPERFLAT_SETTINGS


@dataclass(frozen=True, slots=True)
class SuperflatPreset:
    name: str
    icon_id: str
    settings: SuperflatSettings


def _strip_namespace(value: str) -> str:
    value = str(value).strip().lower()
    if ":" not in value:
        value = f"minecraft:{value}"
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid identifier: {value}")
    namespace, path = value.split(":", 1)
    if namespace != "minecraft":
        raise ValueError(f"Unsupported namespace: {namespace}")
    return path


def normalize_block_id(value: str) -> str:
    raw_id = _strip_namespace(value)
    block_id = _BLOCK_ALIASES.get(raw_id, raw_id)
    if not has_block_id(block_id):
        raise ValueError(f"Unknown block: minecraft:{block_id}")
    return block_id


def normalize_biome_id(value: str) -> str:
    raw = str(value).strip().lower()
    raw = _LEGACY_BIOMES.get(raw, raw)
    biome_id = _strip_namespace(raw)
    known = biome_id == biome.Void.biome_id or biome_id in biome.BIOME_PROFILES
    if not known:
        raise ValueError(f"Unknown biome: minecraft:{biome_id}")
    return biome_id


def parse_superflat_code(code: str) -> SuperflatSettings:
    """Parse modern ``layers;biome`` and legacy 1.8 preset strings.

    Whitespace is ignored as documented by Minecraft.  Legacy strings such as
    ``3;...;1;village`` remain accepted because the supplied visual reference
    uses that form, while newly serialized codes use the modern two-part form.
    """

    compact = re.sub(r"\s+", "", str(code))
    if not compact or len(compact) > MAX_PRESET_CODE_LENGTH:
        raise ValueError("Preset code must contain 1 to 1230 characters")

    parts = compact.split(";")
    legacy = len(parts) >= 3 and parts[0].isdigit()
    if legacy:
        parts = parts[1:]
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError("Preset code must use the layers;biome format")

    layers: list[FlatLayer] = []
    for token in parts[0].split(","):
        if not token:
            raise ValueError("Preset contains an empty layer")
        if "*" in token:
            count_text, block_text = token.split("*", 1)
            if not count_text.isdigit():
                raise ValueError(f"Invalid layer height: {count_text}")
            height = int(count_text)
        else:
            height = 1
            block_text = token
        layers.append(FlatLayer(height, block_text))

    structures: tuple[str, ...] = ()
    if legacy and len(parts) >= 3 and parts[2]:
        structures = tuple(
            value for value in re.split(r"[,(]", parts[2].replace(")", "")) if value
        )
    return SuperflatSettings(tuple(layers), parts[1], structures)


def _settings(
    layers: tuple[tuple[int, str], ...],
    biome_id: str,
    structures: tuple[str, ...] = (),
) -> SuperflatSettings:
    return SuperflatSettings(
        tuple(FlatLayer(height, block_id) for height, block_id in layers),
        biome_id,
        structures,
    )


SUPERFLAT_PRESETS: tuple[SuperflatPreset, ...] = (
    SuperflatPreset(
        "Classic Flat",
        "grass_block",
        _settings(
            ((1, "bedrock"), (2, "dirt"), (1, "grass_block")),
            "plains",
            ("village",),
        ),
    ),
    SuperflatPreset(
        "Tunnelers' Dream",
        "stone",
        _settings(
            ((1, "bedrock"), (230, "stone"), (5, "dirt"), (1, "grass_block")),
            "windswept_hills",
            ("stronghold", "mineshaft"),
        ),
    ),
    SuperflatPreset(
        "Water World",
        "water",
        _settings(
            (
                (1, "bedrock"),
                (64, "deepslate"),
                (5, "stone"),
                (5, "dirt"),
                (5, "sand"),
                (90, "water"),
            ),
            "deep_ocean",
            ("ocean_monument", "ocean_ruin", "shipwreck"),
        ),
    ),
    SuperflatPreset(
        "Overworld",
        "short_grass",
        _settings(
            ((1, "bedrock"), (59, "stone"), (3, "dirt"), (1, "grass_block")),
            "plains",
            ("pillager_outpost", "stronghold", "village", "mineshaft", "ruined_portal"),
        ),
    ),
    SuperflatPreset(
        "Snowy Kingdom",
        "snow",
        _settings(
            (
                (1, "bedrock"),
                (59, "stone"),
                (3, "dirt"),
                (1, "grass_block"),
                (1, "snow"),
            ),
            "snowy_plains",
            ("village", "igloo"),
        ),
    ),
    SuperflatPreset(
        "Bottomless Pit",
        "feather",
        _settings(
            ((2, "cobblestone"), (3, "dirt"), (1, "grass_block")),
            "plains",
            ("village",),
        ),
    ),
    SuperflatPreset(
        "Desert",
        "sand",
        _settings(
            ((1, "bedrock"), (3, "stone"), (52, "sandstone"), (8, "sand")),
            "desert",
            ("stronghold", "village", "desert_pyramid", "mineshaft"),
        ),
    ),
    SuperflatPreset(
        "Redstone Ready",
        "redstone_ore",
        _settings(
            ((1, "bedrock"), (3, "stone"), (116, "sandstone")),
            "desert",
        ),
    ),
    SuperflatPreset(
        "The Void",
        "air",
        _settings(((1, "air"),), "void"),
    ),
)

DEFAULT_SUPERFLAT_SETTINGS = SUPERFLAT_PRESETS[0].settings


BLOCK_DISPLAY_NAMES = {
    "air": "Air",
    "bedrock": "Bedrock",
    "cobblestone": "Cobblestone",
    "deepslate": "Deepslate",
    "dirt": "Dirt",
    "grass_block": "Grass Block",
    "sand": "Sand",
    "sandstone": "Sandstone",
    "snow": "Snow",
    "stone": "Stone",
    "water": "Water",
}
