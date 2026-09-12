from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Generic, TypeVar


PACKET_TYPE_KEY = "__class__"


class Direction(Enum):
    SERVERBOUND = "serverbound"
    CLIENTBOUND = "clientbound"


SERVERBOUND = Direction.SERVERBOUND
CLIENTBOUND = Direction.CLIENTBOUND


class PacketDecodeError(ValueError):
    """Raised when a wire value does not satisfy the shared packet contract."""


@dataclass(frozen=True, slots=True)
class PacketSpec:
    name: str
    directions: frozenset[Direction]
    fields: frozenset[str] = field(default_factory=frozenset)
    required: frozenset[str] = field(default_factory=frozenset)

    def validate(self, payload: Mapping[str, Any]) -> None:
        missing = self.required.difference(payload)
        if missing:
            names = ", ".join(sorted(missing))
            raise PacketDecodeError(f"{self.name} is missing required fields: {names}")


_SPECS: dict[str, PacketSpec] = {}


def packet_spec(
    name: str,
    *directions: Direction,
    fields: tuple[str, ...] = (),
    required: tuple[str, ...] = (),
) -> PacketSpec:
    if not name or not directions:
        raise ValueError("packet name and at least one direction are required")
    if name in _SPECS:
        raise RuntimeError(f"duplicate packet specification: {name}")
    spec = PacketSpec(
        name=name,
        directions=frozenset(directions),
        fields=frozenset(fields),
        required=frozenset(required),
    )
    if not spec.required.issubset(spec.fields):
        raise ValueError(f"required fields must be declared for packet {name}")
    _SPECS[name] = spec
    return spec


def get_packet_spec(name: str) -> PacketSpec:
    try:
        return _SPECS[name]
    except KeyError as exc:
        raise PacketDecodeError(f"unknown packet type: {name!r}") from exc


def packet_specs(direction: Direction | None = None) -> tuple[PacketSpec, ...]:
    specs = _SPECS.values()
    if direction is not None:
        specs = (spec for spec in specs if direction in spec.directions)
    return tuple(sorted(specs, key=lambda spec: spec.name))


@dataclass(frozen=True, slots=True)
class Packet(Mapping[str, Any]):
    """Validated packet value that remains mapping-compatible with old handlers."""

    spec: PacketSpec
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        values = dict(self.payload)
        values.pop(PACKET_TYPE_KEY, None)
        self.spec.validate(values)
        object.__setattr__(self, "payload", MappingProxyType(values))

    @property
    def name(self) -> str:
        return self.spec.name

    def __getitem__(self, key: str) -> Any:
        if key == PACKET_TYPE_KEY:
            return self.name
        return self.payload[key]

    def __iter__(self):
        yield PACKET_TYPE_KEY
        yield from self.payload

    def __len__(self) -> int:
        return len(self.payload) + 1

    def to_dict(self) -> dict[str, Any]:
        return {PACKET_TYPE_KEY: self.name, **self.payload}


def make_packet(name: str, /, **payload: Any) -> Packet:
    # Use exactly the same contract as legacy dictionary packets. MsgPack owns
    # value serialization (including the server's NumPy default encoder); a
    # separate recursive whitelist here rejects otherwise valid world/NBT data.
    return Packet(get_packet_spec(name), payload)


def decode_payload(raw: Mapping[str, Any], direction: Direction) -> Packet:
    if not isinstance(raw, Mapping):
        raise PacketDecodeError("packet payload must be a mapping")
    name = raw.get(PACKET_TYPE_KEY)
    if not isinstance(name, str) or not name:
        raise PacketDecodeError(f"packet has no valid {PACKET_TYPE_KEY!r}")
    try:
        spec = _SPECS[name]
    except KeyError as exc:
        raise PacketDecodeError(f"unknown packet type: {name!r}") from exc
    if direction not in spec.directions:
        raise PacketDecodeError(
            f"packet {name!r} is not valid in the {direction.value} direction"
        )
    # Packet copies the outer mapping and strips the envelope key. Leave nested
    # values to the transport encoder, just as for make_packet and legacy sends.
    return Packet(spec, raw)


