"""Validate loaded Mods against independent client/server requirements."""

from typing import cast

from .manager import ModError, ModManager
from .manifest import SIDE_REQUIREMENTS
from .types import NetworkMod


class ModMismatch(ModError):
    pass


def validate_client_mods(manager: ModManager | None, incoming: object) -> None:
    if not isinstance(incoming, list) or len(incoming) > 512:
        raise ModMismatch("Invalid Mod list")
    client: dict[str, NetworkMod] = {}
    for entry in incoming:
        if (not isinstance(entry, dict) or not isinstance(entry.get("namespace"), str)
                or not entry["namespace"].strip()
                or not isinstance(entry.get("version"), str)
                or not entry["version"].strip()
                or any(entry.get(side) not in SIDE_REQUIREMENTS for side in ("client", "server"))
                or entry["client"] == "unsupported"):
            raise ModMismatch("Invalid Mod manifest in handshake")
        key = entry["namespace"]
        if key in client:
            raise ModMismatch("Duplicate Mod in handshake")
        client[key] = cast(NetworkMod, entry)
    server = {entry["namespace"]: entry for entry in manager.network_mods()} if manager else {}
    problems = []
    for key, entry in server.items():
        if entry["client"] == "required" and key not in client:
            problems.append(f"client: {key}@{entry['version']} required")
    for key, entry in client.items():
        other = server.get(key)
        if other is None:
            if entry["server"] == "required":
                problems.append(f"server: {key}@{entry['version']} required")
            continue
        if other["client"] == "unsupported" or entry["server"] == "unsupported":
            problems.append(f"{key}: peer runtime unsupported")
        if other["version"] != entry["version"]:
            problems.append(f"{key}: client version {entry['version']} != server version {other['version']}")
    if problems:
        raise ModMismatch("; ".join(problems))
