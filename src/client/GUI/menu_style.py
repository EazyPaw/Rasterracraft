"""Shared pixel metrics and drawing primitives for Minecraft-style menus."""

import pygame


def gui_scale(render):
    # Vanilla's automatic scale keeps at least a 320 x 240 logical canvas.
    return max(1, min(3, render.SCREEN_WIDTH // 320, render.SCREEN_HEIGHT // 240))


def draw_dirt(menu, *, list_rect=None):
    render = menu.render
    size = (render.SCREEN_WIDTH, render.SCREEN_HEIGHT)
    scale = gui_scale(render)
    key = (size, scale, tuple(list_rect) if list_rect is not None else None)
    if getattr(menu, "_dirt_style_key", None) != key:
        surface = render.create_surface(size, convert=True)
        dirt = render.client.resources_manager.get_texture_img("blocks.dirt")
        if dirt is None:
            surface.fill((28, 20, 14))
        else:
            # GuiScreen uses a 32 GUI-pixel repeat and a 64/255 tint;
            # GuiSlot uses the darker 32/255 tint inside the scrolling list.
            tile = pygame.transform.scale(dirt, (32 * scale, 32 * scale)).copy()
            tile.fill((64, 64, 64), special_flags=pygame.BLEND_RGB_MULT)
            for y in range(0, size[1], tile.get_height()):
                for x in range(0, size[0], tile.get_width()):
                    surface.blit(tile, (x, y))
        if list_rect is not None:
            surface.fill((128, 128, 128), list_rect, pygame.BLEND_RGB_MULT)
        menu._dirt_style_surface = surface
        menu._dirt_style_key = key
    render.blit(menu._dirt_style_surface, (0, 0))


def draw_list_edges(render, rect):
    """The short black fades that visually inset vanilla scrolling lists."""
    scale = gui_scale(render)
    fade = pygame.Surface((1, 4 * scale), pygame.SRCALPHA)
    for y in range(fade.get_height()):
        fade.set_at((0, y), (0, 0, 0, int(255 * (1 - y / fade.get_height()))))
    fade = pygame.transform.scale(fade, (rect.width, fade.get_height()))
    render.blit(fade, rect.topleft)
    render.blit(pygame.transform.flip(fade, False, True), (rect.x, rect.bottom - fade.get_height()))
    render.draw_line((64, 64, 64), rect.topleft, (rect.right, rect.top), 1)
    render.draw_line((64, 64, 64), (rect.x, rect.bottom), rect.bottomright, 1)


def draw_scrollbar(render, rect, offset, total):
    if total <= rect.height:
        return
    scale = gui_scale(render)
    track = pygame.Rect(rect.right - 6 * scale, rect.y, 6 * scale, rect.height)
    render.draw_rect((0, 0, 0), track)
    height = min(rect.height, max(16 * scale, rect.height * rect.height // total))
    y = rect.y + int(offset / max(1, total - rect.height) * (rect.height - height))
    thumb = pygame.Rect(track.x, y, track.width, height)
    render.draw_rect((128, 128, 128), thumb)
    render.draw_rect((192, 192, 192), thumb.inflate(-scale, -scale).move(-scale // 2, -scale // 2))


def widget_surface(texture, size, scale):
    """Nine-slice widgets so resizing preserves the pixel border thickness."""
    width, height = size
    source_w, source_h = texture.get_size()
    edge = min(2, source_w // 3, source_h // 3)
    target_edge = min(edge * scale, width // 3, height // 3)
    result = pygame.Surface(size, pygame.SRCALPHA)
    sx = (0, edge, source_w - edge, source_w)
    sy = (0, edge, source_h - edge, source_h)
    dx = (0, target_edge, width - target_edge, width)
    dy = (0, target_edge, height - target_edge, height)
    for row in range(3):
        for col in range(3):
            area = pygame.Rect(sx[col], sy[row], sx[col + 1] - sx[col], sy[row + 1] - sy[row])
            tile_size = (dx[col + 1] - dx[col], dy[row + 1] - dy[row])
            result.blit(pygame.transform.scale(texture.subsurface(area), tile_size), (dx[col], dy[row]))
    return result
