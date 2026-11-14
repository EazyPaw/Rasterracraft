"""Read graphics backend requests before SDL creates its first window.

No mod code is imported here. The environment always takes precedence. A mod
enabled after window creation can use its software fallback until next launch.
"""

import json
from pathlib import Path
from typing import Literal

from .manifest import ModInfo


def preferred_shader_mode(root: str | Path) -> Literal["auto", "always"]:
    directory = Path(root) / "mods"
    try:
        enabled = json.loads((directory / "enabled.json").read_text(encoding="utf-8"))["enabled"]
        if not isinstance(enabled, list) or any(not isinstance(key, str) for key in enabled):
            return "auto"
        enabled = set(enabled)
        candidates = []
        for path in directory.iterdir():
            if path.is_dir() and (path / "mod.json").is_file() or path.is_file() and path.suffix.lower() == ".zip":
                try:
                    info = ModInfo.read(path)
                    candidates.append(info)
                except Exception:
                    # Invalid ZIPs/manifests are diagnosed by the real loader;
                    # a backend preference must never prevent opening the game.
                    continue
        counts = {}
        for info in candidates:
            counts[info.namespace] = counts.get(info.namespace, 0) + 1
        for info in candidates:
            # Match exactly the source selected by the main-menu loader. Old
            # namespace-only preferences remain valid for a unique source;
            # duplicate versions must never select an arbitrary GPU backend.
            selected = info.source_key in enabled or (
                info.namespace in enabled and counts[info.namespace] == 1)
            if selected and info.compatible and info.supports("client") and info.render_backend == "opengl":
                return "always"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return "auto"
