"""Bounded socket output with latest-state replacement for slow receivers."""
from collections import OrderedDict
from dataclasses import dataclass
import logging
import socket
import struct
import threading

import msgpack
import numpy as np


def msgpack_default(value):
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (np.str_, np.bytes_)):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


@dataclass(slots=True)
class _QueuedFrame:
    frame: bytes
    packet: dict | None = None
    entity_uuid: str | None = None


class PacketSender:
    MAX_PENDING_BYTES = 32 * 1024 * 1024
    BATCH_BYTES = 64 * 1024
    MAX_ATTRIBUTE_CACHE = 512
    CHUNK_BACKPRESSURE_BYTES = 2 * 1024 * 1024

    def __init__(self, connection, *, name="SocketWriter"):
        self.connection = connection
        self._condition = threading.Condition()
        self._frames = OrderedDict()
        self._updates = {}
        self._attributes = OrderedDict()
        self._removed_entities = OrderedDict()
        self._sequence = 0
        self._pending_bytes = 0
        self._closed = False
        self.thread = threading.Thread(target=self._run, name=name, daemon=True)
        self.thread.start()

    @staticmethod
    def _encode(packet):
        payload = msgpack.packb(packet, use_bin_type=True, default=msgpack_default)
        return struct.pack(">I", len(payload)) + payload

    def _discard_update(self, entity_uuid):
        sequence = self._updates.pop(entity_uuid, None)
        if sequence is not None:
            previous = self._frames.pop(sequence, None)
            if previous is not None:
                self._pending_bytes -= len(previous.frame)
                return previous.packet
        return None

    @property
    def pending_bytes(self):
        with self._condition:
            return self._pending_bytes

    def enqueue(self, frame, packet=None):
        with self._condition:
            if self._closed:
                return False
            update_uuid = None
            if packet is not None:
                packet = dict(packet)
                kind = packet.get("__class__")
                entity_uuid = str(packet.get("uuid", ""))
                if kind == "EntityUpdate" and entity_uuid in self._removed_entities:
                    return True
                if kind == "WorldLoadStart":
                    for pending_uuid in tuple(self._updates):
                        self._discard_update(pending_uuid)
                    self._attributes.clear()
                    self._removed_entities.clear()
                elif kind in {"EntitySpawn", "EntityRemove"}:
                    self._discard_update(entity_uuid)
                    self._attributes.pop(entity_uuid, None)
                    if kind == "EntityRemove":
                        self._removed_entities[entity_uuid] = True
                        if len(self._removed_entities) > 4096:
                            self._removed_entities.popitem(last=False)
                    else:
                        self._removed_entities.pop(entity_uuid, None)
                elif kind == "Teleport":
                    self._discard_update(entity_uuid)
                elif kind == "AttributeUpdate":
                    # An explicit attribute packet supersedes unread attributes
                    # in an older movement packet, even if that packet is
                    # subsequently merged with newer position-only updates.
                    sequence = self._updates.get(entity_uuid)
                    entry = self._frames.get(sequence)
                    if entry is not None and "attributes" in entry.packet:
                        self._pending_bytes -= len(entry.frame)
                        entry.packet.pop("attributes")
                        entry.frame = self._encode(entry.packet)
                        self._pending_bytes += len(entry.frame)
                    self._attributes.pop(entity_uuid, None)
                if kind in {"EntitySpawn", "EntityUpdate"} and "attributes" in packet:
                    attributes = packet["attributes"]
                    if kind == "EntityUpdate" and attributes == self._attributes.get(entity_uuid):
                        packet.pop("attributes")
                    else:
                        self._attributes[entity_uuid] = attributes
                        self._attributes.move_to_end(entity_uuid)
                        if len(self._attributes) > self.MAX_ATTRIBUTE_CACHE:
                            self._attributes.popitem(last=False)
                if kind == "EntityUpdate" and entity_uuid:
                    previous = self._discard_update(entity_uuid)
                    if previous is not None:
                        # Keep unread attribute/health changes when a newer
                        # position-only delta supersedes their old position.
                        if "motion" in previous and "motion" in packet:
                            packet["motion"] = {**previous["motion"], **packet["motion"]}
                        packet = {**previous, **packet}
                    update_uuid = entity_uuid
                    frame = self._encode(packet)
            if self._pending_bytes + len(frame) > self.MAX_PENDING_BYTES:
                # Never drop reliable state or grow an unbounded backlog.
                self._closed = True
                self._frames.clear()
                self._updates.clear()
                self._attributes.clear()
                self._removed_entities.clear()
                self._pending_bytes = 0
                self._condition.notify_all()
            else:
                self._sequence += 1
                self._frames[self._sequence] = _QueuedFrame(frame, packet, update_uuid)
                if update_uuid is not None:
                    self._updates[update_uuid] = self._sequence
                self._pending_bytes += len(frame)
                self._condition.notify()
                return True
        logging.warning("Disconnecting slow client: outgoing packet queue exceeded %s bytes",
                        self.MAX_PENDING_BYTES)
        self._shutdown_socket()
        return False

    def close(self):
        with self._condition:
            self._closed = True
            self._frames.clear()
            self._updates.clear()
            self._attributes.clear()
            self._removed_entities.clear()
            self._pending_bytes = 0
            self._condition.notify_all()
        # shutdown wakes a writer blocked in sendall as well as the reader.
        self._shutdown_socket()

    def _shutdown_socket(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def _run(self):
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._frames or self._closed)
                    if self._closed:
                        return
                    batch = []
                    size = 0
                    while self._frames and size < self.BATCH_BYTES:
                        sequence, entry = self._frames.popitem(last=False)
                        if entry.entity_uuid is not None:
                            self._updates.pop(entry.entity_uuid, None)
                        batch.append(entry.frame)
                        size += len(entry.frame)
                    # Keep in-flight bytes counted until sendall completes.
                self.connection.sendall(b"".join(batch))
                with self._condition:
                    if not self._closed:
                        self._pending_bytes -= size
        except OSError as error:
            logging.debug("Socket writer stopped: %s", error)
        finally:
            self.close()
