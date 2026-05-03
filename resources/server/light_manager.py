import logging
from collections import deque
from typing import List, Tuple

import numpy as np

from resources.server.block_class import Block


def flood_fill_light_2d(
    light: np.ndarray,          # 形状 (SX, SY) 的 uint8 光照图，函数会就地修改
    region_array: np.ndarray,   # 形状 (SX, SY, SZ) 的 Block 数组
    z: int,                     # 参与光照计算的 z 层
    sources: List[Tuple[int, int, int]],   # 光源列表，每个元素为 (x, y, level)
    max_light: int = 15
) -> None:
    """
    基于 BFS 的二维光照扩散，极致效率版。

    参数
    ----------
    light : np.ndarray
        会被就地修改的光照数组，dtype 为 uint8。
    region_array : np.ndarray
        三维方块数组，每个元素为 Block 对象。
    z : int
        要读取方块属性的层索引。
    sources : List[Tuple[int, int, int]]
        光源种子列表，每项格式 (x, y, level)。
    max_light : int
        最高亮度值（包含），默认为 15。
    """
    SX, SY = light.shape
    # ---------------- 1. 快速构建只读的衰减/阻挡矩阵 ----------------
    # 取出本层所有方块引用（视图）
    blocks_2d = region_array[:, :, z]                # shape (SX, SY)
    # 用列表推导获得纯 Python 列表，但为了速度，我们直接遍历 numpy 数组并提取属性。
    # 创建布尔阻挡矩阵（True 表示完全阻光）和衰减矩阵。
    # 注意：solid 为 True 的方块完全阻光；非固体方块按 light_attenuation 衰减。
    opaque = np.zeros((SX, SY), dtype=bool)
    atten = np.zeros((SX, SY), dtype=np.uint8)

    # 预提取所有方块的属性（这里用双层循环，仅在函数入口执行一次）
    for x in range(SX):
        for y in range(SY):
            blk: Block = blocks_2d[x, y]
            opaque[x, y] = blk.solid
            # 对于非固体，衰减值至少为 1，防止负衰减
            atten[x, y] = max(1, blk.light_attenuation)

    # ---------------- 2. 初始化光源，保证光照 >= 原有值 ----------------
    queue = deque()
    for x, y, lvl in sources:
        # 边界检查
        if 0 <= x < SX and 0 <= y < SY:
            # 如果光源方块本身就是固体，它依然可以发光，但自身光必须能存在
            # 这里我们不阻止光源方块被设置，但固体方块在邻居传播时会被阻挡
            if lvl > light[x, y]:
                light[x, y] = lvl
                queue.append((x, y, lvl))

    # ---------------- 3. BFS 主循环 ----------------
    # 方向偏移 (dx, dy)，上下左右
    dirs = ( (0, 1), (0, -1), (1, 0), (-1, 0) )

    while queue:
        x, y, cur_level = queue.popleft()
        # 当前亮度能传递到邻居所需的最低值
        next_min_level = cur_level - 1           # 第一步基本衰减
        if next_min_level <= 0:
            continue

        for dx, dy in dirs:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < SX and 0 <= ny < SY:
                # 完全阻挡
                if opaque[nx, ny]:
                    continue
                # 计算传入邻居后的光强
                new_level = cur_level - atten[nx, ny]
                if new_level <= 0:
                    continue
                # 只有严格更高时才更新并入队
                if new_level > light[nx, ny]:
                    light[nx, ny] = new_level
                    queue.append((nx, ny, new_level))