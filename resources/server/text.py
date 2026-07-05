from enum import Enum

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

class Text:
    def __init__(self, text: str | list, color: TextColor = TextColor.WHITE):
        self.text: list[dict] = []
        if isinstance(text, str):
            self.text = [{"text": text, "color": color}]
        elif isinstance(text, list):
            self.text = text

    def __add__(self, other):
        if isinstance(other, Text):
            return Text(self.text + other.text)
        elif isinstance(other, str):
            text_list = self.text.copy()
            text_list.append({"text": other, "color": self.text[-1]["color"]})
            return Text(text_list)
        raise TypeError

    def append(self, other):
        if isinstance(other, Text):
            self.text.extend(other.text)
        elif isinstance(other, str):
            self.text.append({"text": other, "color": self.text[-1]["color"]})
            return
        else:
            raise TypeError

    def __iadd__(self, other):
        if isinstance(other, Text):
            self.text.extend(other.text)
        elif isinstance(other, str):
            self.text.append({"text": other, "color": self.text[-1]["color"]})
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
                result.append({"text": delimiter, "color": TextColor.WHITE})
            if isinstance(t, Text):
                result.extend(t.text)
            elif isinstance(t, str):
                result.append({"text": t, "color": TextColor.WHITE})
        self.text = result

    def to_plain_string(self) -> str:
        """将所有文本段拼接为纯字符串（忽略颜色）。"""
        return "".join(seg["text"] for seg in self.text)

    def to_dict(self) -> dict:
        """序列化为 msgpack-safe 字典（color 用枚举名存储）。"""
        return {
            "text": [
                {"text": seg["text"], "color": seg["color"].name}
                for seg in self.text
            ]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Text":
        """从字典反序列化 Text 对象。"""
        segments = []
        for seg in data.get("text", []):
            color = TextColor[seg["color"]]
            segments.append({"text": seg["text"], "color": color})
        return cls(segments)
