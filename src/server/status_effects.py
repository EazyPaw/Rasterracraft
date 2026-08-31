"""Vanilla-style status-effect definitions shared by the server and client."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from src.server.attributes import AttributeModifier, AttributeOperation


INFINITE_DURATION = -1


@dataclass(frozen=True)
class StatusEffect:
    id: str
    color: int
    category: str

    @property
    def translation_key(self) -> str:
        return f"effect.minecraft.{self.id}"

    def attribute_modifiers(
        self, amplifier: int
    ) -> tuple[tuple[str, AttributeModifier], ...]:
        level = max(0, int(amplifier)) + 1
        modifier_id = f"minecraft:effect.{self.id}"
        multiplied_total = AttributeOperation.ADD_MULTIPLIED_TOTAL
        add_value = AttributeOperation.ADD_VALUE
        if self.id == "speed":
            return (
                (
                    "movement_speed",
                    AttributeModifier(modifier_id, 0.2 * level, multiplied_total),
                ),
            )
        if self.id == "slowness":
            return (
                (
                    "movement_speed",
                    AttributeModifier(
                        modifier_id, max(-1.0, -0.15 * level), multiplied_total
                    ),
                ),
            )
        if self.id == "haste":
            return (
                (
                    "attack_speed",
                    AttributeModifier(
                        modifier_id + ".attack", 0.1 * level, multiplied_total
                    ),
                ),
                (
                    "block_break_speed",
                    AttributeModifier(
                        modifier_id + ".mining", 0.2 * level, multiplied_total
                    ),
                ),
            )
        if self.id == "mining_fatigue":
            return (
                (
                    "attack_speed",
                    AttributeModifier(
                        modifier_id + ".attack",
                        max(-1.0, -0.1 * level),
                        multiplied_total,
                    ),
                ),
                (
                    "block_break_speed",
                    AttributeModifier(
                        modifier_id + ".mining",
                        0.3**level - 1.0,
                        multiplied_total,
                    ),
                ),
            )
        if self.id == "strength":
            return (
                (
                    "attack_damage",
                    AttributeModifier(modifier_id, 3.0 * level, add_value),
                ),
            )
        if self.id == "jump_boost":
            return (
                (
                    "jump_strength",
                    AttributeModifier(
                        modifier_id + ".jump", 0.1 * level, add_value
                    ),
                ),
                (
                    "safe_fall_distance",
                    AttributeModifier(
                        modifier_id + ".fall", float(level), add_value
                    ),
                ),
            )
        if self.id == "weakness":
            return (
                (
                    "attack_damage",
                    AttributeModifier(modifier_id, -4.0 * level, add_value),
                ),
            )
        if self.id == "health_boost":
            return (
                (
                    "max_health",
                    AttributeModifier(modifier_id, 4.0 * level, add_value),
                ),
            )
        if self.id == "absorption":
            return (
                (
                    "max_absorption",
                    AttributeModifier(modifier_id, 4.0 * level, add_value),
                ),
            )
        return ()


@dataclass
class StatusEffectInstance:
    effect_id: str
    duration: int
    amplifier: int = 0
    ambient: bool = False
    show_particles: bool = True
    show_icon: bool = True
    hidden_effect: "StatusEffectInstance | None" = None

    def __post_init__(self) -> None:
        self.effect_id = normalize_effect_id(self.effect_id)
        self.duration = normalize_duration(self.duration)
        self.amplifier = max(0, min(255, int(self.amplifier)))
        self.ambient = bool(self.ambient)
        self.show_particles = bool(self.show_particles)
        self.show_icon = bool(self.show_icon)

    @property
    def infinite(self) -> bool:
        return self.duration == INFINITE_DURATION

    def copy(self, **changes) -> "StatusEffectInstance":
        return replace(self, **changes)

    def to_dict(self, *, include_hidden: bool = True) -> dict:
        data = {
            "id": self.effect_id,
            "duration": self.duration,
            "amplifier": self.amplifier,
            "ambient": self.ambient,
            "show_particles": self.show_particles,
            "show_icon": self.show_icon,
        }
        if include_hidden and self.hidden_effect is not None:
            data["hidden_effect"] = self.hidden_effect.to_dict(include_hidden=True)
        return data

    @classmethod
    def from_dict(cls, data: Mapping) -> "StatusEffectInstance":
        hidden_data = data.get("hidden_effect")
        hidden = cls.from_dict(hidden_data) if isinstance(hidden_data, Mapping) else None
        return cls(
            data.get("id", ""),
            data.get("duration", 0),
            data.get("amplifier", 0),
            data.get("ambient", False),
            data.get("show_particles", True),
            data.get("show_icon", True),
            hidden,
        )


def normalize_duration(value) -> int:
    if isinstance(value, str) and value.strip().lower() == "infinite":
        return INFINITE_DURATION
    duration = int(value)
    return INFINITE_DURATION if duration < 0 else max(0, duration)


def normalize_effect_id(value: str) -> str:
    value = str(value).strip().lower()
    if value.startswith("minecraft:"):
        value = value.split(":", 1)[1]
    return value


def _effect(effect_id: str, color: int, category: str) -> StatusEffect:
    return StatusEffect(effect_id, color, category)


# This registry deliberately matches assets/minecraft/textures/mob_effect exactly.
_EFFECTS = (
    _effect("speed", 0x33EBFF, "beneficial"),
    _effect("slowness", 0x8BAFE0, "harmful"),
    _effect("haste", 0xD9C043, "beneficial"),
    _effect("mining_fatigue", 0x4A4217, "harmful"),
    _effect("strength", 0xFFC700, "beneficial"),
    _effect("jump_boost", 0xFDFF84, "beneficial"),
    _effect("nausea", 0x551D4A, "harmful"),
    _effect("regeneration", 0xCD5CAB, "beneficial"),
    _effect("resistance", 0x9146F0, "beneficial"),
    _effect("fire_resistance", 0xFF9900, "beneficial"),
    _effect("water_breathing", 0x98DAC0, "beneficial"),
    _effect("invisibility", 0xF6F6F6, "beneficial"),
    _effect("blindness", 0x1F1F23, "harmful"),
    _effect("night_vision", 0xC2FF66, "beneficial"),
    _effect("hunger", 0x587653, "harmful"),
    _effect("weakness", 0x484D48, "harmful"),
    _effect("poison", 0x87A363, "harmful"),
    _effect("wither", 0x736156, "harmful"),
    _effect("health_boost", 0xF87D23, "beneficial"),
    _effect("absorption", 0x2552A5, "beneficial"),
)

STATUS_EFFECTS = {effect.id: effect for effect in _EFFECTS}


def get_status_effect(effect_id: str) -> StatusEffect | None:
    return STATUS_EFFECTS.get(normalize_effect_id(effect_id))


def duration_is_longer(left: int, right: int) -> bool:
    if left == INFINITE_DURATION:
        return right != INFINITE_DURATION
    if right == INFINITE_DURATION:
        return False
    return left > right


def tick_duration(instance: StatusEffectInstance) -> None:
    if instance.duration > 0:
        instance.duration -= 1
    if instance.hidden_effect is not None:
        tick_duration(instance.hidden_effect)


def merge_effect(
    current: StatusEffectInstance, incoming: StatusEffectInstance
) -> tuple[StatusEffectInstance, bool]:
    """Apply Java's stronger-effect/hidden-effect replacement rules."""
    if current.effect_id != incoming.effect_id:
        raise ValueError("cannot merge different status effects")
    changed = False
    if incoming.amplifier > current.amplifier:
        old_visible = current.copy()
        old_visible.hidden_effect = current.hidden_effect
        current = incoming.copy(hidden_effect=old_visible)
        changed = True
    elif incoming.amplifier == current.amplifier:
        if duration_is_longer(incoming.duration, current.duration):
            current.duration = incoming.duration
            changed = True
        if incoming.ambient != current.ambient:
            current.ambient = incoming.ambient
            changed = True
        if incoming.show_particles != current.show_particles:
            current.show_particles = incoming.show_particles
            changed = True
        if incoming.show_icon != current.show_icon:
            current.show_icon = incoming.show_icon
            changed = True
    elif duration_is_longer(incoming.duration, current.duration):
        if current.hidden_effect is None:
            current.hidden_effect = incoming.copy()
            changed = True
        else:
            current.hidden_effect, changed = merge_effect(current.hidden_effect, incoming)
    return current, changed

