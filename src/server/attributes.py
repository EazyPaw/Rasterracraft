# Commented and arranged by ChatGPT
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Callable, Iterable, Mapping


def normalize_id(value: str) -> str:
    value = str(value).strip().lower()
    if ":" not in value:
        value = f"minecraft:{value}"
    namespace, path = value.split(":", 1)
    for legacy_prefix in ("generic.", "player.", "zombie.", "horse."):
        if namespace == "minecraft" and path.startswith(legacy_prefix):
            path = path[len(legacy_prefix) :]
            break
    return f"{namespace}:{path}"


class AttributeOperation(str, Enum):
    ADD_VALUE = "add_value"
    ADD_MULTIPLIED_BASE = "add_multiplied_base"
    ADD_MULTIPLIED_TOTAL = "add_multiplied_total"

    @classmethod
    def parse(cls, value) -> "AttributeOperation":
        if isinstance(value, cls):
            return value
        if isinstance(value, bool):
            raise ValueError("boolean is not an attribute modifier operation")
        aliases = {
            0: cls.ADD_VALUE,
            1: cls.ADD_MULTIPLIED_BASE,
            2: cls.ADD_MULTIPLIED_TOTAL,
            "add": cls.ADD_VALUE,
            "multiply_base": cls.ADD_MULTIPLIED_BASE,
            "multiply": cls.ADD_MULTIPLIED_TOTAL,
        }
        if value in aliases:
            return aliases[value]
        return cls(str(value).lower())


@dataclass(frozen=True)
class AttributeDefinition:
    id: str
    default: float
    minimum: float
    maximum: float
    syncable: bool = False
    sentiment: str = "positive"

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", normalize_id(self.id))
        if self.minimum > self.maximum:
            raise ValueError("attribute minimum cannot exceed maximum")
        if not self.minimum <= self.default <= self.maximum:
            raise ValueError("attribute default must be inside its range")

    def sanitize(self, value: float) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = self.minimum
        if math.isnan(value):
            value = self.minimum
        return max(self.minimum, min(self.maximum, value))


@dataclass(frozen=True)
class AttributeModifier:
    id: str
    amount: float
    operation: AttributeOperation = AttributeOperation.ADD_VALUE

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", normalize_id(self.id))
        object.__setattr__(self, "amount", float(self.amount))
        object.__setattr__(self, "operation", AttributeOperation.parse(self.operation))

    @classmethod
    def from_dict(cls, data: Mapping) -> "AttributeModifier":
        return cls(
            data["id"], data.get("amount", 0.0), data.get("operation", "add_value")
        )

    def to_dict(self) -> dict:
        return {"id": self.id, "amount": self.amount, "operation": self.operation.value}


class AttributeInstance:
    def __init__(
        self,
        definition: AttributeDefinition,
        base_value: float | None = None,
        on_dirty: Callable[["AttributeInstance"], None] | None = None,
    ):
        self.definition = definition
        self._base_value = (
            definition.default if base_value is None else float(base_value)
        )
        self._modifiers: dict[str, AttributeModifier] = {}
        self._permanent_ids: set[str] = set()
        self._modifier_sources: dict[str, str] = {}
        self._dirty = True
        self._cached_value = definition.sanitize(self._base_value)
        self._on_dirty = on_dirty

    @property
    def base_value(self) -> float:
        return self._base_value

    @base_value.setter
    def base_value(self, value: float) -> None:
        value = float(value)
        if value != self._base_value:
            self._base_value = value
            self._set_dirty()

    @property
    def value(self) -> float:
        if self._dirty:
            base_with_additions = self._base_value + sum(
                modifier.amount
                for modifier in self._modifiers.values()
                if modifier.operation is AttributeOperation.ADD_VALUE
            )
            result = base_with_additions + sum(
                base_with_additions * modifier.amount
                for modifier in self._modifiers.values()
                if modifier.operation is AttributeOperation.ADD_MULTIPLIED_BASE
            )
            for modifier in self._modifiers.values():
                if modifier.operation is AttributeOperation.ADD_MULTIPLIED_TOTAL:
                    result *= 1.0 + modifier.amount
            self._cached_value = self.definition.sanitize(result)
            self._dirty = False
        return self._cached_value

    @property
    def modifiers(self) -> tuple[AttributeModifier, ...]:
        return tuple(self._modifiers.values())

    def get_modifier(self, modifier_id: str) -> AttributeModifier | None:
        return self._modifiers.get(normalize_id(modifier_id))

    def add_modifier(
        self,
        modifier: AttributeModifier,
        *,
        permanent: bool = False,
        source: str | None = None,
        replace: bool = False,
    ) -> None:
        modifier_id = modifier.id
        if modifier_id in self._modifiers and not replace:
            raise ValueError(
                f"modifier {modifier_id!r} is already applied to {self.definition.id}"
            )
        self._modifiers[modifier_id] = modifier
        if permanent:
            self._permanent_ids.add(modifier_id)
        else:
            self._permanent_ids.discard(modifier_id)
        if source is None:
            self._modifier_sources.pop(modifier_id, None)
        else:
            self._modifier_sources[modifier_id] = str(source)
        self._set_dirty()

    def remove_modifier(self, modifier_id: str) -> bool:
        modifier_id = normalize_id(modifier_id)
        if modifier_id not in self._modifiers:
            return False
        del self._modifiers[modifier_id]
        self._permanent_ids.discard(modifier_id)
        self._modifier_sources.pop(modifier_id, None)
        self._set_dirty()
        return True

    def remove_source(self, source: str) -> None:
        for modifier_id, owner in tuple(self._modifier_sources.items()):
            if owner == source:
                self.remove_modifier(modifier_id)

    def _set_dirty(self) -> None:
        self._dirty = True
        if self._on_dirty is not None:
            self._on_dirty(self)

    def to_dict(self, *, permanent_only: bool = False) -> dict:
        modifiers = self._modifiers.values()
        if permanent_only:
            modifiers = (
                modifier
                for modifier_id, modifier in self._modifiers.items()
                if modifier_id in self._permanent_ids
            )
        return {
            "id": self.definition.id,
            "base": self._base_value,
            "modifiers": [modifier.to_dict() for modifier in modifiers],
        }


