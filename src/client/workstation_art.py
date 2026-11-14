"""Fixed workstation UV sprites and software-projected ModelBook geometry."""
import math

import numpy as np
import pygame


def textured_quad(target, texture, points):
    """Nearest-neighbour affine texture projection onto a parallelogram."""
    origin, right, _, bottom = (np.asarray(point, dtype=float) for point in points)
    matrix = np.column_stack((right - origin, bottom - origin))
    if abs(np.linalg.det(matrix)) < .01:
        return
    bounds = pygame.Rect(math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points)),
                         math.ceil(max(p[0] for p in points)) - math.floor(min(p[0] for p in points)),
                         math.ceil(max(p[1] for p in points)) - math.floor(min(p[1] for p in points)))
    bounds = bounds.clip(target.get_rect())
    if not bounds.width or not bounds.height:
        return
    xx, yy = np.meshgrid(np.arange(bounds.x, bounds.right) + .5,
                         np.arange(bounds.y, bounds.bottom) + .5, indexing="ij")
    uv = np.linalg.inv(matrix) @ np.stack((xx - origin[0], yy - origin[1])).reshape(2, -1)
    visible = ((uv >= 0) & (uv < 1)).all(axis=0).reshape(bounds.size)
    tx = np.clip((uv[0] * texture.get_width()).astype(int), 0, texture.get_width() - 1)
    ty = np.clip((uv[1] * texture.get_height()).astype(int), 0, texture.get_height() - 1)
    patch = pygame.Surface(bounds.size, pygame.SRCALPHA)
    rgb = pygame.surfarray.pixels3d(patch)
    rgb[:] = pygame.surfarray.array3d(texture)[tx, ty].reshape((*bounds.size, 3))
    del rgb
    alpha = pygame.surfarray.pixels_alpha(patch)
    alpha[:] = pygame.surfarray.array_alpha(texture)[tx, ty].reshape(bounds.size) * visible
    del alpha
    target.blit(patch, bounds)


def render_anvil(resources, damage, size):
    """Assemble the long side at native 16px, like the chest's fixed UVs."""
    damage = max(0, min(2, int(damage)))
    body = resources.get_texture_img("blocks.anvil_base")
    top = resources.get_texture_img(f"blocks.anvil_top_damaged_{damage}")
    cache = getattr(resources, "_anvil_projection_cache", None)
    if cache is None:
        cache = resources._anvil_projection_cache = {}
    key = (damage, int(size), body, top)
    if key in cache:
        return cache[key]
    canvas = pygame.Surface((16, 16), pygame.SRCALPHA)
    # West-face UVs (u, v, width, height), rotated clockwise into Z/Y.
    # Screen-space silhouette matches BlockSprite_anvil.webp exactly.
    for uv, position in (((0, 2, 4, 12), (2, 12)),
                         ((4, 3, 1, 10), (3, 11)),
                         ((5, 4, 5, 8), (4, 6)),
                         ((10, 0, 6, 16), (0, 0))):
        face = pygame.transform.rotate(body.subsurface(tuple(round(v * body.get_width() / 16) for v in uv)), -90)
        face = pygame.transform.scale(face, (uv[3], uv[2]))
        canvas.blit(face, position)
    # Keep a one-pixel rim to identify the damaged top without changing
    # the orthographic silhouette or shortening any of the four sections.
    cap = pygame.transform.rotate(top.subsurface((round(3 * top.get_width() / 16), 0,
                                                 round(10 * top.get_width() / 16), top.get_height())), 90)
    canvas.blit(pygame.transform.scale(cap, (16, 1)), (0, 0))
    result = pygame.transform.scale(canvas, (max(1, int(size)), max(1, int(size))))
    cache[key] = result
    if len(cache) > 48:
        cache.pop(next(iter(cache)))
    return result


