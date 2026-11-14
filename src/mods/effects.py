"""Ownership, reversible effects and a barrier for managed method calls."""

from __future__ import annotations

from collections.abc import Callable, Iterator, MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
import functools
import inspect
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from .types import Action, ConfigMenuFactory, ModSide

if TYPE_CHECKING:
    from src.client.client_main import Client
    from src.server.server_main import Server
    from .manager import ModManager
    from .manifest import ModInfo

K = TypeVar("K")
V = TypeVar("V")
PatchKind = Literal["wrap", "replace"]
# A slot composes independently typed methods selected by an attribute name.
PatchEntry = tuple[int, str, int, PatchKind, Callable[..., Any]]


current_context: ContextVar[ModContext | None] = ContextVar("mod_registration_context", default=None)
_contexts: dict[str, ModContext] = {}
MISSING = object()


def registration_context(cls: type) -> ModContext | None:
    # Importing a builtin while importing a Mod must not transfer its ownership.
    module = cls.__module__
    ctx = current_context.get()
    if ctx and (module == ctx.package or module.startswith(ctx.package + ".")):
        return ctx
    for prefix, ctx in tuple(_contexts.items()):
        if module == prefix or module.startswith(prefix + "."):
            return ctx
    return None


def register_value(mapping: MutableMapping[K, V], key: K, value: V, cls: type) -> None:
    existing = mapping.get(key, MISSING)
    if existing is not MISSING and existing is not value and existing != value:
        raise ValueError(f"Duplicate registration: {key}")
    ctx = registration_context(cls)
    if ctx:
        ctx.set_item(mapping, key, value)
    else:
        mapping[key] = value


class CallBarrier:
    """Concurrent calls run normally; edits wait for managed calls to finish."""

    def __init__(self) -> None:
        self.condition = threading.Condition(threading.RLock())
        self.active = 0
        self.editor: int | None = None
        self.local = threading.local()

    @contextmanager
    def call(self) -> Iterator[None]:
        ident = threading.get_ident()
        with self.condition:
            while (self.editor is not None and self.editor != ident
                   and not getattr(self.local, "depth", 0)):
                self.condition.wait()
            self.active += 1
            self.local.depth = getattr(self.local, "depth", 0) + 1
        try:
            yield
        finally:
            with self.condition:
                self.active -= 1
                self.local.depth -= 1
                self.condition.notify_all()

    @contextmanager
    def edit(self, timeout: float = 3.0) -> Iterator[None]:
        if getattr(self.local, "depth", 0):
            raise RuntimeError("Cannot change Mods from inside a patched call")
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.editor is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Another Mod operation is still running")
                self.condition.wait(remaining)
            self.editor = threading.get_ident()
            try:
                while self.active:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("Mod calls have not finished; retry later")
                    self.condition.wait(remaining)
            except BaseException:
                self.editor = None
                self.condition.notify_all()
                raise
        try:
            yield
        finally:
            with self.condition:
                self.editor = None
                self.condition.notify_all()


barrier = CallBarrier()


class Effect:
    def __init__(self, apply: Action, undo: Action) -> None:
        self.apply = apply
        self.undo = undo


class PatchSlot:
    def __init__(self, owner: object, name: str) -> None:
        self.owner, self.name = owner, name
        self.original = vars(owner).get(name, MISSING)
        raw = inspect.getattr_static(owner, name)
        self.kind = type(raw) if isinstance(raw, (staticmethod, classmethod)) else None
        self.base = raw.__func__ if self.kind else raw
        if not callable(self.base) or isinstance(raw, property):
            raise TypeError("wrap/replace require a synchronous method or function")
        if inspect.iscoroutinefunction(self.base) or inspect.isgeneratorfunction(self.base):
            raise TypeError("Async and generator functions cannot be managed patches")
        self.entries: list[PatchEntry] = []
        self.chain = self.base

        def dispatch(*args, **kwargs):
            with barrier.call():
                return self.chain(*args, **kwargs)

        functools.update_wrapper(dispatch, self.base)
        self.dispatch = dispatch
        self.installed = self.kind(dispatch) if self.kind else dispatch

    def check(self) -> None:
        expected = self.installed if self.entries else self.original
        if vars(self.owner).get(self.name, MISSING) is not expected:
            raise RuntimeError(f"Unmanaged modification of {self.owner}.{self.name}")

    def rebuild(self) -> None:
        chain = next((entry[4] for entry in self.entries if entry[3] == "replace"), self.base)
        # Low priority loads first and is the outermost wrapper.
        for _, _, _, kind, function in reversed(sorted(self.entries, key=lambda e: e[:3])):
            if kind == "wrap":
                next_call = chain

                def chain(*args, _next=next_call, _wrap=function, **kwargs):
                    return _wrap(_next, *args, **kwargs)

        self.chain = chain
        if self.entries:
            setattr(self.owner, self.name, self.installed)
        elif self.original is MISSING:
            delattr(self.owner, self.name)
        else:
            setattr(self.owner, self.name, self.original)