class AttributeMap:
    def __init__(
        self,
        base_values: Mapping[str, float] | None = None,
        on_dirty: Callable[[AttributeInstance], None] | None = None,
    ):
        values = {
            normalize_id(key): value for key, value in (base_values or {}).items()
        }
        self._on_dirty = on_dirty
        self._instances = {
            definition.id: AttributeInstance(
                definition, values.get(definition.id), self._changed
            )
            for definition in ATTRIBUTE_REGISTRY.values()
        }
        self._dirty_syncable: set[str] = set()

    def _changed(self, instance: AttributeInstance) -> None:
        if instance.definition.syncable:
            self._dirty_syncable.add(instance.definition.id)
        if self._on_dirty is not None:
            self._on_dirty(instance)

    def get_instance(self, attribute_id: str) -> AttributeInstance:
        attribute_id = normalize_id(attribute_id)
        try:
            return self._instances[attribute_id]
        except KeyError as exc:
            raise KeyError(f"unknown attribute {attribute_id!r}") from exc

    def get_value(self, attribute_id: str) -> float:
        return self.get_instance(attribute_id).value

    def get_base_value(self, attribute_id: str) -> float:
        return self.get_instance(attribute_id).base_value

    def set_base_value(self, attribute_id: str, value: float) -> None:
        self.get_instance(attribute_id).base_value = value

    def add_modifier(
        self, attribute_id: str, modifier: AttributeModifier, **kwargs
    ) -> None:
        self.get_instance(attribute_id).add_modifier(modifier, **kwargs)

    def remove_modifier(self, attribute_id: str, modifier_id: str) -> bool:
        return self.get_instance(attribute_id).remove_modifier(modifier_id)

    def replace_source(
        self, source: str, entries: Iterable[tuple[str, AttributeModifier]]
    ) -> None:
        for instance in self._instances.values():
            instance.remove_source(source)
        for attribute_id, modifier in entries:
            self.add_modifier(attribute_id, modifier, source=source, replace=True)

    def to_persistent_data(self) -> list[dict]:
        return [
            instance.to_dict(permanent_only=True)
            for instance in self._instances.values()
        ]

    def load_persistent_data(self, payload) -> None:
        if not isinstance(payload, list):
            return
        for entry in payload:
            if not isinstance(entry, Mapping) or "id" not in entry:
                continue
            try:
                instance = self.get_instance(entry["id"])
                instance.base_value = float(entry.get("base", instance.base_value))
                for modifier_data in entry.get("modifiers", ()):
                    if isinstance(modifier_data, Mapping):
                        instance.add_modifier(
                            AttributeModifier.from_dict(modifier_data),
                            permanent=True,
                            replace=True,
                        )
            except (KeyError, TypeError, ValueError):
                continue

    def sync_snapshot(self) -> list[dict]:
        return [
            instance.to_dict()
            for instance in self._instances.values()
            if instance.definition.syncable
        ]

    def take_dirty_syncable(self) -> set[str]:
        dirty = set(self._dirty_syncable)
        self._dirty_syncable.clear()
        return dirty

    def apply_sync_snapshot(self, payload) -> None:
        if not isinstance(payload, list):
            return
        for entry in payload:
            if not isinstance(entry, Mapping) or "id" not in entry:
                continue
            try:
                instance = self.get_instance(entry["id"])
                instance.base_value = float(entry.get("base", instance.base_value))
                for modifier in tuple(instance.modifiers):
                    instance.remove_modifier(modifier.id)
                for modifier_data in entry.get("modifiers", ()):
                    if isinstance(modifier_data, Mapping):
                        instance.add_modifier(
                            AttributeModifier.from_dict(modifier_data)
                        )
            except (KeyError, TypeError, ValueError):
                continue


