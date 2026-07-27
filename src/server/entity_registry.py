# Commented and arranged by ChatGPT

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class NamespacedKey:
    namespace: str
    key: str

    def __post_init__(self) -> None:
        namespace = str(self.namespace).strip().lower()
        key = str(self.key).strip().lower()
        if (
            re.fullmatch(r"[a-z0-9_.-]+", namespace) is None
            or re.fullmatch(r"[a-z0-9/._-]+", key) is None
        ):
            raise ValueError(f"Invalid namespaced key: {self.namespace}:{self.key}")
        object.__setattr__(self, "namespace", namespace)
        object.__setattr__(self, "key", key)

    @classmethod
    def parse(
        cls, value: str | NamespacedKey, *, default_namespace: str = "minecraft"
    ) -> NamespacedKey:
        if isinstance(value, cls):
            return value
        raw = str(value).strip().lower()
        if ":" in raw:
            namespace, key = raw.split(":", 1)
        else:
            namespace, key = default_namespace, raw
        return cls(namespace, key)

    def __str__(self) -> str:
        return f"{self.namespace}:{self.key}"


_entity_registry: dict[NamespacedKey, type] = {}
_entity_aliases: dict[NamespacedKey, NamespacedKey] = {}
_builtins_loaded = False


def register_entity(
    cls=None,
    /,
    *,
    key: str | NamespacedKey | None = None,
    aliases: tuple[str | NamespacedKey, ...] = (),
    namespace: str = "minecraft",
    name_spaced_key: str | None = None,
    summonable: bool = True,
    persistent: bool = True,
):

    if cls is None:
        return lambda entity_cls: register_entity(
            entity_cls,
            key=key,
            aliases=aliases,
            namespace=namespace,
            name_spaced_key=name_spaced_key,
            summonable=summonable,
            persistent=persistent,
        )

    if name_spaced_key is not None:
        namespace = str(name_spaced_key)
    raw_key = key if key is not None else getattr(cls, "entity_id", None)
    if raw_key is None:
        raise ValueError(f"{cls.__name__} must define entity_id or provide key=")
    namespaced_key = NamespacedKey.parse(raw_key, default_namespace=namespace)
    existing = _entity_registry.get(namespaced_key)
    if existing is not None and existing is not cls:
        raise ValueError(f"Duplicate entity registration: {namespaced_key}")

    cls.registry_key = namespaced_key
    cls.entity_id = (
        namespaced_key.key
        if namespaced_key.namespace == "minecraft"
        else str(namespaced_key)
    )
    cls.summonable = bool(summonable)
    cls.persistent = bool(persistent)
    _entity_registry[namespaced_key] = cls
    for alias in aliases:
        alias_key = NamespacedKey.parse(
            alias, default_namespace=namespaced_key.namespace
        )
        alias_owner = _entity_registry.get(alias_key)
        if alias_owner is not None and alias_owner is not cls:
            raise ValueError(f"Entity alias conflicts with primary key: {alias_key}")
        alias_target = _entity_aliases.get(alias_key)
        if alias_target is not None and alias_target != namespaced_key:
            raise ValueError(f"Duplicate entity alias: {alias_key}")
        _entity_aliases[alias_key] = namespaced_key
    return cls


def _load_builtin_entities() -> None:
    global _builtins_loaded
    if _builtins_loaded:
        return

    from src.server.entities import (  # noqa: F401
        chicken,
        cow,
        experience_orb,
        falling_block,
        item,
        pig,
        primed_tnt,
        sheep,
        zombie,
    )

    _builtins_loaded = True


def get_entity_type(
    entity_id: str | NamespacedKey, *, summonable_only: bool = False
) -> type | None:
    _load_builtin_entities()
    key = NamespacedKey.parse(entity_id)
    key = _entity_aliases.get(key, key)
    entity_type = _entity_registry.get(key)
    if entity_type is not None and (
        not summonable_only or bool(getattr(entity_type, "summonable", False))
    ):
        return entity_type
    return None


def get_entity_types(*, summonable_only: bool = True) -> dict[str, type]:

    _load_builtin_entities()
    result: dict[str, type] = {}
    for namespaced_key, entity_type in _entity_registry.items():
        if summonable_only and not bool(getattr(entity_type, "summonable", False)):
            continue
        display_key = (
            namespaced_key.key
            if namespaced_key.namespace == "minecraft"
            else str(namespaced_key)
        )
        result[display_key] = entity_type
    return result


def get_registered_entity_key(entity_or_type) -> NamespacedKey | None:
    entity_type = (
        entity_or_type if isinstance(entity_or_type, type) else type(entity_or_type)
    )
    key = getattr(entity_type, "registry_key", None)
    return key if isinstance(key, NamespacedKey) else None


def is_entity_persistent(entity_or_type) -> bool:
    return bool(
        get_registered_entity_key(entity_or_type) is not None
        and getattr(
            entity_or_type
            if isinstance(entity_or_type, type)
            else type(entity_or_type),
            "persistent",
            False,
        )
    )


def create_entity(
    entity_id: str | NamespacedKey, x: float, y: float, world, z: int = 0
):
    entity_type = get_entity_type(entity_id, summonable_only=True)
    if entity_type is None:
        raise ValueError(f"Unknown or non-summonable entity: {entity_id}")
    return entity_type(float(x), float(y), world, int(z))


def create_entity_from_save(data: dict[str, Any], world):

    raw_id = data.get("id", data.get("entity_id", ""))
    try:
        entity_type = get_entity_type(raw_id)
        if entity_type is None or not bool(getattr(entity_type, "persistent", False)):
            return None
        factory: Callable = getattr(entity_type, "create_from_save")
        entity = factory(data, world)
        entity.restore_common_save_data(data)
        return entity
    except (KeyError, TypeError, ValueError):
        return None
