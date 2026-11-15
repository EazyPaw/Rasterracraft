"""RenderGlobal.renderSkyEnd's dark, repeating cubemap for the 2.5D camera."""
from functools import lru_cache

import numpy as np
import pygame


@lru_cache(maxsize=2)
def skybox(texture, width, height):
    # Build only on resize/resource changes, in a bounded small raster. The
    # skybox follows camera orientation, never camera position or world time.
    w = min(512, width)
    h = max(1, round(w * height / max(1, width)))
    horizontal = (np.arange(w, dtype=np.float32) + .5) / w * 3.2 - 1.6
    vertical = (.5 - (np.arange(h, dtype=np.float32) + .5) / h) * 3.2 * height / max(1, width)
    x, y = np.meshgrid(horizontal, vertical, indexing="ij")
    dominant = np.maximum(1, np.maximum(np.abs(x), np.abs(y)))
    side = np.abs(x) == dominant
    cap = (~side) & (np.abs(y) == dominant)
    u = np.where(side, np.sign(x) / dominant, x / dominant)
    v = np.where(cap, np.sign(y) / dominant, y / dominant)
    # The original renders all six faces with UV 0..16 and color (40,40,40).
    pixels = pygame.surfarray.array3d(texture)
    tx = ((u + 1) * 8 * texture.get_width()).astype(np.int32) % texture.get_width()
    ty = ((v + 1) * 8 * texture.get_height()).astype(np.int32) % texture.get_height()
    sampled = (pixels[tx, ty].astype(np.uint16) * 40 // 255).astype(np.uint8)
    native = pygame.surfarray.make_surface(sampled)
    return pygame.transform.scale(native, (max(1, width), max(1, height)))
