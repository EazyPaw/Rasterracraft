"""Integrated server Mod runtime, kept alive while the player is in menus.

Mod lifecycle code executes in this process, never in the client's process.
The private loopback socket is independent of the gameplay protocol.
"""

import json
import logging
import os
from pathlib import Path
import queue
import socket
import struct
import threading
import traceback

from .manager import ModError, ModManager


def send_message(connection, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    connection.sendall(struct.pack(">I", len(data)) + data)


def receive_message(connection):
    def exact(length):
        result = bytearray()
        while len(result) < length:
            chunk = connection.recv(length - len(result))
            if not chunk:
                raise EOFError("Mod host disconnected")
            result.extend(chunk)
        return bytes(result)

    length = struct.unpack(">I", exact(4))[0]
    if length > 8 * 1024 * 1024:
        raise ModError("Oversized Mod control message")
    return json.loads(exact(length))


class Host:
    def __init__(self, connection, root):
        self.connection = connection
        self.manager = ModManager(root, "server")
        self.requests = queue.Queue()
        self.server = None
        self.running = True
        self.start_pending = False
        self.manager.startup()
        self.load_errors = list(self.manager.diagnostics)
        threading.Thread(target=self.read, name="ModControlReader", daemon=True).start()

    def read(self):
        try:
            while True:
                self.requests.put(receive_message(self.connection))
        except (EOFError, OSError, ValueError):
            self.requests.put({"op": "quit", "disconnected": True})

    def reply(self, **result):
        send_message(self.connection, result)

    def status(self):
        return {"loaded": [record.ctx.namespace for record in self.manager.loaded],
                "mods": self.manager.network_mods(),
                "diagnostics": list(dict.fromkeys(self.manager.diagnostics + self.load_errors)),
                "broken": self.manager.broken}

    def started(self):
        if self.start_pending:
            self.start_pending = False
            self.reply(ok=True, **self.status())

    def pump(self):
        """Called at server Tick boundaries; only stop/status are legal in-game."""
        while not self.requests.empty():
            self.dispatch(self.requests.get_nowait())

    def dispatch(self, request):
        op = request.get("op")
        try:
            if op in ("stop", "quit"):
                if self.server is not None:
                    self.server.close_server()
                if op == "quit":
                    self.running = False
                if not request.get("disconnected"):
                    self.reply(ok=True)
                return
            if op == "status":
                self.reply(ok=True, **self.status())
                return
            if self.server is not None:
                raise ModError("Mods can only be changed at the main menu")
            if op == "scan":
                self.manager.scan()
            elif op == "check":
                self.manager.check_change(set(request["enabled"]))
            elif op == "prepare":
                self.manager.prepare(set(request["enabled"]))
            elif op == "commit":
                if self.manager.pending:
                    self.manager.pending.commit()
            elif op == "rollback":
                if self.manager.pending:
                    self.manager.pending.rollback()
            elif op == "start":
                if self.manager.pending or self.manager.broken:
                    raise ModError("Unfinished Mod operation; restart required")
                self.start_pending = True
                self.start_server(request.get("save_id"))
                return
            else:
                raise ModError(f"Unknown Mod host operation: {op}")
            self.reply(ok=True, **self.status())
        except BaseException as error:
            logging.exception("[Mods][server] host request failed: op=%s desired=%s loaded=%s",
                              op, request.get("enabled"), [r.ctx.namespace for r in self.manager.loaded])
            if op == "start" and not self.start_pending:
                # The start reply has already been delivered. Gameplay transport
                # disconnects the player; do not poison the next RPC response.
                return
            self.start_pending = False
            self.reply(ok=False, error=f"{type(error).__name__}: {error}",
                       error_type=type(error).__name__, trace=traceback.format_exc(), **self.status())

    def start_server(self, save_id):
        from src.server.server_main import Server

        try:
            # Patches are installed before creating the Server instance.
            self.server = Server(integrated=True, save_id=save_id, mod_manager=self.manager)
            self.server.mod_host = self
            self.manager.in_game = True
            self.server.init()
        finally:
            if self.server is not None and self.server.running:
                self.server.close_server()
            self.server = None
            self.manager.app = None
            self.manager.in_game = False

    def run(self):
        try:
            while self.running:
                self.dispatch(self.requests.get())
        finally:
            self.manager.close()
            self.connection.close()


def run_host():
    port = int(os.environ.pop("PYCRAFT_MOD_HOST_PORT"))
    secret = os.environ.pop("PYCRAFT_MOD_HOST_SECRET")
    root = Path(os.environ.pop("PYCRAFT_MOD_ROOT"))
    connection = socket.create_connection(("127.0.0.1", port), timeout=15)
    connection.settimeout(None)
    send_message(connection, {"secret": secret})
    Host(connection, root).run()
