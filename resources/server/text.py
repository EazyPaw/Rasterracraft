from enum import Enum
import math

class TextColor(Enum):
    # 标准 16 色
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)
    DARK_BLUE = (0, 0, 170)
    DARK_GREEN = (0, 170, 0)
    DARK_AQUA = (0, 170, 170)
    DARK_RED = (170, 0, 0)
    DARK_PURPLE = (170, 0, 170)
    GOLD = (255, 170, 0)
    GRAY = (170, 170, 170)
    DARK_GRAY = (85, 85, 85)
    BLUE = (85, 85, 255)
    GREEN = (85, 255, 85)
    AQUA = (85, 255, 255)
    RED = (255, 85, 85)
    LIGHT_PURPLE = (255, 85, 255)
    YELLOW = (255, 255, 85)

    # 仅基岩版（BE）材料颜色
    MINECOIN_GOLD = (221, 214, 5)
    MATERIAL_QUARTZ = (227, 212, 209)
    MATERIAL_IRON = (206, 202, 202)
    MATERIAL_NETHERITE = (68, 58, 59)
    MATERIAL_REDSTONE = (151, 22, 7)
    MATERIAL_COPPER = (180, 104, 77)
    MATERIAL_GOLD = (222, 177, 45)
    MATERIAL_EMERALD = (17, 160, 54)
    MATERIAL_DIAMOND = (44, 186, 168)
    MATERIAL_LAPIS = (33, 73, 123)
    MATERIAL_AMETHYST = (154, 92, 198)
    MATERIAL_RESIN = (235, 114, 20)
    PARTY_BLUE_COLOR = (140, 179, 255)


def _is_rgb_color(value) -> bool:
    return (
        isinstance(value, (tuple, list))
        and len(value) == 3
        and all(isinstance(component, int) and 0 <= component <= 255 for component in value)
    )


def parse_solid_text_color(value) -> tuple[int, int, int]:
    """Resolve a named, RGB, integer, or string hex color to RGB."""
    if isinstance(value, TextColor):
        return value.value
    if _is_rgb_color(value):
        return tuple(value)
    if isinstance(value, int):
        if not 0 <= value <= 0xFFFFFF:
            raise ValueError("hex text color must be between 0x000000 and 0xFFFFFF")
        return value >> 16 & 0xFF, value >> 8 & 0xFF, value & 0xFF
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("#"):
            raw = raw[1:]
        elif raw.lower().startswith("0x"):
            raw = raw[2:]
        if len(raw) == 3:
            raw = "".join(character * 2 for character in raw)
        if len(raw) != 6:
            raise ValueError("string text colors must use RGB hex, such as '#55AAFF'")
        try:
            packed = int(raw, 16)
        except ValueError as error:
            raise ValueError(f"invalid hex text color: {value!r}") from error
        return (packed >> 16 & 0xFF, packed >> 8 & 0xFF, packed & 0xFF)
    raise TypeError(f"unsupported text color: {value!r}")


def is_gradient_text_color(value) -> bool:
    """Return whether *value* is a tuple of two or more valid color stops."""
    if not isinstance(value, tuple) or _is_rgb_color(value) or len(value) < 2:
        return False
    try:
        for stop in value:
            parse_solid_text_color(stop)
    except (TypeError, ValueError):
        return False
    return True


def normalize_text_color(value):
    """Return either one RGB tuple or a tuple of RGB gradient stops."""
    if is_gradient_text_color(value):
        return tuple(parse_solid_text_color(stop) for stop in value)
    return parse_solid_text_color(value)


def gradient_text_color_at(stops, progress: float) -> tuple[int, int, int]:
    """Interpolate through all gradient stops in their declared order."""
    normalized = normalize_text_color(stops)
    if _is_rgb_color(normalized):
        return normalized
    progress = max(0.0, min(1.0, float(progress)))
    scaled = progress * (len(normalized) - 1)
    left_index = min(len(normalized) - 2, int(math.floor(scaled)))
    local_progress = scaled - left_index
    left = normalized[left_index]
    right = normalized[left_index + 1]
    return tuple(
        round(start + (end - start) * local_progress)
        for start, end in zip(left, right)
    )


def darken_text_color(value, strength: float):
    """Apply the same shadow multiplier to a solid color or every stop."""
    normalized = normalize_text_color(value)
    strength = max(0.0, float(strength))

    def darken(rgb):
        return tuple(max(0, min(255, round(component * strength))) for component in rgb)

    if _is_rgb_color(normalized):
        return darken(normalized)
    return tuple(darken(stop) for stop in normalized)


