"""Ordered surface cache with constant-time memory accounting.

Recomputing the size of hundreds of cached character poses on every insert
made animated entities progressively more expensive after the cache filled.
"""

from collections import OrderedDict


class SurfaceCache(OrderedDict):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.byte_size = 0
        self.update(*args, **kwargs)

    @staticmethod
    def _bytes(surface):
        return surface.get_width() * surface.get_height() * surface.get_bytesize()

    def __setitem__(self, key, surface):
        size = self._bytes(surface)
        if key in self:
            self.byte_size -= self._bytes(self[key])
        super().__setitem__(key, surface)
        self.byte_size += size

    def __delitem__(self, key):
        size = self._bytes(self[key])
        super().__delitem__(key)
        self.byte_size -= size

    def popitem(self, last=True):
        key, surface = super().popitem(last=last)
        self.byte_size -= self._bytes(surface)
        return key, surface

    def pop(self, key, *default):
        if key in self:
            surface = self[key]
            del self[key]
            return surface
        if default:
            return default[0]
        raise KeyError(key)

    def clear(self):
        super().clear()
        self.byte_size = 0

    def update(self, *args, **kwargs):
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]