_slots: dict[tuple[int, str], PatchSlot] = {}


def clear_empty_patch_slots() -> None:
    for key, slot in tuple(_slots.items()):
        if not slot.entries:
            _slots.pop(key, None)


class PatchFacade:
    def __init__(self, context: ModContext) -> None:
        self.context = context

    def wrap(self, owner: object, name: str, function: Callable[..., object]) -> None:
        """给现有函数或方法包一层逻辑，卸载模组时自动移除这一层。

        owner 是持有方法的类或模块，name 是方法名字符串，function 是包装函数。
        包装函数接收 ``(next_call, *args, **kwargs)``；next_call 表示下一层
        实现，调用它就能继续执行原有逻辑，也可以修改传入参数或返回结果。
        包装实例方法时，args 的第一个参数是实例 self。

        例如 ``ctx.patches.wrap(Player, "jump", jump_wrapper)``，其中
        ``def jump_wrapper(next_call, player): return next_call(player)``。
        多个包装可以叠加，先加载的模组位于外层；卸载只移除本模组的包装。
        仅可在模块导入或 load(ctx) 中登记；不支持 property、异步函数和生成器。
        """
        return self._add(owner, name, function, "wrap")

    def replace(self, owner: object, name: str, function: Callable[..., object]) -> None:
        """替换函数或方法的基础实现，卸载模组时自动撤销。

        owner 是持有方法的类或模块，name 是方法名字符串，function 是新函数。
        新函数接收原方法的参数（实例方法包含 self），不会额外收到 next_call。
        例如 ``ctx.patches.replace(Player, "jump", new_jump)``。

        其他模组通过 wrap 登记的包装仍然生效；同一方法只能有一个 replace，
        重复替换会报错。仅可在模块导入或 load(ctx) 中登记；
        不支持 property、异步函数和生成器。
        """
        return self._add(owner, name, function, "replace")

    def _add(self, owner: object, name: str, function: Callable[..., Any], kind: PatchKind) -> None:
        if not callable(function):
            raise TypeError("Patch must be callable")
        if inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function):
            raise TypeError("Async and generator patches are unsupported")
        ctx = self.context
        slot_key = (id(owner), name)
        slot = _slots.get(slot_key)
        if slot is None:
            slot = _slots[slot_key] = PatchSlot(owner, name)
        entry: PatchEntry = (ctx.info.priority, ctx.info.namespace, len(ctx.effects), kind, function)

        def apply():
            _slots[slot_key] = slot
            slot.check()
            if kind == "replace" and any(e[3] == kind for e in slot.entries):
                raise RuntimeError(f"Multiple replacements for {name}")
            slot.entries.append(entry)
            slot.rebuild()

        def undo():
            slot.check()
            slot.entries.remove(entry)
            slot.rebuild()

        ctx.action(apply, undo)


