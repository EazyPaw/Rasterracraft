"""Small, reversible infrastructure for source-level Python Mods.

Gameplay classes remain the game's ordinary Python classes. See docs/mods.md.
"""

from .manager import ModError, ModManager

__all__ = ["ModError", "ModManager"]
