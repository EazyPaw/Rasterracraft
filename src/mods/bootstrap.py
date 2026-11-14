"""Read graphics backend requests before SDL creates its first window.

No mod code is imported here. The environment always takes precedence. A mod
enabled after window creation can use its software fallback until next launch.
"""

import json
from pathlib import Path

from .manifest import ModInfo


def preferred_shader_mode(root):
    directory = Path(root) / "mods"
    try:
        enabled = set(json.loads((directory / "enabled.json").read_text(encoding="utf-8"))["enabled"])
        for path in directory.iterdir():
            if path.is_dir() and (path / "mod.json").is_file() or path.is_file() and path.suffix.lower() == ".zip":
                try:
                    info = ModInfo.read(path)
                    if info.namespace in enabled and info.client_required and info.render_backend == "opengl":
                        return "always"
                except Exception:
                    # Invalid ZIPs/manifests are diagnosed by the real loader;
                    # a backend preference must never prevent opening the game.
                    continue
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return "auto"