def _serialize_color_stop(value) -> str:
    if isinstance(value, TextColor):
        return value.name
    red, green, blue = parse_solid_text_color(value)
    return f"#{red:02X}{green:02X}{blue:02X}"


def serialize_text_color(value):
    """Convert a color specification to a msgpack-safe representation."""
    if isinstance(value, TextColor):
        return value.name  # Preserve the existing wire format for named colors.
    if is_gradient_text_color(value):
        return {"gradient": [_serialize_color_stop(stop) for stop in value]}
    return _serialize_color_stop(value)


def _deserialize_color_stop(value):
    if isinstance(value, str) and value in TextColor.__members__:
        return TextColor[value]
    if isinstance(value, (str, int)) or _is_rgb_color(value):
        red, green, blue = parse_solid_text_color(value)
        return red << 16 | green << 8 | blue
    raise TypeError(f"invalid serialized text color: {value!r}")


def deserialize_text_color(value):
    """Read both the legacy enum-name format and custom color formats."""
    if isinstance(value, dict) and "gradient" in value:
        stops = value["gradient"]
        if not isinstance(stops, (tuple, list)) or len(stops) < 2:
            raise ValueError("a text gradient needs at least two color stops")
        return tuple(_deserialize_color_stop(stop) for stop in stops)
    return _deserialize_color_stop(value)

class Text:
    """Styled text with named, RGB/hex, or ordered gradient colors.

    Examples::

        Text("custom", 0x32E6A1)
        Text("custom", "#32E6A1")
        Text("gradient", (TextColor.AQUA, "#FF40C8", 0xFFAA00))
    """

    def __init__(
        self,
        text: str | list,
        color: TextColor | int | str | tuple = TextColor.WHITE,
        bold: bool = False,
    ):
        self.text: list[dict] = []
        if isinstance(text, str):
            self.text = [{"text": text, "color": color, "bold": bold}]
        elif isinstance(text, list):
            self.text = text

    def __add__(self, other):
        if isinstance(other, Text):
            return Text(self.text + other.text)
        elif isinstance(other, str):
            text_list = self.text.copy()
            text_list.append({"text": other, "color": self.text[-1]["color"], "bold": self.text[-1].get("bold", False)})
            return Text(text_list)
        raise TypeError

    def append(self, other):
        if isinstance(other, Text):
            self.text.extend(other.text)
        elif isinstance(other, str):
            self.text.append({"text": other, "color": self.text[-1]["color"], "bold": self.text[-1].get("bold", False)})
            return
        else:
            raise TypeError

    def __iadd__(self, other):
        if isinstance(other, Text):
            self.text.extend(other.text)
        elif isinstance(other, str):
            self.text.append({"text": other, "color": self.text[-1]["color"], "bold": self.text[-1].get("bold", False)})
        return self

    def join(self, *args, delimiter=""):
        """拼接多个 Text 对象，用 delimiter 分隔。

        Parameters
        ----------
        *args : Text
            要拼接的 Text 对象。
        delimiter : str
            分隔符字符串（放在每两个 Text 之间）。
        """
        result = []
        for i, t in enumerate(args):
            if i > 0 and delimiter:
                result.append({"text": delimiter, "color": TextColor.WHITE, "bold": False})
            if isinstance(t, Text):
                result.extend(t.text)
            elif isinstance(t, str):
                result.append({"text": t, "color": TextColor.WHITE, "bold": False})
        self.text = result

    def to_plain_string(self) -> str:
        """将所有文本段拼接为纯字符串（忽略颜色）。"""
        return "".join(seg["text"] for seg in self.text)

    def to_dict(self) -> dict:
        """序列化为 msgpack-safe 字典，兼容命名色、十六进制和渐变色。"""
        return {
            "text": [
                {
                    "text": seg["text"],
                    "color": serialize_text_color(seg.get("color", TextColor.WHITE)),
                    "bold": seg.get("bold", False),
                }
                for seg in self.text
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Text":
        """从字典反序列化 Text 对象。"""
        segments = []
        for seg in data.get("text", []):
            color = deserialize_text_color(seg.get("color", "WHITE"))
            bold = seg.get("bold", False)
            segments.append({"text": seg["text"], "color": color, 'bold': bold})
        return cls(segments)
