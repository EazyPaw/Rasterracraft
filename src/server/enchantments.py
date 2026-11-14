"""Server-authoritative enchantment definitions and registry.

Item stacks only persist enchantment ids and levels.  Behaviour, applicability,
tooltip names, and attribute contributions live here so future enchanting
sources (commands, tables, anvils, loot) all use the same rules.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from src.server.tags import DamageTag


def normalize_enchantment_id(value: str) -> str:
    value = str(value).strip().lower()
    if ":" not in value:
        value = f"minecraft:{value}"
    namespace, path = value.split(":", 1)
    if not namespace or not path:
        raise ValueError(f"invalid enchantment id: {value!r}")
    return f"{namespace}:{path}"


AttributeFactory = Callable[[int], Iterable[Mapping]]
ApplicabilityPredicate = Callable[[object], bool]
DamageProtectionFactory = Callable[[int, type], int]


@dataclass(frozen=True)
class Enchantment:
    id: str
    translation_key: str
    max_level: int
    can_apply_to: ApplicabilityPredicate
    attribute_factory: AttributeFactory = lambda _level: ()
    damage_protection_factory: DamageProtectionFactory = (
        lambda _level, _damage_type: 0
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", normalize_enchantment_id(self.id))
        if int(self.max_level) < 1:
            raise ValueError("enchantment max_level must be at least 1")
        object.__setattr__(self, "max_level", int(self.max_level))

    def supports(self, stack) -> bool:
        return bool(
            stack is not None
            and not stack.is_empty()
            and self.can_apply_to(getattr(stack, "material", None))
        )

    def validate_level(self, level: int) -> int:
        level = int(level)
        if not 1 <= level <= self.max_level:
            raise ValueError(
                f"level must be between 1 and {self.max_level} for {self.id}"
            )
        return level

    def get_attribute_modifiers(self, level: int) -> tuple[Mapping, ...]:
        return tuple(self.attribute_factory(self.validate_level(level)))

    def get_damage_protection(self, level: int, damage_type: type) -> int:
        return max(
            0,
            int(
                self.damage_protection_factory(
                    self.validate_level(level), damage_type
                )
            ),
        )


_enchantment_registry: dict[str, Enchantment] = {}
_enchantment_aliases: dict[str, str] = {}


def register_enchantment(
    enchantment: Enchantment, *, aliases: Iterable[str] = ()
) -> Enchantment:
    if enchantment.id in _enchantment_registry:
        raise ValueError(f"duplicate enchantment id: {enchantment.id}")
    _enchantment_registry[enchantment.id] = enchantment
    _enchantment_aliases[enchantment.id.split(":", 1)[1]] = enchantment.id
    for alias in aliases:
        normalized = normalize_enchantment_id(alias)
        _enchantment_aliases[normalized] = enchantment.id
        _enchantment_aliases[normalized.split(":", 1)[1]] = enchantment.id
    return enchantment


def get_enchantment(enchantment_id: str) -> Enchantment | None:
    try:
        normalized = normalize_enchantment_id(enchantment_id)
    except ValueError:
        return None
    resolved = _enchantment_aliases.get(
        normalized, _enchantment_aliases.get(normalized.split(":", 1)[1], normalized)
    )
    return _enchantment_registry.get(resolved)


def get_registered_enchantments() -> tuple[Enchantment, ...]:
    return tuple(_enchantment_registry.values())


def _damage_type_has_tag(damage_type, tag: DamageTag) -> bool:
    checker = getattr(damage_type, "has_tag", None)
    if callable(checker):
        return bool(checker(tag))
    tags = getattr(damage_type, "tags", ())
    return tag in tags or tag.value in tags


def get_armor_protection_factor(
    stacks: Iterable[object], damage_type: type, random_source=None
) -> int:
    """Return Minecraft 1.8's randomized armor enchantment protection factor."""
    if _damage_type_has_tag(damage_type, DamageTag.BYPASSES_ENCHANTMENTS):
        return 0

    raw_factor = 0
    for stack in stacks:
        if stack is None or stack.is_empty():
            continue
        for enchantment_id, level in stack.get_enchantments().items():
            enchantment = get_enchantment(enchantment_id)
            if enchantment is not None:
                try:
                    raw_factor += enchantment.get_damage_protection(
                        level, damage_type
                    )
                except (TypeError, ValueError):
                    continue

    raw_factor = max(0, min(25, raw_factor))
    if raw_factor == 0:
        return 0
    if random_source is None:
        random_source = random
    randomized = ((raw_factor + 1) >> 1) + random_source.randrange(
        (raw_factor >> 1) + 1
    )
    return min(20, randomized)


def reduce_damage_by_armor_enchantments(
    damage: float,
    stacks: Iterable[object],
    damage_type: type,
    random_source=None,
) -> float:
    """Apply Minecraft 1.8's EPF reduction after ordinary armor reduction."""
    damage = max(0.0, float(damage))
    protection_factor = get_armor_protection_factor(
        stacks, damage_type, random_source
    )
    return damage * (25 - protection_factor) / 25.0


def _is_melee_weapon(material) -> bool:
    return getattr(material, "tool_type", None) in {"sword", "axe"}


def _is_armor(material) -> bool:
    from src.server.materials import Armor

    return isinstance(material, Armor)


def _is_bow(material) -> bool:
    return getattr(material, "tool_type", None) == "bow"


def _is_damageable(material) -> bool:
    return int(getattr(material, "max_damage", 0)) > 0


