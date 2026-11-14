"""Reversible, render-thread stages for client-only visual mods.

Registration never creates SDL/GL resources. Callbacks run for one stage at a
time under the mod call barrier, rather than locking the entire render loop.
"""

import logging
from queue import SimpleQueue

from src.mods.effects import barrier


class RenderExtensions:
    STAGES = frozenset({"events", "sky", "requirements", "background", "terrain", "world",
                        "overlay", "composite", "capture", "display_reset", "world_transform", "block_section", "pre_terrain", "block_texture", "precipitation"})

    def __init__(self):
        self._stages = {stage: () for stage in self.STAGES}
        self._failed = set()
        self._cleanup = SimpleQueue()
        self.material_revision = 0

    def invalidate_materials(self):
        """Invalidate baked sections without changing authoritative chunk data."""
        self.material_revision += 1

    def defer(self, callback):
        """Queue SDL/GL destruction for the window-owning thread."""
        self._cleanup.put(callback)

    def drain(self):
        with barrier.call():
            while not self._cleanup.empty():
                callback = self._cleanup.get_nowait()
                try:
                    callback()
                except Exception:
                    logging.exception("Render resource cleanup failed")

    def add(self, stage, key, callback, priority=0):
        if stage not in self.STAGES:
            raise ValueError(f"Unknown render stage: {stage}")
        if not callable(callback):
            raise TypeError("Render callback must be callable")
        entries = self._stages[stage]
        if any(entry[1] == key for entry in entries):
            raise ValueError(f"Duplicate render hook: {stage}/{key}")
        self._stages[stage] = tuple(sorted((*entries, (priority, key, callback)), key=lambda e: e[:2]))
        self._failed.discard((stage, key))
        if stage == "block_texture":
            self.invalidate_materials()

    def remove(self, stage, key):
        self._stages[stage] = tuple(e for e in self._stages[stage] if e[1] != key)
        self._failed.discard((stage, key))
        if stage == "block_texture":
            self.invalidate_materials()

    def run(self, stage, render, *args):
        if not self._stages[stage]:
            return
        with barrier.call():
            for _, key, callback in self._stages[stage]:
                if (stage, key) in self._failed:
                    continue
                try:
                    result = callback(render, *args)
                    if stage in {"sky", "requirements", "composite", "capture", "world_transform", "block_section", "block_texture", "precipitation"} and result is not None and result is not False:
                        return result
                except Exception:
                    # A broken visual mod must not terminate the game or flood
                    # the log every frame. Re-enabling it resets this breaker.
                    self._failed.add((stage, key))
                    logging.exception("Render hook disabled: %s/%s", stage, key)