def encode_payload(
    value: Packet | Mapping[str, Any], direction: Direction | None = None
) -> dict[str, Any]:
    if isinstance(value, Packet):
        packet = value
        if direction is not None and direction not in packet.spec.directions:
            raise PacketDecodeError(
                f"packet {packet.name!r} is not valid in the {direction.value} direction"
            )
    else:
        if direction is None:
            name = value.get(PACKET_TYPE_KEY) if isinstance(value, Mapping) else None
            if not isinstance(name, str) or name not in _SPECS:
                raise PacketDecodeError(f"unknown packet type: {name!r}")
            direction = next(iter(_SPECS[name].directions))
        packet = decode_payload(value, direction)
    return packet.to_dict()


ContextT = TypeVar("ContextT")
Handler = Callable[[dict[str, Any], ContextT], None]


class PacketDispatcher(Generic[ContextT]):
    def __init__(self, direction: Direction):
        self.direction = direction
        self._handlers: dict[str, Handler[ContextT]] = {}

    def handler(self, packet_name: str):
        try:
            spec = _SPECS[packet_name]
        except KeyError as exc:
            raise RuntimeError(f"handler uses unknown packet: {packet_name}") from exc
        if self.direction not in spec.directions:
            raise RuntimeError(
                f"handler direction does not match packet {packet_name!r}"
            )

        def decorate(func: Handler[ContextT]) -> Handler[ContextT]:
            if packet_name in self._handlers:
                raise RuntimeError(f"duplicate packet handler: {packet_name}")
            self._handlers[packet_name] = func
            return func

        return decorate

    def dispatch(self, raw: Mapping[str, Any], context: ContextT) -> Packet:
        packet = decode_payload(raw, self.direction)
        return self.dispatch_packet(packet, context)

    def dispatch_packet(self, packet: Packet, context: ContextT) -> Packet:
        if self.direction not in packet.spec.directions:
            raise PacketDecodeError(
                f"packet {packet.name!r} is not valid in the {self.direction.value} direction"
            )
        try:
            handler = self._handlers[packet.name]
        except KeyError as exc:
            raise PacketDecodeError(
                f"no {self.direction.value} handler for packet {packet.name!r}"
            ) from exc
        # Existing gameplay handlers historically receive mutable dictionaries.
        # Keep that boundary stable while Packet remains the validated transport
        # representation; several domain decoders pass the payload onward.
        handler(packet.to_dict(), context)
        return packet

    @property
    def packet_names(self) -> frozenset[str]:
        return frozenset(self._handlers)

    def validate_handlers(self, *, exclude: tuple[str, ...] = ()) -> None:
        """Fail at startup if a registered wire contract has no receiver.

        Phase-specific packets such as ClientHello are handled by the socket
        handshake and must be excluded explicitly by the gameplay dispatcher.
        """
        expected = {spec.name for spec in packet_specs(self.direction)}
        missing = expected.difference(self._handlers, exclude)
        if missing:
            raise RuntimeError(
                f"missing {self.direction.value} handlers: {', '.join(sorted(missing))}"
            )


