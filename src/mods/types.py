"""Public Mod contracts. Runtime imports never initialize game/GUI modules."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal, Protocol, TypeAlias, TypedDict

if TYPE_CHECKING:
    from src.client.GUI.gui import GUI
    from src.client.GUI.mods_menu import ModsMenu
    from src.client.render.renderer import Render
    from .effects import ModContext


class LifecycleModule(Protocol):
    __name__: str

    def load(self, ctx: ModContext) -> None: ...
    def unload(self, ctx: ModContext) -> None: ...


ModSide: TypeAlias = Literal["client", "server"]
EntrySide: TypeAlias = Literal["common", "client", "server"]
SideRequirement: TypeAlias = Literal["unsupported", "optional", "required"]
RenderBackend: TypeAlias = Literal["software", "opengl"]
VersionRequirement: TypeAlias = str | list[str]


class NetworkMod(TypedDict):
    namespace: str
    version: str
    client: SideRequirement
    server: SideRequirement


class HostStatus(TypedDict, total=False):
    ok: bool
    loaded: list[str]
    mods: list[NetworkMod]
    diagnostics: list[str]
    broken: bool
    error: str
    error_type: str
    trace: str


ConfigMenuFactory: TypeAlias = Callable[["Render", "ModsMenu"], "GUI"]
Action: TypeAlias = Callable[[], object]
