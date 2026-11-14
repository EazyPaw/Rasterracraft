"""Main-menu coordinator: reversible changes in both local runtimes."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
from time import perf_counter
from typing import TYPE_CHECKING, Literal

from .host import receive_message, send_message
from .manager import ModError, ModManager, RestartRequired
from .types import HostStatus, NetworkMod

if TYPE_CHECKING:
    from src.client.client_main import Client


class ClientModService:
    def __init__(self, client: Client, root: str | Path) -> None:
        self.client = client
        self.manager = ModManager(root, "client", client)
        self.root = Path(root).resolve()
        self.connection: socket.socket | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.lock = threading.RLock()
        self.busy = False
        self.uncertain = False
        self.server_status: HostStatus = {"loaded": [], "diagnostics": []}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ModHost")
        self.start_future: Future[HostStatus] | None = None
        self.errors: list[str] = []
        try:
            self.desired = self.manager.read_enabled()
        except Exception as error:
            self.desired = set()
            self.errors.append(str(error))
        self.manager.startup(self.desired)
        self.errors.extend(self.manager.diagnostics)

    def ensure_host(self) -> None:
        if self.connection is not None and self.process.poll() is None:
            return
        if self.process is not None and self.process.poll() is not None:
            self.uncertain = True
        if self.uncertain:
            raise ModError("Mod server state is uncertain; restart required")
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(15)
        secret = secrets.token_hex(32)
        environment = os.environ.copy()
        environment.update(PYCRAFT_MOD_HOST_PORT=str(listener.getsockname()[1]),
                           PYCRAFT_MOD_HOST_SECRET=secret, PYCRAFT_MOD_ROOT=str(self.root))
        environment.pop("PYCRAFT_CLIENT", None)
        for key in ("PYTHONPATH", "PYTHONHOME", "NUITKA_ONEFILE_PARENT", "NUITKA_RESUME_FILENAME"):
            environment.pop(key, None)
        try:
            self.process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve().parents[2] / "start_server.py"), "--mod-host"],
                cwd=self.root, env=environment,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            connection, _ = listener.accept()
            connection.settimeout(15)
            if receive_message(connection).get("secret") != secret:
                connection.close()
                raise ModError("Invalid Mod host authentication")
            self.connection = connection
            logging.info("[Mods][coordinator] server host connected: pid=%s", self.process.pid)
        except BaseException:
            if self.process and self.process.poll() is None:
                self.process.terminate()
            self.process = None
            raise
        finally:
            listener.close()

    def rpc(self, op: str, **data: object) -> HostStatus:
        with self.lock:
            self.ensure_host()
            try:
                send_message(self.connection, {"op": op, **data})
                result = receive_message(self.connection)
            except (OSError, EOFError, ValueError) as error:
                self.uncertain = True
                raise ModError(f"Mod host connection failed; restart required: {error}") from error
            if "loaded" in result:
                self.server_status = result
            if not result.get("ok"):
                logging.error("[Mods][coordinator] server request failed: op=%s desired=%s error=%s\n%s",
                              op, data.get("enabled"), result.get("error"), result.get("trace", ""))
                error_type = RestartRequired if result.get("error_type") == "RestartRequired" else ModError
                raise error_type(result.get("error", "Mod host operation failed"))
            return result

    def assert_menu(self) -> None:
        if self.client.game_started or self.client.in_game or self.client.world_loading:
            raise ModError("Mods can only be changed at the main menu")
        if self.uncertain:
            raise ModError("Mod state requires a restart")

    def refresh(self) -> None:
        self.assert_menu()
        self.manager.scan()
        self.desired = {self.manager.resolve_key(key) for key in self.desired}
        # Browsing local graphics mods must not start an integrated server.
        if self.connection is not None or any(
            info.supports("server") for key, info in self.manager.catalog.items() if key in self.desired
        ):
            self.rpc("scan")

    def _set_client_only(self, desired: set[str]) -> Literal["restart"] | None:
        """Keep local-only changes independent of the server control channel."""
        try:
            self.manager.check_change(desired)
        except RestartRequired:
            self.manager.write_enabled(desired)
            self.desired = desired
            return "restart"
        change = self.manager.prepare(desired)
        try:
            self.manager.write_enabled(desired)
        except BaseException:
            change.rollback()
            raise
        change.commit()
        self.desired = desired

    def set_enabled(self, namespace: str, enabled: bool) -> Literal["enabled", "disabled", "restart"]:
        self.assert_menu()
        if self.busy:
            raise ModError("A Mod operation is already pending")
        namespace = self.manager.resolve_key(namespace)
        if namespace not in self.manager.catalog:
            raise ModError(f"Unknown Mod: {namespace}")
        self.busy = True
        started = perf_counter()
        action = "enable" if enabled else "disable"
        logging.info("[Mods][coordinator] request: action=%s mod=%s previous=%s", action, namespace, sorted(self.desired))
        desired = (self.desired | {namespace} if enabled else self.desired - {namespace}) & self.manager.catalog.keys()
        local_change = None
        remote_prepared = False
        old_desired = set(self.desired)
        saved = False
        try:
            self.manager.ordered(desired)
            changed = old_desired ^ desired
            if changed and all(not self.manager.catalog[key].supports("server") for key in changed):
                result = self._set_client_only(desired)
                return result or ("enabled" if enabled else "disabled")
            # Initialize the server against the CURRENT settings before saving
            # any deferred change. Both runtimes must share the same snapshot.
            self.rpc("status")
            try:
                self.manager.check_change(desired)
                self.rpc("check", enabled=sorted(desired))
            except RestartRequired as reason:
                self.manager.write_enabled(desired)
                self.desired = desired
                logging.info("[Mods][coordinator] deferred until restart: action=%s mod=%s reason=%s desired=%s",
                             action, namespace, reason, sorted(desired))
                return "restart"
            self.rpc("prepare", enabled=sorted(desired))
            remote_prepared = True
            local_change = self.manager.prepare(desired)
            self.manager.write_enabled(desired)
            saved = True
            self.rpc("commit")
            remote_prepared = False
            local_change.commit()
            self.desired = desired
            logging.info("[Mods][coordinator] operation complete: action=%s mod=%s desired=%s elapsed_ms=%.1f",
                         action, namespace, sorted(desired), (perf_counter() - started) * 1000)
            return "enabled" if enabled else "disabled"
        except BaseException as error:
            recovery = []
            if local_change:
                try:
                    local_change.rollback()
                except BaseException as failure:
                    recovery.append(str(failure))
            if remote_prepared and not self.uncertain:
                try:
                    self.rpc("rollback")
                except BaseException as failure:
                    recovery.append(str(failure))
            if saved:
                try:
                    self.manager.write_enabled(old_desired)
                except Exception as failure:
                    recovery.append(str(failure))
            if recovery:
                self.uncertain = True
            logging.exception("[Mods][coordinator] operation failed: action=%s mod=%s desired=%s "
                              "rollback=%s uncertain=%s elapsed_ms=%.1f", action, namespace, sorted(desired),
                              recovery or "complete", self.uncertain, (perf_counter() - started) * 1000)
            raise ModError(str(error) + ("\nRollback: " + "; ".join(recovery) if recovery else "")) from error
        finally:
            self.busy = False

    def start_server(self, save_id: str | None) -> None:
        if self.busy or self.uncertain or self.manager.broken:
            raise ModError("Mod operation unfinished; restart required")
        self.start_future = self.executor.submit(self.rpc, "start", save_id=save_id)

    def network_mods(self) -> list[NetworkMod]:
        # A remote server must see only code loaded on this client, never Mods
        # that happen to be enabled in the local integrated server.
        return self.manager.network_mods()

    def poll(self) -> None:
        if self.start_future and self.start_future.done():
            future, self.start_future = self.start_future, None
            try:
                future.result()
            except Exception as error:
                self.client.show_disconnect("connect.failed", str(error))

    def stop_server(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        try:
            self.rpc("stop")
        except Exception:
            logging.exception("Failed to stop integrated Mod server")

    def close(self) -> None:
        try:
            if self.process and self.process.poll() is None and not self.uncertain:
                self.rpc("quit")
        except Exception:
            logging.exception("Failed to close Mod host")
        finally:
            if self.connection:
                self.connection.close()
                self.connection = None
            if self.process:
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.manager.close()
