"""Read metadata without importing any Mod code."""

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

from src.version import GAME_VERSION


def _version(value):
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[-+][\w.-]+)?", value)
    if not match:
        raise ValueError(f"Invalid game version: {value}")
    return tuple(int(part or 0) for part in match.groups())


def matches_versions(requirement, current=GAME_VERSION):
    """Lists and || are OR; comma-separated comparisons are AND."""
    if isinstance(requirement, list):
        if not requirement:
            raise ValueError("game_versions cannot be empty")
        matches = [matches_versions(item, current) for item in requirement]
        return any(matches)
    if not isinstance(requirement, str) or not requirement.strip():
        raise ValueError("game_versions must be a string or a list of strings")
    results = []
    for alternative in requirement.split("||"):
        comparisons = []
        for term in alternative.split(","):
            term = term.strip()
            if term == "*":
                comparisons.append(True)
                continue
            match = re.fullmatch(r"(>=|<=|==|!=|>|<|=)?\s*(\S+)", term)
            if not match:
                raise ValueError(f"Invalid game version range: {term}")
            op, wanted = match.groups()
            a, b = _version(current), _version(wanted)
            comparisons.append({None: a == b, "=": a == b, "==": a == b,
                                "!=": a != b, ">": a > b, "<": a < b,
                                ">=": a >= b, "<=": a <= b}[op])
        results.append(all(comparisons))
    return any(results)


def safe_member(info):
    name = info.filename
    path = PurePosixPath(name)
    if ("\\" in name or path.is_absolute() or ".." in path.parts
            or any(":" in part for part in path.parts)
            or stat.S_ISLNK(info.external_attr >> 16)):
        raise ValueError(f"Unsafe ZIP member: {name}")
    return path


@dataclass(frozen=True)
class ModInfo:
    path: Path
    prefix: str
    namespace: str
    name: str
    authors: tuple[str, ...]
    version: str
    description: str
    game_versions: str | list
    hot_load: bool
    hot_unload: bool
    server_required: bool
    client_required: bool
    priority: int
    entrypoints: dict
    dependencies: tuple[str, ...]
    compatible: bool

    @classmethod
    def read(cls, path):
        prefix = ""
        if path.is_dir():
            raw = (path / "mod.json").read_text(encoding="utf-8-sig")
            if not (path / "icon.png").is_file():
                raise ValueError("Missing icon.png")
        else:
            with zipfile.ZipFile(path) as archive:
                names = set()
                for member in archive.infolist():
                    safe_member(member)
                    if member.filename in names:
                        raise ValueError(f"Duplicate ZIP member: {member.filename}")
                    names.add(member.filename)
                candidates = [name for name in names if name == "mod.json"
                              or (name.endswith("/mod.json") and name.count("/") == 1)]
                if len(candidates) != 1:
                    raise ValueError("ZIP must contain one root mod.json (or one enclosing folder)")
                manifest = candidates[0]
                prefix = manifest[:-len("mod.json")]
                raw = archive.read(manifest).decode("utf-8-sig")
                if prefix + "icon.png" not in names:
                    raise ValueError("Missing icon.png")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("mod.json must be an object")
        for field in ("namespace", "name", "version", "description"):
            if not isinstance(data.get(field), str) or not data[field].strip():
                raise ValueError(f"Missing or invalid {field}")
        namespace = data["namespace"]
        if (not re.fullmatch(r"[a-z][a-z0-9_.-]*", namespace)
                or namespace in ("minecraft", "rasterracraft")):
            raise ValueError("Invalid or reserved namespace")
        authors = data.get("authors")
        if isinstance(authors, str):
            authors = [authors]
        if not isinstance(authors, list) or not authors or any(
                not isinstance(author, str) or not author.strip() for author in authors):
            raise ValueError("authors must be a nonempty string/list")
        for field in ("hot_load", "hot_unload", "server_required", "client_required"):
            if type(data.get(field)) is not bool:
                raise ValueError(f"{field} must be boolean")
        if type(data.get("priority")) is not int:
            raise ValueError("priority must be an integer")
        entries = data.get("entrypoints")
        if not isinstance(entries, dict) or not entries:
            raise ValueError("entrypoints must declare common, client and/or server modules")
        for side, module in entries.items():
            if side not in ("common", "client", "server") or not isinstance(module, str) or not re.fullmatch(
                    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module):
                raise ValueError(f"Invalid entrypoint: {side}={module}")
        if not (data["server_required"] or data["client_required"]):
            raise ValueError("At least one runtime must be required")
        for side in ("server", "client"):
            required = data[side + "_required"]
            if required and side not in entries and "common" not in entries:
                raise ValueError(f"{side}_required needs a {side}/common entrypoint")
            if not required and side in entries:
                raise ValueError(f"{side} entrypoint conflicts with {side}_required=false")
        dependencies = data.get("dependencies", [])
        if (not isinstance(dependencies, list) or any(not isinstance(item, str)
                or not re.fullmatch(r"[a-z][a-z0-9_.-]*", item) for item in dependencies)):
            raise ValueError("dependencies must be a list of namespaces")
        versions = data.get("game_versions")
        compatible = matches_versions(versions)
        return cls(path.resolve(), prefix, namespace, data["name"], tuple(authors),
                   data["version"], data["description"], versions, data["hot_load"],
                   data["hot_unload"], data["server_required"], data["client_required"],
                   data["priority"], entries, tuple(dependencies), compatible)

    def read_file(self, name):
        if self.path.is_dir():
            return (self.path / name).read_bytes()
        with zipfile.ZipFile(self.path) as archive:
            return archive.read(self.prefix + name)
