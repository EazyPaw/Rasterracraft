import logging

from main import client

class Biome:
    id = "null"
    name = "null"
    temperature = 0.5
    downfall = 0.5
    grass_color = (0, 0, 0)
    foliage_color = (0, 0, 0)
    
    def __init__(self):
        """
        初始化生物群系，根据温度和降水从颜色图中获取草和树叶的颜色。
        """
        self.grass_color = self._get_color_from_colormap("colormap.grass")
        self.foliage_color = self._get_color_from_colormap("colormap.foliage")

    def _get_color_from_colormap(self, colormap_name: str) -> tuple[int, int, int]:
        """
        从颜色图中获取对应坐标的 RGB 颜色值。
        
        :param colormap_name: 颜色图名称（如 "colormap.grass" 或 "colormap.foliage"）
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

class PLAIN(Biome):
    id = "plain"
    name = "plain"
    temperature = 0.8
    downfall = 0.4