def _sharpness_attributes(level: int):
    # PyCraft2D currently follows the pre-1.9 combat value: +1.25 per level.
    return (
        {
            "type": "minecraft:attack_damage",
            "id": "minecraft:enchantment.sharpness",
            "amount": 1.25 * level,
            "operation": "add_value",
            "slot": "mainhand",
        },
    )


def _protection_damage_factor(level: int, _damage_type: type) -> int:
    # Minecraft 1.8.8 EnchantmentProtection type 0 (all damage).
    base = (6 + level * level) / 3.0
    return math.floor(base * 0.75)


SHARPNESS = register_enchantment(
    Enchantment(
        id="minecraft:sharpness",
        translation_key="enchantment.damage.all",
        max_level=5,
        can_apply_to=_is_melee_weapon,
        attribute_factory=_sharpness_attributes,
    ),
    aliases=("damage_all",),
)


PROTECTION = register_enchantment(
    Enchantment(
        id="minecraft:protection",
        translation_key="enchantment.protect.all",
        max_level=4,
        can_apply_to=_is_armor,
        damage_protection_factory=_protection_damage_factor,
    ),
    aliases=("protect_all",),
)


UNBREAKING = register_enchantment(
    Enchantment(
        id="minecraft:unbreaking",
        translation_key="enchantment.durability",
        max_level=3,
        can_apply_to=_is_damageable,
    ),
    aliases=("durability",),
)


POWER = register_enchantment(
    Enchantment(
        id="minecraft:power",
        translation_key="enchantment.arrowDamage",
        max_level=5,
        can_apply_to=_is_bow,
    ),
    aliases=("arrow_damage",),
)


PUNCH = register_enchantment(
    Enchantment(
        id="minecraft:punch",
        translation_key="enchantment.arrowKnockback",
        max_level=2,
        can_apply_to=_is_bow,
    ),
    aliases=("arrow_knockback",),
)


FLAME = register_enchantment(
    Enchantment(
        id="minecraft:flame",
        translation_key="enchantment.arrowFire",
        max_level=1,
        can_apply_to=_is_bow,
    ),
    aliases=("arrow_fire",),
)


INFINITY = register_enchantment(
    Enchantment(
        id="minecraft:infinity",
        translation_key="enchantment.arrowInfinite",
        max_level=1,
        can_apply_to=_is_bow,
    ),
    aliases=("arrow_infinite",),
)


def _slot(slot):
    return lambda material: _is_armor(material) and material.equipment_slot == slot


def _digger(material):
    return getattr(material, "tool_type", None) in {"pickaxe", "axe", "shovel"}


def _sword(material):
    return getattr(material, "tool_type", None) == "sword"


def _modifier(attribute, amount, slot="mainhand"):
    return ({"type": "minecraft:" + attribute, "id": "minecraft:enchantment." + attribute,
             "amount": amount, "operation": "add_value", "slot": slot},)


def _special_protection(kind, multiplier):
    def factor(level, damage):
        name = getattr(damage, "message_id", "")
        matches = {
            "fire": _damage_type_has_tag(damage, DamageTag.IS_FIRE),
            "fall": name == "fall", "explosion": "explosion" in name,
            "projectile": name in {"arrow", "thrown", "fireball"},
        }
        return math.floor((6 + level * level) / 3 * multiplier) if matches[kind] else 0
    return factor


for _id, _key, _maximum, _supports, _attributes, _protection in (
    ("fire_protection", "protect.fire", 4, _is_armor, None, _special_protection("fire", 1.25)),
    ("feather_falling", "protect.fall", 4, _slot("feet"), None, _special_protection("fall", 2.5)),
    ("blast_protection", "protect.explosion", 4, _is_armor, None, _special_protection("explosion", 1.5)),
    ("projectile_protection", "protect.projectile", 4, _is_armor, None, _special_protection("projectile", 1.5)),
    ("respiration", "oxygen", 3, _slot("head"), None, None),
    ("aqua_affinity", "waterWorker", 1, _slot("head"), None, None),
    ("thorns", "thorns", 3, _is_armor, None, None),
    ("depth_strider", "waterWalker", 3, _slot("feet"),
     lambda level: _modifier("water_movement_efficiency", level / 3, "feet"), None),
    ("smite", "damage.undead", 5, _is_melee_weapon, None, None),
    ("bane_of_arthropods", "damage.arthropods", 5, _is_melee_weapon, None, None),
    ("knockback", "knockback", 2, _sword,
     lambda level: _modifier("attack_knockback", level), None),
    ("fire_aspect", "fire", 2, _sword, None, None),
    ("looting", "lootBonus", 3, _sword, None, None),
    ("efficiency", "digging", 5,
     lambda material: _digger(material) or material.name_id == "shears",
     lambda level: _modifier("mining_efficiency", level * level + 1), None),
    ("silk_touch", "untouching", 1, _digger, None, None),
    ("fortune", "lootBonusDigger", 3, _digger, None, None),
    ("luck_of_the_sea", "lootBonusFishing", 3,
     lambda material: material.name_id == "fishing_rod", None, None),
    ("lure", "fishingSpeed", 3,
     lambda material: material.name_id == "fishing_rod", None, None),
):
    _kwargs = {}
    if _attributes is not None:
        _kwargs["attribute_factory"] = _attributes
    if _protection is not None:
        _kwargs["damage_protection_factory"] = _protection
    register_enchantment(Enchantment(_id, "enchantment." + _key, _maximum, _supports, **_kwargs))
