"""Small, reversible infrastructure for source-level Python Mods.

Gameplay classes remain the game's ordinary Python classes. See docs/mods.md.
"""

from .manager import ModError, ModManager
from .effects import ClientModContext, ModContext, PatchFacade, ServerModContext
from .manifest import ModInfo
from .types import ModSide, NetworkMod, SideRequirement

__all__ = ["ModError", "ModManager", "ModInfo", "ModContext", "ClientModContext",
           "ServerModContext", "PatchFacade", "ModSide", "SideRequirement", "NetworkMod"]