# The wire schema lives in one place.  Fields document the supported contract;
# optional extra fields remain accepted during the migration for compatibility.
packet_spec("ClientHello", SERVERBOUND, fields=("name",), required=("name",))
packet_spec("DisconnectAck", SERVERBOUND)
packet_spec("PlayerMove", SERVERBOUND, fields=("x", "y", "sneaking", "sprinting", "facing", "on_ground", "flying", "look_angle"), required=("x", "y"))
packet_spec("TeleportConfirm", SERVERBOUND, fields=("teleport_id",))
packet_spec("ChunkReady", SERVERBOUND, fields=("rx",), required=("rx",))
packet_spec("PlayerAction", SERVERBOUND, fields=("action", "x", "y", "z"), required=("action",))
packet_spec("BreakBlock", SERVERBOUND, CLIENTBOUND, fields=("x", "y", "z"), required=("x", "y", "z"))
packet_spec("RightClick", SERVERBOUND, fields=("x", "y", "z", "context"))
packet_spec("PickupItem", SERVERBOUND, fields=("uuid",), required=("uuid",))
packet_spec("AttackEntity", SERVERBOUND, fields=("uuid",), required=("uuid",))
packet_spec("InteractEntity", SERVERBOUND, fields=("uuid",), required=("uuid",))
packet_spec("SelfDamage", SERVERBOUND)
packet_spec("ChatMessage", SERVERBOUND, CLIENTBOUND, fields=("text", "color"), required=("text",))
packet_spec("ClientShutdown", SERVERBOUND)
packet_spec("InventoryClick", SERVERBOUND, fields=("slot", "button"), required=("slot", "button"))
packet_spec("ContainerClick", SERVERBOUND, fields=("container", "slot", "button"), required=("container", "slot", "button"))
packet_spec("CloseFurnace", SERVERBOUND, fields=("container",), required=("container",))
packet_spec("CloseChest", SERVERBOUND, fields=("container",), required=("container",))
packet_spec("ContainerQuickMove", SERVERBOUND, fields=("container", "slot", "screen", "crafting_size", "all_matching"), required=("container", "slot"))
packet_spec("ContainerSwap", SERVERBOUND, fields=("container", "slot", "target_container", "target_slot"), required=("container", "slot", "target_container", "target_slot"))
packet_spec("ContainerDrop", SERVERBOUND, fields=("container", "slot", "cursor", "amount"))
packet_spec("CreativeSetSlot", SERVERBOUND, fields=("target", "slot", "item", "id", "amount", "nbt"))
packet_spec("CreativeClearInventory", SERVERBOUND)
packet_spec("InventoryDrag", SERVERBOUND, fields=("slots", "button"), required=("slots",))
packet_spec("ContainerDrag", SERVERBOUND, fields=("container", "slots", "button"), required=("container", "slots"))
packet_spec("CraftingDrag", SERVERBOUND, fields=("slots", "button"), required=("slots",))
packet_spec("InventoryDrop", SERVERBOUND, fields=("cursor", "slot", "amount"))
packet_spec("InventoryResyncRequest", SERVERBOUND)
packet_spec("CraftingClick", SERVERBOUND, fields=("slot", "button"), required=("slot", "button"))
packet_spec("CraftingTake", SERVERBOUND, fields=("width", "height"))
packet_spec("CraftingQuickTake", SERVERBOUND, fields=("width", "height"))
packet_spec("CraftingClose", SERVERBOUND)
packet_spec("SaveHotbar", SERVERBOUND, fields=("preset",), required=("preset",))
packet_spec("LoadHotbar", SERVERBOUND, fields=("preset",), required=("preset",))
packet_spec("SelectHotbarSlot", SERVERBOUND, fields=("slot",), required=("slot",))
packet_spec("RequestRespawn", SERVERBOUND)
packet_spec("StructureEdit", SERVERBOUND, fields=("action", "kind", "start", "end"), required=("action",))