def _attribute(name, default, minimum, maximum, syncable=False, sentiment="positive"):
    return AttributeDefinition(name, default, minimum, maximum, syncable, sentiment)


_DEFINITIONS = (
    _attribute("armor", 0.0, 0.0, 30.0, True),
    _attribute("armor_toughness", 0.0, 0.0, 20.0, True),
    _attribute("attack_damage", 2.0, 0.0, 2048.0),
    _attribute("attack_knockback", 0.0, 0.0, 5.0),
    _attribute("attack_speed", 4.0, 0.0, 1024.0, True),
    _attribute("block_break_speed", 1.0, 0.0, 1024.0, True),
    _attribute("block_interaction_range", 4.5, 0.0, 64.0, True),
    _attribute("burning_time", 1.0, 0.0, 1024.0, True, "negative"),
    _attribute("camera_distance", 4.0, 0.0, 32.0, True, "neutral"),
    _attribute("explosion_knockback_resistance", 0.0, 0.0, 1.0, True),
    _attribute("entity_interaction_range", 3.0, 0.0, 64.0, True),
    _attribute("fall_damage_multiplier", 1.0, 0.0, 100.0, True, "negative"),
    _attribute("flying_speed", 0.4, 0.0, 1024.0, True),
    _attribute("follow_range", 32.0, 0.0, 2048.0),
    _attribute("gravity", 0.08, -1.0, 1.0, True, "neutral"),
    _attribute("jump_strength", 0.42, 0.0, 32.0, True),
    _attribute("knockback_resistance", 0.0, 0.0, 1.0),
    _attribute("luck", 0.0, -1024.0, 1024.0, True),
    _attribute("max_absorption", 0.0, 0.0, 2048.0, True),
    _attribute("max_health", 20.0, 1.0, 1024.0, True),
    _attribute("mining_efficiency", 0.0, 0.0, 1024.0, True),
    _attribute("movement_efficiency", 0.0, 0.0, 1.0, True),
    _attribute("movement_speed", 0.7, 0.0, 1024.0, True),
    _attribute("oxygen_bonus", 0.0, 0.0, 1024.0, True),
    _attribute("safe_fall_distance", 3.0, -1024.0, 1024.0, True),
    _attribute("scale", 1.0, 0.0625, 16.0, True, "neutral"),
    _attribute("sneaking_speed", 0.3, 0.0, 1.0, True),
    _attribute("spawn_reinforcements", 0.0, 0.0, 1.0),
    _attribute("step_height", 0.6, 0.0, 10.0, True),
    _attribute("submerged_mining_speed", 0.2, 0.0, 20.0, True),
    _attribute("sweeping_damage_ratio", 0.0, 0.0, 1.0, True),
    _attribute("tempt_range", 10.0, 0.0, 2048.0),
    _attribute("water_movement_efficiency", 0.0, 0.0, 1.0, True),
    _attribute("waypoint_receive_range", 0.0, 0.0, 60_000_000.0, True),
    _attribute("waypoint_transmit_range", 0.0, 0.0, 60_000_000.0, True),
)

ATTRIBUTE_REGISTRY = {definition.id: definition for definition in _DEFINITIONS}

SPRINTING_SPEED_MODIFIER = AttributeModifier(
    "minecraft:sprinting",
    0.3,
    AttributeOperation.ADD_MULTIPLIED_TOTAL,
)

EATING_SPEED_MODIFIER = AttributeModifier(
    "minecraft:eating",
    -0.8,
    AttributeOperation.ADD_MULTIPLIED_TOTAL,
)

BLOCKING_SPEED_MODIFIER = AttributeModifier(
    "minecraft:blocking",
    -0.8,
    AttributeOperation.ADD_MULTIPLIED_TOTAL,
)
