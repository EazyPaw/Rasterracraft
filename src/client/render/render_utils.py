# Commented and arranged by ChatGPT
"""
数学和渲染工具函数
============
提供渲染过程中使用的纯数学函数：插值、平滑、量化、颜色混合等。
所有函数均为无状态的纯函数，便于测试和复用。
"""

import pygame
from .constants import DAY_TICKS


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """将值限制在 [minimum, maximum] 范围内。

    :param value: 输入值
    :param minimum: 下限（默认 0.0）
    :param maximum: 上限（默认 1.0）

    :return: 限制后的值

    """
    return max(minimum, min(maximum, value))


def lerp(a: float, b: float, t: float) -> float:
    """线性插值：a + (b - a) * t。

    :param a: 起始值
    :param b: 结束值
    :param t: 插值参数（0.0 → 返回 a，1.0 → 返回 b）

    :return: 插值结果

    """
    return a + (b - a) * t


def lerp_color(
    a: tuple[int, int, int], b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    """在两个 RGB 颜色之间进行线性插值。

    :param a: 起始颜色 (R, G, B)
    :param b: 结束颜色 (R, G, B)
    :param t: 插值参数（自动钳制到 [0, 1]）

    :return: 插值后的 RGB 颜色元组

    """
    t = clamp(t)
    return (
        int(lerp(a[0], b[0], t)),
        int(lerp(a[1], b[1], t)),
        int(lerp(a[2], b[2], t)),
    )


def quantize_unit(value: float, levels: int) -> tuple[int, float]:
    """将 [0, 1] 范围内的值离散化为指定级数。

        用于减少缓存键的精度，提高缓存命中率。

    :param value: 输入值（自动钳制到 [0, 1]）
    :param levels: 离散化级数

    :return: (离散化索引, 离散化后的浮点值) 的元组

    """
    q = int(round(clamp(value) * levels))
    return q, q / levels


def quantize_color(color: tuple[int, int, int], step: int) -> tuple[int, ...]:
    """将 RGB 颜色各通道按步长取整，减少颜色空间用于缓存。

    :param color: 输入颜色 (R, G, B)
    :param step: 量化步长

    :return: 量化后的颜色元组，各通道均为 step 的整数倍

    """
    return tuple(
        min(255, max(0, int(round(channel / step) * step))) for channel in color
    )


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    """平滑阶跃函数（Hermite 插值）。

        在 [edge0, edge1] 范围内产生平滑的 S 形过渡曲线，
        利用 Hermite 多项式 3t² - 2t³ 实现 C¹ 连续。

    :param edge0: 下边缘
    :param edge1: 上边缘
    :param value: 输入值

    :return: [0, 1] 范围内的平滑过渡值

    """
    if edge0 == edge1:
        return 1.0 if value >= edge1 else 0.0
    x = clamp((value - edge0) / (edge1 - edge0))
    return x * x * (3.0 - 2.0 * x)


def cyclic_lerp_color(
    keyframes: list[tuple[float, tuple[int, int, int]]], time_value: float
) -> tuple[int, int, int]:
    """在循环关键帧之间进行颜色插值。

        支持跨日边界的循环插值（例如从 23000 刻过渡到 1000 刻）。

    :param keyframes: 关键帧列表 [(tick, color), ...]，tick 范围 [0, DAY_TICKS)
    :param time_value: 当前时间（刻），自动取模

    :return: 插值后的 RGB 颜色元组

    """
    time_value %= DAY_TICKS
    frames = sorted(keyframes, key=lambda item: item[0])
    for index, (tick, color) in enumerate(frames):
        next_tick, next_color = frames[(index + 1) % len(frames)]
        # 处理跨日循环：如果下一帧的 tick 更小，则加上一天
        end_tick = next_tick if next_tick > tick else next_tick + DAY_TICKS
        test_time = time_value if time_value >= tick else time_value + DAY_TICKS
        if tick <= test_time <= end_tick:
            progress = (test_time - tick) / max(end_tick - tick, 1)
            return lerp_color(color, next_color, smoothstep(0.0, 1.0, progress))
    return frames[0][1]


def draw_dashed_rect(surface, color, rect, dash_length=10, gap_length=5, width=1):
    """
    在指定surface上绘制一个虚线矩形框
    """
    x, y, w, h = rect
    # 1. 绘制上边 (水平)
    draw_dashed_line(surface, color, (x, y), (x + w, y), dash_length, gap_length, width)
    # 2. 绘制下边 (水平)
    draw_dashed_line(
        surface, color, (x, y + h), (x + w, y + h), dash_length, gap_length, width
    )
    # 3. 绘制左边 (垂直)
    draw_dashed_line(surface, color, (x, y), (x, y + h), dash_length, gap_length, width)
    # 4. 绘制右边 (垂直)
    draw_dashed_line(
        surface, color, (x + w, y), (x + w, y + h), dash_length, gap_length, width
    )


def draw_dashed_line(
    surf, color, start_pos, end_pos, dash_length=10, gap_length=5, width=1
):
    """
    在两点之间绘制一条虚线
    """
    # 计算线段的总长度和方向
    x1, y1 = start_pos
    x2, y2 = end_pos
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    if length == 0:
        return

    # 计算单位方向向量
    dx = (x2 - x1) / length
    dy = (y2 - y1) / length

    # 沿着线段一步步绘制
    current_dist = 0
    while current_dist < length:
        # 计算当前段的起始点
        start_x = x1 + dx * current_dist
        start_y = y1 + dy * current_dist
        # 计算当前段的终点 (虚线部分)
        end_dist = min(current_dist + dash_length, length)
        end_x = x1 + dx * end_dist
        end_y = y1 + dy * end_dist

        # 绘制一个实线小段
        pygame.draw.line(surf, color, (start_x, start_y), (end_x, end_y), width)

        # 前进到下一个虚线段的起始位置 (跳过间隙)
        current_dist += dash_length + gap_length