packet_spec("Disconnect", CLIENTBOUND, fields=("reason", "reason_is_translation_key"), required=("reason",))
packet_spec("Chunk", CLIENTBOUND, fields=("x", "format", "payload", "region_array", "biome_array", "light_array", "sky_light_array", "block_light_array"), required=("x",))
packet_spec("Teleport", CLIENTBOUND, fields=("x", "y", "uuid", "name", "health", "absorption_amount", "hurt_time", "last_hurt_damage", "food_level", "saturation", "experience", "experience_level", "experience_total", "score", "sleeping", "sleeping_bed", "selected_slot", "teleport_id", "inventory", "cursor", "equipment", "attributes", "active_effects"), required=("x", "y"))
packet_spec("BlockBreakProgress", CLIENTBOUND, fields=("x", "y", "z", "miner_uuid", "progress", "active"), required=("x", "y", "z"))
packet_spec("BlockBreakCorrection", CLIENTBOUND, fields=("x", "y", "z", "block_data"), required=("x", "y", "z", "block_data"))
packet_spec("BlockUpdate", CLIENTBOUND, fields=("x", "y", "z", "block_data"), required=("x", "y", "z", "block_data"))
packet_spec("LightUpdate", CLIENTBOUND, fields=("rx", "format", "height", "sky_light", "block_light", "light_array", "sky_light_array", "block_light_array"), required=("rx",))
packet_spec("BiomeUpdate", CLIENTBOUND, fields=("rx", "biome_array"), required=("rx", "biome_array"))
packet_spec("UnloadChunk", CLIENTBOUND, fields=("rx",), required=("rx",))
packet_spec("TimeUpdate", CLIENTBOUND, fields=("time",), required=("time",))
packet_spec("WorldLoadStart", CLIENTBOUND, fields=("regions",), required=("regions",))
packet_spec("WorldLoadComplete", CLIENTBOUND, fields=("regions",), required=("regions",))
packet_spec("WeatherUpdate", CLIENTBOUND, fields=("weather", "remaining_ticks"), required=("weather",))
packet_spec("Particle", CLIENTBOUND, fields=("particle_id", "x", "y", "z", "count", "motion", "data"), required=("particle_id",))
packet_spec("SoundEffect", CLIENTBOUND, fields=("sound_id", "x", "y", "z", "volume", "global"), required=("sound_id",))
packet_spec("InventoryUpdate", CLIENTBOUND, fields=("inventory", "equipment", "crafting", "cursor", "selected_slot", "health", "absorption_amount", "food_level", "saturation", "blocking", "attributes", "active_effects"), required=("inventory",))
packet_spec("FurnaceOpen", CLIENTBOUND, fields=("container", "slots", "burn_time", "burn_time_total", "cook_time", "cook_time_total"), required=("container",))
packet_spec("FurnaceUpdate", CLIENTBOUND, fields=("container", "slots", "burn_time", "burn_time_total", "cook_time", "cook_time_total"), required=("container",))
packet_spec("FurnaceClosed", CLIENTBOUND, fields=("container",), required=("container",))
packet_spec("ChestOpen", CLIENTBOUND, fields=("container", "slots", "rows", "x", "y", "z"), required=("container",))
packet_spec("ChestUpdate", CLIENTBOUND, fields=("container", "slots", "rows", "x", "y", "z"), required=("container",))
packet_spec("ChestClosed", CLIENTBOUND, fields=("container",), required=("container",))
packet_spec("CraftingTableOpen", CLIENTBOUND, fields=("width", "height"))
packet_spec("PlayerHurt", CLIENTBOUND, fields=("health", "absorption_amount", "hurt_time", "last_hurt_damage", "motion", "death_message", "score", "cause", "damage"), required=("health",))
packet_spec("AttributeUpdate", CLIENTBOUND, fields=("uuid", "attributes", "max_health"), required=("attributes",))
packet_spec("EffectUpdate", CLIENTBOUND, fields=("uuid", "active_effects", "attributes", "health", "max_health", "absorption_amount"), required=("active_effects",))
packet_spec("PlayerVelocity", CLIENTBOUND, fields=("motion", "sprinting"), required=("motion",))
packet_spec("Experience", CLIENTBOUND, fields=("amount", "experience", "experience_level", "experience_total", "score"))
packet_spec("EntitySpawn", CLIENTBOUND, fields=("uuid",))
packet_spec("EntityUpdate", CLIENTBOUND, fields=("uuid",))
packet_spec("EntityRemove", CLIENTBOUND, fields=("uuid",), required=("uuid",))
packet_spec("SaveComplete", CLIENTBOUND)
packet_spec("GamemodeUpdate", CLIENTBOUND, fields=("new_mode",), required=("new_mode",))
packet_spec("StructureBuildState", CLIENTBOUND, fields=("mode", "bounds", "full", "void_cells", "void_add", "void_remove"), required=("mode",))
