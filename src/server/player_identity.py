"""Minecraft-compatible name-based identities for offline players."""

import hashlib
import uuid


def player_uuid_from_name(player_name: str) -> uuid.UUID:
    """Match Java's UUID.nameUUIDFromBytes for ``OfflinePlayer:<name>``."""
    name = str(player_name)
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return uuid.UUID(bytes=bytes(digest))


def random_player_name() -> str:
    return f"Player_{uuid.uuid4().hex[:8]}"
