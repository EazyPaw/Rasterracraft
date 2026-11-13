"""Match only the Mods whose manifests require the peer runtime."""

from .manager import ModError


class ModMismatch(ModError):
    pass


def validate_client_mods(manager, incoming):
    if not isinstance(incoming, list) or len(incoming) > 512:
        raise ModMismatch("Invalid Mod list")
    client = {}
    for entry in incoming:
        if (not isinstance(entry, dict) or not isinstance(entry.get("namespace"), str)
                or not isinstance(entry.get("version"), str)
                or any(type(entry.get(key)) is not bool for key in (
                    "server_required", "client_required", "client_loaded"))):
            raise ModMismatch("Invalid Mod manifest in handshake")
        key = entry["namespace"]
        if key in client:
            raise ModMismatch("Duplicate Mod in handshake")
        client[key] = entry
    server = {entry["namespace"]: entry for entry in manager.network_mods()} if manager else {}
    problems = []
    for key, entry in server.items():
        if entry["client_required"]:
            other = client.get(key, {})
            if other.get("version") != entry["version"] or not other.get("client_loaded"):
                problems.append(f"client: {key}@{entry['version']}")
    for key, entry in client.items():
        if entry["server_required"] and server.get(key, {}).get("version") != entry["version"]:
            problems.append(f"server: {key}@{entry['version']}")
    if problems:
        raise ModMismatch("; ".join(problems))
