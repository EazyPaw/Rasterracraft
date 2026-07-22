from collections import deque
from typing import List, Tuple, cast

import numpy as np

from resources.server.block_class import Block


_SOLID = np.frompyfunc(lambda block: bool(block.solid), 1, 1)
_ATTENUATION = np.frompyfunc(lambda block: int(block.light_attenuation), 1, 1)
_LIGHT_SOURCE = np.frompyfunc(lambda block: int(block.light_source), 1, 1)


def calculate_light_layers_2d(region_array: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Calculate sky and block light with the same fixed point as the BFS.

    Attribute extraction still visits each Python block once, but propagation
    runs as vectorized ndarray operations instead of tens of thousands of
    Python deque/cast iterations.  Level-one light intentionally does not
    propagate, matching ``flood_fill_light_2d`` exactly.
    """
    layer0 = region_array[:, :, 0]
    layer1 = region_array[:, :, 1]
    solid = _SOLID(layer0).astype(np.bool_)
    attenuation = _ATTENUATION(layer0).astype(np.int16)
    source0 = _LIGHT_SOURCE(layer0).astype(np.int16)
    source1 = _LIGHT_SOURCE(layer1).astype(np.int16)

    # A cell is a direct sky source only when no solid block exists at or
    # above it in the same column, matching the old top-down source scan.
    sky_exposed = ~np.logical_or.accumulate(solid[:, ::-1], axis=1)[:, ::-1]

    light = np.zeros((2, *solid.shape), dtype=np.int16)
    light[0, sky_exposed] = 15
    light[1] = np.minimum(15, source0 + source1)

    while True:
        propagating = np.where(light > 1, light, 0)
        neighbor = np.zeros_like(light)
        neighbor[:, 1:, :] = np.maximum(neighbor[:, 1:, :], propagating[:, :-1, :])
        neighbor[:, :-1, :] = np.maximum(neighbor[:, :-1, :], propagating[:, 1:, :])
        neighbor[:, :, 1:] = np.maximum(neighbor[:, :, 1:], propagating[:, :, :-1])
        neighbor[:, :, :-1] = np.maximum(neighbor[:, :, :-1], propagating[:, :, 1:])
        updated = np.maximum(light, np.maximum(0, neighbor - attenuation[None, :, :]))
        if np.array_equal(updated, light):
            break
        light = updated

    return light[0].astype(np.uint8), light[1].astype(np.uint8)


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