class ModContext:
    """模组生命周期上下文，提供能在卸载或加载失败时自动撤销的修改操作。

    set_item 修改字典项，set_attr 修改对象属性，patches.wrap/replace 修改方法，
    action 登记自定义操作。它们会立即生效，只能在模块导入或 load(ctx) 中调用。
    unload(ctx) 无需手动恢复这些修改，加载器会统一撤销。
    客户端入口使用 ClientModContext，服务端入口使用 ServerModContext。
    """

    def __init__(self, manager: ModManager, info: ModInfo, package: str, root: Path) -> None:
        self.manager, self.info = manager, info
        self.package, self.root = package, root
        self.side: ModSide = manager.side
        self.namespace = info.namespace
        self.effects: list[Effect] = []
        self.patches = PatchFacade(self)
        self.loading = True
        _contexts[package] = self

    @property
    def app(self) -> Client | Server | None:
        """当前运行端对象：客户端为 Client，服务端为当前 Server；未开世界时服务端为 None。"""
        return self.manager.app

    @property
    def data_dir(self) -> Path:
        """本模组的数据目录 data/mods/<命名空间>，访问时自动创建，卸载时不删除。"""
        path = self.manager.root / "data" / "mods" / self.namespace
        path.mkdir(parents=True, exist_ok=True)
        return path

    def action(self, apply: Action, undo: Action) -> None:
        """立即执行自定义操作，并登记对应的撤销函数。

        apply 和 undo 都是不接收参数的函数：apply() 应用修改，undo() 恢复修改。
        例如 ``ctx.action(start_worker, stop_worker)``。
        卸载或回滚时加载器调用 undo；恢复模组时可能再次调用 apply，
        因此两者必须支持再次执行。回调自身抛错时不能留下半完成的修改。
        仅可在模块导入或 load(ctx) 中调用。
        """
        if not self.loading:
            raise RuntimeError("Register effects only during import/load(ctx)")
        if not callable(apply) or not callable(undo):
            raise TypeError("action requires apply and undo callables")
        # The apply callback must be atomic if it raises.
        apply()
        self.effects.append(Effect(apply, undo))

    def set_item(self, mapping: MutableMapping[K, V], key: K, value: V) -> None:
        """立即执行 mapping[key] = value，并记录旧值以便自动恢复。

        mapping 是要修改的字典或其他可变映射，key 是键，value 是要放入的新值。
        例如 ``ctx.set_item(textures, ("entity.steve", False, False, False), skin)``
        等价于 ``textures[("entity.steve", False, False, False)] = skin``，
        另外还登记了撤销操作；这里的元组只是一个完整的字典键。

        卸载或回滚时恢复原来的值；如果原先没有这个键，则删除新增项。
        记录的是旧对象引用，不会深拷贝对象内容。若该项之后被未受管理的代码
        换成其他对象，撤销时会报错。仅可在模块导入或 load(ctx) 中调用。
        """
        old = mapping.get(key, MISSING)

        def undo():
            if mapping.get(key, MISSING) is not value:
                raise RuntimeError(f"Unmanaged change to registry key {key}")
            if old is MISSING:
                del mapping[key]
            else:
                mapping[key] = cast(V, old)

        self.action(lambda: mapping.__setitem__(key, value), undo)

    def set_attr(self, owner: object, name: str, value: object) -> None:
        """立即修改对象或类的属性，并记录旧值以便自动恢复。

        owner 是要修改的对象、类或模块，name 是属性名字符串，value 是新值。
        例如 ``ctx.set_attr(Stone, "hardness", 1.0)`` 相当于
        ``Stone.hardness = 1.0``，另外还登记了撤销操作。

        卸载或回滚时恢复原先直接定义的属性；若原先没有直接定义，
        则删除新增属性，让继承的属性重新生效。owner 必须支持 vars() 和属性赋值。
        不会深拷贝旧值；若属性被未受管理的代码换成其他对象，撤销时会报错。
        仅可在模块导入或 load(ctx) 中调用。
        """
        old = vars(owner).get(name, MISSING)

        def undo():
            if vars(owner).get(name, MISSING) is not value:
                raise RuntimeError(f"Unmanaged change to attribute {name}")
            if old is MISSING:
                delattr(owner, name)
            else:
                setattr(owner, name, old)

        self.action(lambda: setattr(owner, name, value), undo)

    def render_hook(self, stage: str, callback: Callable[..., object]) -> None:
        """在客户端指定渲染阶段登记回调，卸载时自动移除。

        stage 是渲染阶段名称，callback 通常接收 render，即 callback(render)。
        events 阶段额外接收可修改的事件列表，并在游戏处理事件之前调用。
        渲染资源应在回调中按需创建，确保创建操作位于渲染线程。
        仅限客户端，且只能在模块导入或 load(ctx) 中登记。
        """
        if self.side != "client" or self.app is None:
            raise RuntimeError("Render hooks require the client runtime")
        extensions = cast("Client", self.app).render.extensions
        key = (self.namespace, len(self.effects))
        self.action(
            lambda: extensions.add(stage, key, callback, self.info.priority),
            lambda: extensions.remove(stage, key),
        )

    def forget(self) -> None:
        _contexts.pop(self.package, None)

    def config_menu(self, factory: ConfigMenuFactory) -> None:
        """登记本模组的客户端设置界面工厂，卸载时自动移除。

        factory 是函数，调用形式为 factory(render, parent)，返回一个 GUI 界面。
        加载器保存的是工厂函数，在打开设置时才创建界面。
        仅限客户端，且只能在模块导入或 load(ctx) 中登记。
        """
        if self.side != "client" or not callable(factory):
            raise TypeError("Configuration menus require a client GUI factory")
        self.set_item(self.manager.config_menus, self.namespace, factory)


class ClientModContext(ModContext):
    """客户端模组上下文，app 始终指向正在运行的 Client。"""

    @property
    def app(self) -> Client:
        """正在运行的客户端，可通过它访问资源管理器、渲染器等。"""
        return cast("Client", self.manager.app)


class ServerModContext(ModContext):
    """服务端模组上下文，未开世界时 app 为 None，开世界后为当前 Server。"""

    @property
    def app(self) -> Server | None:
        """当前服务端实例；主菜单期间为 None，访问前应判断是否存在。"""
        return cast("Server | None", self.manager.app)
