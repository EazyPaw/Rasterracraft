# Commented and arranged by ChatGPT
from enum import Enum


class BlockTag(Enum):
    GRASS_BLOCKS = "grass_blocks"
    ANIMALS_SPAWNABLE_ON = "animals_spawnable_on"


class DamageTag(Enum):
    BYPASSES_COOLDOWN = "bypasses_cooldown"
    BYPASSES_ARMOR = "bypasses_armor"
    BYPASSES_ENCHANTMENTS = "bypasses_enchantments"
    BYPASSES_EFFECTS = "bypasses_effects"
    IS_FIRE = "is_fire"


class ItemTag(Enum):
    COBBLESTONE = "cobblestone"