def render_enchanting_table(resources, size, frame):
    """A 3/4-height table with an open book bobbing above its solid top."""
    side = resources.get_texture_img("blocks.enchanting_table_side")
    atlas = resources.get_texture_img("entity.enchanting_table_book")
    frame = int(frame) % 80
    size = max(1, round(size))
    cache = getattr(resources, "_enchanting_table_cache", None)
    if cache is None:
        cache = resources._enchanting_table_cache = {}
    key = (side, atlas, size, frame)
    if key in cache:
        return cache[key]
    # Eight pixels of transparent overhang are accounted for by the world
    # renderer's section padding. The bottom remains the block's world Y.
    native = pygame.Surface((64, 96), pygame.SRCALPHA)
    native.blit(pygame.transform.scale(side, (64, 64)), (0, 32))
    book = pygame.transform.scale(render_book(resources, 1, frame // 2), (60, 40))
    bob = round(math.sin(frame * math.tau / 80) * 4)
    native.blit(book, (2, 8 + bob))
    result = pygame.transform.scale(native, (size, max(1, round(size * 1.5))))
    cache[key] = result
    if len(cache) > 320:
        cache.pop(next(iter(cache)))
    return result


def render_book(resources, opening, page):
    """Project ModelBook's covers, spine, page blocks and two flipping pages."""
    atlas = resources.get_texture_img("entity.enchanting_table_book")
    opening = max(0, min(10, round(opening * 10)))
    page = int(page) % 20
    key = (atlas, opening, page)
    cache = getattr(resources, "_enchanting_book_cache", None)
    if cache is None:
        cache = resources._enchanting_book_cache = {}
    if key in cache:
        return cache[key]
    result = pygame.Surface((52, 34), pygame.SRCALPHA)
    opened = opening / 10
    angle = 1.25 * opened
    camera = -(1 - opened) * math.pi / 2 - math.pi / 2
    faces = []
    def project(x, y, z, rotation=0, offset=(0, 0, 0)):
        x, z = x * math.cos(rotation) + z * math.sin(rotation), -x * math.sin(rotation) + z * math.cos(rotation)
        x, y, z = x + offset[0], y + offset[1], z + offset[2]
        # GuiEnchantment applies Rx(180), Ry(camera), Rx(20), Rz(180).
        # Screen Y then reverses OpenGL Y. Omitting Rx(180) opens the
        # book away from the viewer and reverses its cover/page occlusion.
        y, z = -y, -z
        x, z = x * math.cos(camera) + z * math.sin(camera), -x * math.sin(camera) + z * math.cos(camera)
        y, z = y * math.cos(math.radians(20)) - z * math.sin(math.radians(20)), y * math.sin(math.radians(20)) + z * math.cos(math.radians(20))
        return 26 - x * 2.5, 17 + y * 2.5, z
    def leaf(uv, bounds, rotation, offset=(0, 0, 0), shade=255):
        x0, y0, x1, y1 = bounds
        texture = atlas.subsurface(uv).copy()
        texture.fill((shade, shade, shade, 255), special_flags=pygame.BLEND_RGBA_MULT)
        points = [project(x, y, 0, rotation, offset) for x, y in ((x0,y0), (x1,y0), (x1,y1), (x0,y1))]
        faces.append((sum(point[2] for point in points) / 4, texture, [point[:2] for point in points]))
    leaf((0, 0, 6, 10), (-6, -5, 0, 5), math.pi + angle, (0, 0, -1))
    leaf((16, 0, 6, 10), (0, -5, 6, 5), -angle, (0, 0, 1))
    leaf((12, 0, 2, 10), (-1, -5, 1, 5), math.pi / 2)
    shift = math.sin(angle)
    leaf((1, 11, 5, 8), (0, -4, 5, 4), angle, (shift, 0, -.99), 225)
    leaf((13, 11, 5, 8), (0, -4, 5, 4), -angle, (shift, 0, -.01))
    if opened > .1:
        for phase in (page / 20, (page / 20 + .5) % 1):
            flip = max(0, min(1, phase * 1.6 - .3))
            leaf((24, 10, 5, 8), (0, -4, 5, 4), angle - angle * 2 * flip, (shift, 0, 0), 245)
    for _, texture, points in sorted(faces, key=lambda face: face[0]):
        textured_quad(result, texture, points)
    cache[key] = result
    if len(cache) > 220:
        cache.pop(next(iter(cache)))
    return result
