"""Bounded, shared CPU surfaces for the End portal's layered star field.

Sixteen additive depth layers follow the vanilla renderer's seed and palette.
Compose at 192x64, animate at 6.7 Hz and share three seamless tile phases;
neither per-pixel Python work nor per-portal textures are needed each frame.
"""
from functools import lru_cache
from collections import OrderedDict
import random

import pygame

_scaled_cache = OrderedDict()
_scaled_bytes = 0
_MAX_SCALED_BYTES = 8 * 1024 * 1024


def _scaled(key, build):
    global _scaled_bytes
    if key in _scaled_cache:
        _scaled_cache.move_to_end(key)
        return _scaled_cache[key]
    surface = build()
    byte_size = surface.get_pitch() * surface.get_height()
    while _scaled_cache and (_scaled_bytes + byte_size > _MAX_SCALED_BYTES or len(_scaled_cache) >= 128):
        _, old = _scaled_cache.popitem(last=False)
        _scaled_bytes -= old.get_pitch() * old.get_height()
    if byte_size <= _MAX_SCALED_BYTES:
        _scaled_cache[key] = surface
        _scaled_bytes += byte_size
    return surface


@lru_cache(maxsize=96)
def _star_field(frame):
    rng = random.Random(31100)
    surface = pygame.Surface((192, 64), pygame.SRCALPHA)
    surface.fill((2, 8, 12, 255), (0, 16, 192, 48))
    for layer in range(16):
        strength = 1 / (17 - layer)
        color = (int((rng.random() * .5 + .1) * strength * 255),
                 int((rng.random() * .5 + .4) * strength * 255),
                 int((rng.random() * .5 + .5) * strength * 255), 255)
        stars = pygame.Surface((192, 48))
        for _ in range(18):
            # Integer periods make the animation wrap continuously.
            x = (rng.randrange(192) + frame * (1 + layer % 3) * 2) % 192
            y = (rng.randrange(48) + frame * (1 + layer % 2)) % 48
            pygame.draw.rect(stars, color, (x, y, 2 + layer // 7, 2 + layer // 10))
        surface.blit(stars, (0, 16), special_flags=pygame.BLEND_RGB_ADD)
    return surface


def portal_texture(size, phase, frame):
    def build():
        native = _star_field(frame).subsurface((phase * 64, 0, 64, 64))
        return pygame.transform.scale(native, (max(1, size), max(1, size)))
    return _scaled(("portal", size, phase, frame), build)


def frame_texture(resources, size, eye, facing):
    return _scaled(("frame", resources, size, eye, facing),
                   lambda: _build_frame(resources, size, eye, facing))


def _build_frame(resources, size, eye, facing):
    size = max(1, size)
    native = pygame.Surface((16, 16), pygame.SRCALPHA)
    side = resources.get_texture_img("blocks.endframe_side")
    top = resources.get_texture_img("blocks.endframe_top")
    if side is not None:
        native.blit(pygame.transform.scale(side, (16, 16)), (0, 3))
    else:
        native.fill((71, 100, 77), (0, 3, 16, 13))
    if top is not None:
        native.blit(pygame.transform.scale(top, (16, 4)), (0, 3))
    if eye:
        texture = resources.get_texture_img("blocks.endframe_eye")
        if texture is not None:
            native.blit(pygame.transform.scale(texture, (8, 4)), (4, 0))
        else:
            pygame.draw.ellipse(native, (58, 181, 146), (4, 0, 8, 4))
        pygame.draw.rect(native, (7, 33, 29), (7, 0, 2, 3))
    # Small inset on the inward edge makes creative placement direction visible.
    if facing:
        pygame.draw.line(native, (155, 182, 115),
                         (13 if facing > 0 else 2, 4), (13 if facing > 0 else 2, 6))
    return pygame.transform.scale(native, (size, size))
