from collections import deque
from typing import List, Tuple, cast

import numpy as np

from resources.server.block_class import Block


def flood_fill_light_2d(
    light: np.ndarray,
    region_array: np.ndarray,
    z: int,
    sources: List[Tuple[int, int, int]],
) -> None:
    """
    基于 BFS 的二维光照扩散，支持固体阻挡与衰减。
    :param light: 要更新的光照数组（2D, uint8）
    :param region_array: 3D 方块数组 (x, y, z)
    :param z: 当前计算的层（通常为 0）
    :param sources: 光源列表 [(x, y, level), ...]
    """
    SX, SY = light.shape
    queue = deque()

    # 预处理：对于每个光源，若其位置光照更高则更新并入队
    for x, y, lvl in sources:
        if 0 <= x < SX and 0 <= y < SY and lvl > light[x, y]:
            light[x, y] = lvl
            queue.append((x, y, lvl))

    dirs = ((0, 1), (0, -1), (1, 0), (-1, 0))

    while queue:
        x, y, cur_level = queue.popleft()
        for dx, dy in dirs:
            nx, ny = x + dx, y + dy
            if 0 <= nx < SX and 0 <= ny < SY:
                blk: Block = cast(Block, region_array[nx, ny, z])
                new_level = cur_level - blk.light_attenuation
                if new_level > light[nx, ny]:
                    light[nx, ny] = new_level
                    # 剩余亮度 > 1 时才继续传播（剪枝优化）
                    if new_level > 1:
                        queue.append((nx, ny, new_level))