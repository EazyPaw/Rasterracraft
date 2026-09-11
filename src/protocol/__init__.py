"""Shared packet contracts and dispatch primitives.

The client and server intentionally share this package.  It defines the wire
contract once while keeping client presentation and server-authoritative game
logic in their respective handler modules.
"""

from .core import (
    CLIENTBOUND,
    SERVERBOUND,
    Direction,
    Packet,
    PacketDecodeError,
    PacketDispatcher,
    PacketSpec,
    decode_payload,
    encode_payload,
    get_packet_spec,
    make_packet,
    packet_spec,
    packet_specs,
)

__all__ = [
    "CLIENTBOUND",
    "SERVERBOUND",
    "Direction",
    "Packet",
    "PacketDecodeError",
    "PacketDispatcher",
    "PacketSpec",
    "decode_payload",
    "encode_payload",
    "get_packet_spec",
    "make_packet",
    "packet_spec",
    "packet_specs",
]
