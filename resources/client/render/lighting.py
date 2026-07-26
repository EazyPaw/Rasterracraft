# Commented and arranged by ChatGPT
"""
光照工具函数
============
提供世界坐标光照查询、四角光照插值、纹理染色等功能。
"""

from typing import Any

import numpy as np
import pygame


def get_light_level(
    light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]], x: int, y: int
) -> float:
    """获取世界坐标 (x, y) 处的归一化光照值。

    :param light_map: 2D光照数组}
    :type light_map: 光照图字典 {区块x索引
    :param x: 世界 X 坐标
    :param y: 世界 Y 坐标

    :return: 归一化光照值 [0.0, 1.0]

    """
    rx = x // 16
    chunk_light_map = light_map.get(rx)

    if chunk_light_map is None:
        return 0.0

    local_x = x % 16
    if y < 0:
        return 0.0

    if y >= chunk_light_map.shape[1]:
        return 1.0  # 高于区块范围视为完全明亮

    try:
        light = chunk_light_map[local_x, y]
        return light / 15.0
    except IndexError:
        return 0.0


def get_light_levels_at(
    light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]], x: int, y: int
) -> tuple[float, float, float, float]:
    """获取方块四个角落的平滑光照值。

        采用"边-角-边-中心"四点平均算法，对 (x, y) 及其
        8 邻域共 9 个采样点进行平均，生成四个角落的值。

    :param light_map: 光照图字典
    :param x: 世界 X 坐标
    :param y: 世界 Y 坐标

    :return: (左上, 右上, 左下, 右下) 四个角落的归一化光照值

    """
    center = get_light_level(light_map, x, y)
    # 左上角：取左侧、左上、上方、中心四点的平均值
    tl = (
        get_light_level(light_map, x - 1, y)
        + get_light_level(light_map, x - 1, y + 1)
        + get_light_level(light_map, x, y + 1)
        + center
    ) / 4.0
    # 右上角
    tr = (
        get_light_level(light_map, x, y + 1)
        + get_light_level(light_map, x + 1, y + 1)
        + get_light_level(light_map, x + 1, y)
        + center
    ) / 4.0
    # 左下角
    bl = (
        get_light_level(light_map, x - 1, y)
        + get_light_level(light_map, x - 1, y - 1)
        + get_light_level(light_map, x, y - 1)
        + center
    ) / 4.0
    # 右下角
    br = (
        get_light_level(light_map, x, y - 1)
        + get_light_level(light_map, x + 1, y - 1)
        + get_light_level(light_map, x + 1, y)
        + center
    ) / 4.0
    return tl, tr, bl, br


def color_tint(
    image: pygame.Surface, new_color: tuple[int, int, int]
) -> pygame.Surface:
    """使用混合模式对图像进行染色（保持原始 Alpha 通道）。

        两步混合法：
        1. BLEND_RGBA_MULT → 将 RGB 通道归零，保留原始 Alpha
        2. BLEND_RGBA_ADD → 叠加新颜色

    :param image: 原始图像 Surface
    :param new_color: 目标颜色 (R, G, B)

    :return: 染色后的新 Surface（原始图像不会被修改）

    """
    tinted_image = image.copy()
    # 第一步：用乘法混合将 RGB 归零，保留 Alpha 通道
    tinted_image.fill((0, 0, 0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # 第二步：用加法混合叠加新颜色（Alpha=0 不影响透明通道）
    tinted_image.fill((*new_color, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tinted_image
