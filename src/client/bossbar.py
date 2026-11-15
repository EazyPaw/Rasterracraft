"""Shared boss HUD: keyed updates and the resource pack's boss_bar sprites."""
from dataclasses import dataclass
from functools import lru_cache
from threading import RLock

import pygame

from src.client.resources_manager import transkey


COLORS = frozenset(("pink", "blue", "red", "green", "yellow", "purple", "white"))


@dataclass(frozen=True)
class BossBar:
    uuid: str
    name: str
    health: float
    max_health: float
    color: str = "pink"

    @property
    def progress(self):
        return max(0.0, min(1.0, self.health / max(1.0, self.max_health)))


@lru_cache(maxsize=42)
def _scaled_texture(sheet, scale):
    return pygame.transform.scale(sheet, (182 * scale, 5 * scale))


class BossBarOverlay:
    """A dragon, a wither, or multiple bosses use the same packet and renderer."""
    def __init__(self):
        self._bars = {}
        self._lock = RLock()

    def snapshot(self):
        with self._lock:
            return tuple(self._bars.values())

    def update(self, packet):
        uuid = packet.get("uuid")
        if not uuid:
            return
        with self._lock:
            if not packet.get("active") or packet.get("health", 0) <= 0:
                self._bars.pop(uuid, None)
                return
            color = packet.get("color", "pink")
            self._bars[uuid] = BossBar(uuid, packet.get("name", ""),
                                      float(packet["health"]), float(packet.get("max_health", 1)),
                                      color if color in COLORS else "pink")

    def draw(self, render):
        scale = max(1, min(3, render.SCREEN_WIDTH // 480))
        width, height = 182 * scale, 5 * scale
        x, y = (render.SCREEN_WIDTH - width) // 2, 12 * scale
        for bar in self.snapshot():
            prefix = "gui.sprites.boss_bar." + bar.color
            resources = render.client.resources_manager
            background = _scaled_texture(resources.get_texture_img(prefix + "_background"), scale)
            foreground = _scaled_texture(resources.get_texture_img(prefix + "_progress"), scale)
            render.screen.blit(background, (x, y))
            filled = min(width, int(bar.progress * width))
            if filled:
                # Clip the full progress texture, preserving its pixel pattern.
                render.screen.blit(foreground, (x, y), (0, 0, filled, height))
            label = transkey(bar.name)
            size = 10 * scale
            text_width = render.get_font(size).size(label)[0]
            render.render_text(label, ((render.SCREEN_WIDTH - text_width) // 2, y - 10 * scale),
                               (255, 255, 255), size, True)
            y += 19 * scale
            if y >= render.SCREEN_HEIGHT // 3:
                break


def draw_boss_bars(render):
    render.client_world.boss_bars.draw(render)
