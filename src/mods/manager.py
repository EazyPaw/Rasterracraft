"""Transactional Mod loading. No renderer or gameplay imports at module level."""

import importlib
import importlib.machinery
import json
import logging
from pathlib import Path
import sys
import tempfile
from time import perf_counter
import types
import uuid
import zipfile

from .effects import ModContext, barrier, current_context, clear_empty_patch_slots
from .manifest import ModInfo, safe_member
from .importer import mod_sources, register_source


class ModError(RuntimeError):
    pass


class RestartRequired(ModError):
    pass


def _run_effects(effects, forward):
    """Restore the pre-operation state if an individual inverse fails."""
    done = []
    try:
        for effect in (effects if forward else reversed(effects)):
            (effect.apply if forward else effect.undo)()
            done.append(effect)
    except BaseException as error:
        errors = []
        for effect in reversed(done):
            try:
                (effect.undo if forward else effect.apply)()
            except BaseException as recovery_error:
                errors.append(str(recovery_error))
        if errors:
            raise ModError(f"{error}; recovery failed: {'; '.join(errors)}; restart required") from error
        raise


class LoadedMod:
    def __init__(self, ctx, modules, temporary):
        self.ctx, self.modules, self.temporary = ctx, modules, temporary

    def dispose(self):
        prefix = self.ctx.package
        for name in tuple(sys.modules):
            if name == prefix or name.startswith(prefix + "."):
                sys.modules.pop(name, None)
        self.ctx.forget()
        mod_sources.roots.pop(prefix, None)
        if self.temporary:
            self.temporary.cleanup()


class Change:
    """Retains unloaded modules/effects until both client and server agree."""

    def __init__(self, manager):
        self.manager = manager
        self.before = list(manager.loaded)
        self.removed = []
        self.added = []
        self.finished = False

    def rollback(self):
        if self.finished:
            return
        self.manager.log(logging.WARNING, "rollback started: remove=%s restore=%s",
                         [r.ctx.namespace for r in self.added], [r.ctx.namespace for r in self.removed])
        with barrier.edit():
            errors = []
            for record in reversed(self.added):
                try:
                    _run_effects(record.ctx.effects, False)
                    record.dispose()
                    self.manager.log(logging.INFO, "rollback removed new Mod: mod=%s", record.ctx.namespace)
                except BaseException as error:
                    self.manager.log(logging.ERROR, "rollback removal failed: mod=%s", record.ctx.namespace, exc_info=True)
                    errors.append(str(error))
            for record in reversed(self.removed):
                try:
                    _run_effects(record.ctx.effects, True)
                    self.manager.log(logging.INFO, "rollback restored previous Mod: mod=%s effects=%d",
                                     record.ctx.namespace, len(record.ctx.effects))
                except BaseException as error:
                    self.manager.log(logging.ERROR, "rollback restoration failed: mod=%s", record.ctx.namespace, exc_info=True)
                    errors.append(str(error))
            self.manager.loaded = self.before
            self.finished = True
            self.manager.pending = None
            clear_empty_patch_slots()
            if errors:
                self.manager.broken = True
                raise ModError("Rollback incomplete; restart required: " + "; ".join(errors))
            self.manager.log(logging.INFO, "rollback complete: loaded=%s", [r.ctx.namespace for r in self.before])

    def commit(self):
        if self.finished:
            return
        # Preparation already drained and detached the removed effects. This
        # phase must not run callbacks or acquire a potentially failing barrier:
        # the peer may already have committed its half of the transaction.
        for record in self.removed:
            try:
                record.dispose()
            except Exception:
                self.manager.log(logging.ERROR, "temporary-file cleanup failed: mod=%s", record.ctx.namespace, exc_info=True)
        self.finished = True
        self.manager.pending = None
        self.manager.log(logging.INFO, "change committed: added=%s removed=%s loaded=%s",
                         [r.ctx.namespace for r in self.added], [r.ctx.namespace for r in self.removed],
                         [r.ctx.namespace for r in self.manager.loaded])
        with barrier.condition:
            if barrier.editor is None:
                clear_empty_patch_slots()


