"""Ownership, reversible effects and a barrier for managed method calls."""

from contextlib import contextmanager
from contextvars import ContextVar
import functools
import inspect
import threading
import time


current_context = ContextVar("mod_registration_context", default=None)
_contexts = {}
MISSING = object()


def registration_context(cls):
    # Importing a builtin while importing a Mod must not transfer its ownership.
    module = cls.__module__
    ctx = current_context.get()
    if ctx and (module == ctx.package or module.startswith(ctx.package + ".")):
        return ctx
    for prefix, ctx in tuple(_contexts.items()):
        if module == prefix or module.startswith(prefix + "."):
            return ctx
    return None


def register_value(mapping, key, value, cls):
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

    def __init__(self):
        self.condition = threading.Condition(threading.RLock())
        self.active = 0
        self.editor = None
        self.local = threading.local()

    @contextmanager
    def call(self):
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
    def edit(self, timeout=3.0):
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
    def __init__(self, apply, undo):
        self.apply = apply
        self.undo = undo


class PatchSlot:
    def __init__(self, owner, name):
        self.owner, self.name = owner, name
        self.original = vars(owner).get(name, MISSING)
        raw = inspect.getattr_static(owner, name)
        self.kind = type(raw) if isinstance(raw, (staticmethod, classmethod)) else None
        self.base = raw.__func__ if self.kind else raw
        if not callable(self.base) or isinstance(raw, property):
            raise TypeError("wrap/replace require a synchronous method or function")
        if inspect.iscoroutinefunction(self.base) or inspect.isgeneratorfunction(self.base):
            raise TypeError("Async and generator functions cannot be managed patches")
        self.entries = []
        self.chain = self.base

        def dispatch(*args, **kwargs):
            with barrier.call():
                return self.chain(*args, **kwargs)

        functools.update_wrapper(dispatch, self.base)
        self.dispatch = dispatch
        self.installed = self.kind(dispatch) if self.kind else dispatch

    def check(self):
        expected = self.installed if self.entries else self.original
        if vars(self.owner).get(self.name, MISSING) is not expected:
            raise RuntimeError(f"Unmanaged modification of {self.owner}.{self.name}")

    def rebuild(self):
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


_slots = {}


def clear_empty_patch_slots():
    for key, slot in tuple(_slots.items()):
        if not slot.entries:
            _slots.pop(key, None)


class PatchFacade:
    def __init__(self, context):
        self.context = context

    def wrap(self, owner, name, function):
        return self._add(owner, name, function, "wrap")

    def replace(self, owner, name, function):
        return self._add(owner, name, function, "replace")

    def _add(self, owner, name, function, kind):
        if not callable(function):
            raise TypeError("Patch must be callable")
        if inspect.iscoroutinefunction(function) or inspect.isgeneratorfunction(function):
            raise TypeError("Async and generator patches are unsupported")
        ctx = self.context
        slot_key = (id(owner), name)
        slot = _slots.get(slot_key)
        if slot is None:
            slot = _slots[slot_key] = PatchSlot(owner, name)
        entry = (ctx.info.priority, ctx.info.namespace, len(ctx.effects), kind, function)

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
    def __init__(self, manager, info, package, root):
        self.manager, self.info = manager, info
        self.package, self.root = package, root
        self.side = manager.side
        self.namespace = info.namespace
        self.effects = []
        self.patches = PatchFacade(self)
        self.loading = True
        _contexts[package] = self

    @property
    def app(self):
        """Client, current Server, or None while the server is at the main menu."""
        return self.manager.app

    @property
    def data_dir(self):
        path = self.manager.root / "data" / "mods" / self.namespace
        path.mkdir(parents=True, exist_ok=True)
        return path

    def action(self, apply, undo):
        """Apply a reversible operation; both functions must be repeatable."""
        if not self.loading:
            raise RuntimeError("Register effects only during import/load(ctx)")
        if not callable(apply) or not callable(undo):
            raise TypeError("action requires apply and undo callables")
        # The apply callback must be atomic if it raises.
        apply()
        self.effects.append(Effect(apply, undo))

    def set_item(self, mapping, key, value):
        old = mapping.get(key, MISSING)

        def undo():
            if mapping.get(key, MISSING) is not value:
                raise RuntimeError(f"Unmanaged change to registry key {key}")
            if old is MISSING:
                del mapping[key]
            else:
                mapping[key] = old

        self.action(lambda: mapping.__setitem__(key, value), undo)

    def set_attr(self, owner, name, value):
        old = vars(owner).get(name, MISSING)

        def undo():
            if vars(owner).get(name, MISSING) is not value:
                raise RuntimeError(f"Unmanaged change to attribute {name}")
            if old is MISSING:
                delattr(owner, name)
            else:
                setattr(owner, name, old)

        self.action(lambda: setattr(owner, name, value), undo)

    def forget(self):
        _contexts.pop(self.package, None)