class ModManager:
    def log(self, level, message, *args, **kwargs):
        logging.log(level, "[Mods][%s] " + message, self.side, *args, **kwargs)

    def __init__(self, root, side, app=None):
        self.root = Path(root).resolve()
        self.side, self.app = side, app
        self.directory = self.root / "mods"
        self.catalog = {}
        # Browsing and selection identify sources independently of runtime namespaces.
        self.candidates = {}
        self.diagnostics = []
        self.loaded = []
        self.pending = None
        self.broken = False
        self.in_game = False
        self.config_menus = {}
        self.scan()

    def scan(self):
        if self.pending or self.in_game:
            raise ModError("Mods can only be scanned at the main menu")
        catalog, candidates, diagnostics = {}, {}, []
        self.log(logging.INFO, "scanning: directory=%s", self.directory)
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            paths = sorted(self.directory.iterdir(), key=lambda p: (p.name.casefold(), p.name))
        except OSError as error:
            self.log(logging.ERROR, "scan failed: directory=%s", self.directory, exc_info=True)
            self.catalog, self.diagnostics = {}, [f"mods/: {error}"]
            self.candidates = {}
            return self.diagnostics
        for path in paths:
            if not ((path.is_dir() and (path / "mod.json").is_file())
                    or (path.is_file() and path.suffix.lower() == ".zip")):
                continue
            try:
                info = ModInfo.read(path)
                candidates[info.path] = info
                self.log(logging.DEBUG, "discovered: mod=%s version=%s priority=%s source=%s",
                         info.namespace, info.version, info.priority, info.path)
            except Exception as error:
                self.log(logging.WARNING, "candidate rejected: source=%s reason=%s: %s", path, type(error).__name__, error)
                diagnostics.append(f"{path.name}: {type(error).__name__}: {error}")
        groups = {}
        for info in candidates.values():
            groups.setdefault(info.namespace, []).append(info)
        for namespace, entries in groups.items():
            for info in entries:
                key = namespace if len(entries) == 1 else self.source_key(info)
                catalog[key] = info
        self.catalog, self.diagnostics = catalog, diagnostics
        self.candidates = candidates
        self.log(logging.INFO, "scan complete: discovered=%d loadable=%d diagnostics=%s",
                 len(candidates), len(catalog), diagnostics)
        return diagnostics

    @staticmethod
    def source_key(info):
        return info.namespace + "@" + info.path.name

    def key_for(self, info):
        key = self.source_key(info)
        return key if key in self.catalog else info.namespace

    def resolve_key(self, key):
        if key in self.catalog:
            return key
        for info in self.catalog.values():
            if self.source_key(info) == key:
                return self.key_for(info)
        # A scan may discover extra versions while a previously unique Mod is loaded.
        for record in self.loaded:
            if record.ctx.namespace == key and record.ctx.info.path in self.candidates:
                return self.key_for(self.candidates[record.ctx.info.path])
        return key

    def read_enabled(self):
        path = self.directory / "enabled.json"
        if not path.exists():
            return set()
        data = json.loads(path.read_text(encoding="utf-8"))
        enabled = data.get("enabled") if isinstance(data, dict) else None
        if not isinstance(enabled, list) or any(not isinstance(item, str) for item in enabled):
            raise ModError("Invalid mods/enabled.json")
        return {self.resolve_key(key) for key in enabled}

    def write_enabled(self, enabled):
        path = self.directory / "enabled.json"
        sources = []
        for key in enabled:
            info = self.catalog.get(self.resolve_key(key))
            sources.append(self.source_key(info) if info else key)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"enabled": sorted(sources)}, stream, indent=2, ensure_ascii=False)
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def ordered(self, enabled):
        enabled = {self.resolve_key(key) for key in enabled}
        missing = set(enabled) - self.catalog.keys()
        if missing:
            raise ModError("Missing/invalid Mods: " + ", ".join(sorted(missing)))
        ordered = sorted((self.catalog[key] for key in enabled), key=lambda m: (m.priority, m.namespace))
        positions = {}
        for index, info in enumerate(ordered):
            if info.namespace in positions:
                raise ModError(f"Multiple versions selected for {info.namespace}; disable the current version first")
            positions[info.namespace] = index
        for info in ordered:
            for dependency in info.dependencies:
                if dependency not in positions:
                    raise ModError(f"{info.namespace} requires {dependency}")
                if positions[dependency] >= positions[info.namespace]:
                    raise ModError(f"{dependency} must load before {info.namespace}; adjust priority")
        return ordered

    def _entries(self, info):
        if not getattr(info, self.side + "_required"):
            return []
        return list(dict.fromkeys(info.entrypoints[side] for side in ("common", self.side)
                                  if side in info.entrypoints))

    def target(self, enabled):
        return [info for info in self.ordered(enabled) if self._entries(info)]

    def check_change(self, enabled, startup=False):
        if self.broken:
            raise ModError("Mod state requires a restart")
        if self.in_game:
            raise ModError("Mods can only be changed at the main menu")
        target = self.target(enabled)
        prefix = 0
        while (prefix < min(len(target), len(self.loaded))
               and target[prefix] == self.loaded[prefix].ctx.info):
            prefix += 1
        if not startup:
            for record in self.loaded[prefix:]:
                if not record.ctx.info.hot_unload:
                    raise RestartRequired(f"{record.ctx.namespace}: hot unload unsupported; restart required")
            for info in target[prefix:]:
                if not info.hot_load:
                    raise RestartRequired(f"{info.namespace}: hot load unsupported; restart required")
        return target, prefix

    def prepare(self, enabled, startup=False):
        if self.pending:
            raise ModError("A Mod operation is already pending")
        target, prefix = self.check_change(enabled, startup)
        self.log(logging.INFO, "preparing change: startup=%s order=%s retained_prefix=%d",
                 startup, [info.namespace for info in target], prefix)
        change = Change(self)
        self.pending = change
        try:
            with barrier.edit():
                for record in reversed(self.loaded[prefix:]):
                    started = perf_counter()
                    self.log(logging.INFO, "unload started: mod=%s version=%s effects=%d",
                             record.ctx.namespace, record.ctx.info.version, len(record.ctx.effects))
                    for module in reversed(record.modules):
                        self.log(logging.INFO, "unload callback: mod=%s entry=%s", record.ctx.namespace,
                                 module.__name__.removeprefix(record.ctx.package + "."))
                        module.unload(record.ctx)
                    self.log(logging.DEBUG, "undoing effects: mod=%s count=%d", record.ctx.namespace, len(record.ctx.effects))
                    _run_effects(record.ctx.effects, False)
                    change.removed.append(record)
                    self.loaded.remove(record)
                    self.log(logging.INFO, "unload prepared: mod=%s elapsed_ms=%.1f", record.ctx.namespace,
                             (perf_counter() - started) * 1000)
                for info in target[prefix:]:
                    record = self._load(info)
                    change.added.append(record)
                    self.loaded.append(record)
            return change
        except BaseException as error:
            self.log(logging.ERROR, "change preparation failed; rolling back", exc_info=True)
            try:
                change.rollback()
            except BaseException as recovery:
                raise ModError(f"{error}\n{recovery}") from error
            raise ModError(f"{type(error).__name__}: {error}") from error

    def _load(self, info):
        started = perf_counter()
        self.log(logging.INFO, "load started: mod=%s name=%s version=%s priority=%s source=%s entries=%s",
                 info.namespace, info.name, info.version, info.priority, info.path, self._entries(info))
        if not info.compatible:
            from src.version import GAME_VERSION
            self.log(logging.WARNING, "version mismatch: mod=%s supported=%s current=%s; attempting to load anyway",
                     info.namespace, info.game_versions, GAME_VERSION)
        temporary = None
        root = info.path
        if root.is_file():
            self.log(logging.INFO, "extracting ZIP: mod=%s source=%s", info.namespace, root)
            cache = self.root / "data" / "mod_cache"
            cache.mkdir(parents=True, exist_ok=True)
            temporary = tempfile.TemporaryDirectory(prefix=info.namespace + "_", dir=cache)
            with zipfile.ZipFile(root) as archive:
                for member in archive.infolist():
                    safe_member(member)
                archive.extractall(temporary.name)
            root = Path(temporary.name) / info.prefix
        package = "_pycraft_mod_" + uuid.uuid4().hex
        ctx = ModContext(self, info, package, root)
        modules = []
        record = LoadedMod(ctx, modules, temporary)
        namespace = types.ModuleType(package)
        namespace.__path__ = [str(root)]
        namespace.__package__ = package
        namespace.__spec__ = importlib.machinery.ModuleSpec(package, loader=None, is_package=True)
        sys.modules[package] = namespace
        register_source(package, root)
        token = current_context.set(ctx)
        try:
            importlib.invalidate_caches()
            # Imports and load callbacks may already need their own resources.
            # Mount inside the transaction so an import/load error undoes it.
            if self.side == "client" and self.app is not None:
                self.log(logging.DEBUG, "mounting resources: mod=%s root=%s", info.namespace, root)
                self._mount_resources(ctx)
            # Resolve every lifecycle contract before invoking load callbacks.
            for entry in self._entries(info):
                self.log(logging.INFO, "importing entry: mod=%s entry=%s", info.namespace, entry)
                module = importlib.import_module(package + "." + entry)
                if not callable(getattr(module, "load", None)) or not callable(getattr(module, "unload", None)):
                    raise ModError(f"{info.namespace}:{entry} requires load(ctx) and unload(ctx)")
                modules.append(module)
            for module in modules:
                self.log(logging.INFO, "load callback: mod=%s entry=%s", info.namespace,
                         module.__name__.removeprefix(package + "."))
                module.load(ctx)
            ctx.loading = False
            self.log(logging.INFO, "load prepared: mod=%s effects=%d elapsed_ms=%.1f", info.namespace,
                     len(ctx.effects), (perf_counter() - started) * 1000)
            return record
        except BaseException as error:
            self.log(logging.ERROR, "load failed: mod=%s source=%s; undoing %d effects",
                     info.namespace, info.path, len(ctx.effects), exc_info=True)
            ctx.loading = False
            try:
                _run_effects(ctx.effects, False)
            except BaseException as recovery:
                self.log(logging.ERROR, "load rollback failed: mod=%s; restart required", info.namespace, exc_info=True)
                self.broken = True
                raise ModError(f"{error}; rollback failed: {recovery}; restart required") from error
            finally:
                record.dispose()
            raise
        finally:
            current_context.reset(token)

    def _mount_resources(self, ctx):
        resources = self.app.resources_manager
        root = ctx.root / "assets" / ctx.namespace
        if not root.is_dir():
            return
        ctx.set_item(resources.mod_roots, ctx.namespace, root)
        ctx.action(lambda: resources.clear_mod_cache(ctx.namespace),
                   lambda: resources.clear_mod_cache(ctx.namespace))
        for language, target in (("en_us", resources._fallback_lang_map),
                                 (self.app.language.lower(), resources._lang_map)):
            path = root / "lang" / (language + ".lang")
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    ctx.set_item(target, key.strip(), value)

    def startup(self, enabled=None):
        """Isolate a broken Mod without preventing independent Mods from loading."""
        try:
            enabled = self.read_enabled() if enabled is None else {self.resolve_key(key) for key in enabled}
            missing = enabled - self.catalog.keys()
            if missing:
                self.diagnostics.append("Missing/invalid Mods: " + ", ".join(sorted(missing)))
            target = sorted((self.catalog[key] for key in enabled if key in self.catalog),
                            key=lambda info: (info.priority, info.namespace))
        except Exception as error:
            self.diagnostics.append(str(error))
            self.log(logging.ERROR, "startup configuration failed", exc_info=True)
            return
        accepted = set()
        for info in target:
            try:
                change = self.prepare(accepted | {self.key_for(info)}, startup=True)
                change.commit()
                accepted.add(self.key_for(info))
            except Exception as error:
                self.diagnostics.append(f"{info.namespace}: {error}")
                self.log(logging.ERROR, "startup skipped failed Mod: mod=%s", info.namespace, exc_info=True)

    def close(self):
        self.in_game = False
        if self.pending:
            self.pending.rollback()
        try:
            self.prepare(set(), startup=True).commit()
        except Exception:
            self.log(logging.ERROR, "shutdown unload failed: loaded=%s",
                     [r.ctx.namespace for r in self.loaded], exc_info=True)

    def network_mods(self):
        return [{"namespace": record.ctx.namespace, "version": record.ctx.info.version,
                 "server_required": record.ctx.info.server_required,
                 "client_required": record.ctx.info.client_required,
                 "client_loaded": self.side == "client"} for record in self.loaded]
