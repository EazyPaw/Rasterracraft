import logging
import os
import socket
import struct
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

import msgpack
import pygame

from resources.client import render, client_world
from resources.client.client_packets import decode_packet, encode_packet
from resources.client.game_manager import GameManager
from resources.client.client_player import ClientPlayer
from resources.client.GUI.main_menu import MainMenu
from resources.client.GUI.pause_menu import PauseMenu
from resources.client.GUI.saves_menu import SavesMenu
from resources.client.GUI.loading_screen import LoadingScreen
from resources.client.GUI.disconnect_screen import DisconnectScreen
from resources.client.GUI.death_screen import DeathScreen
from resources.client.particles import ParticleManager
from resources.client.resources_manager import ResourcesManager
from resources.server import save_manager
from resources.server.server_main import Server
from resources.server.text import Text
from resources.server.utils import recv_exact, set_client

class Client:
    def __init__(self):
        # 初始化剪贴板（Ctrl+V 粘贴用）
        try:
            pygame.scrap.init()
        except Exception:
            pass
        self.is_shutting_down = False
        self._shutdown_lock = threading.Lock()
        self._shutdown_started = False
        self.version = "0.0.1 SNAPSHOT - Minecraft 1.8.9"

        self.language = "zh_CN"
        self.fore_place_switch_mode = "switch"

        self.client_world = client_world.ClientWorld(self)
        self.render = render.Render(self)
        self._prepare_socket_transport()
        # 服务端启动模式: "threading" 或 "subprocess"
        #   threading  - 在同一进程内以线程方式运行（受 GIL 影响，高负载时客户端可能卡顿）
        #   subprocess - 以独立子进程运行（绕过 GIL，性能更好，推荐）
        self.server_mode = "subprocess"
        # 注册客户端实例到 utils 模块，供 @client_method 装饰的方法使用。
        # 在 subprocess 模式下服务端运行在独立进程中，不会调用 set_client()，
        # 因此需要在这里主动注册。
        set_client(self)
        self._prepare_server_thread()
        self.server: Server | None = None
        self.server_process: subprocess.Popen | None = None
        # One persistent decoder avoids several Python workers contending with
        # pygame for the GIL.  zlib/msgpack/numpy still do their bulk work in C.
        self.chunk_load_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ChunkLoader")
        self.save_complete_event = threading.Event()
        self.in_game = False
        self.world_loading = False
        self.loading_screen: LoadingScreen | None = None
        self.disconnect_screen: DisconnectScreen | None = None
        self.death_screen: DeathScreen | None = None
        self.loaded_chunk_regions: set[int] = set()
        self.required_spawn_regions: set[int] = set()
        self.pending_teleport_id: int | None = None
        self.initial_sync_received = False
        self.initial_load_started = False
        self.game_started = False
        self.resources_manager = ResourcesManager(self)
        self.resources_manager.load_sounds_json('assets/minecraft/sounds.json')
        self.rate = 20
        self.client_ticks = 0
        # 聊天消息历史
        self.chat_messages: list[dict] = []  # [{'text': str, 'color': tuple, 'time': float}]
        self.max_chat_messages = 100
        self.chat_gui = None  # ChatGUI 在步骤 6 初始化
        self.client_player: ClientPlayer | None = None
        self.server_player_uuid: str | None = None
        self.game_manager = GameManager(self)
        self.particle_manager = ParticleManager(self)
        self.game_thread = threading.Thread(target=self.game_manager.start_game_loop, name="InGameThread")
        self.game_thread.daemon = True
        self.hold_mouse_buttons = [False, False, False]
        self.hold_key_map = {}
        self.key_map = {}
        self.current_save_id: str | None = None
        self.current_game_mode: str = "survival"
        self.saves_menu: SavesMenu | None = None
        self.main_menu = MainMenu(self.render)
        self.render.show_gui(self.main_menu)
        self.game_thread.start()
        self.render.request_text_input(False)

        # 简写方法
        # self.transkey = self.resources_manager.get_translation_key

    def _prepare_socket_transport(self):
        self.client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._send_lock = threading.Lock()
        self.socket_connected = threading.Event()
        self.socket_thread_running = True
        self.socket_thread = threading.Thread(target=self.start_socket, name="SocketThread")
        self.socket_thread.daemon = True

    def _prepare_server_thread(self):
        self.server_thread = threading.Thread(target=self.start_server, name="ServerThread")
        self.server_thread.daemon = True

    def start_socket(self):
        # 重试连接：子进程模式下服务端需要时间绑定端口并开始监听
        max_retries = 10
        retry_delay = 0.3
        last_error = None
        connected = False
        for attempt in range(max_retries):
            try:
                self.client_sock.connect(("127.0.0.1", 14525))
                connected = True
                break
            except ConnectionRefusedError as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logging.error("Could not connect to integrated server after retries")
            except OSError as e:
                last_error = e
                if not self.socket_thread_running or self.is_shutting_down:
                    return
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logging.error(f"Could not connect to integrated server: {e}")

        if not connected:
            if self.socket_thread_running and not self.is_shutting_down:
                self.show_disconnect(
                    "connect.failed", self._format_connection_error(last_error)
                )
            return

        logging.info("Connected to integrated server")
        self.socket_connected.set()
        while self.socket_thread_running:
            try:
                raw_len = recv_exact(self.client_sock, 4)  # 先读 4 字节长度头
                msg_len = struct.unpack('>I', raw_len)[0]  # 解析出长度（大端序）
                msg_body = recv_exact(self.client_sock, msg_len)  # 再读消息体

                # logging.debug(f"Received {msg_len} data from server")
                obj_dict = msgpack.unpackb(msg_body, raw=False)
                decode_packet(obj_dict, self)
            except (ConnectionError, OSError) as e:
                logging.info("Socket connection closed: %s", e)
                if (
                    self.socket_thread_running
                    and not self.is_shutting_down
                    and self.disconnect_screen is None
                ):
                    self.show_disconnect(
                        "disconnect.lost", self._format_connection_error(e)
                    )
                break
            except Exception as e:
                if not self.socket_thread_running:
                    # 正在关闭，忽略错误
                    break
                logging.error(f"Socket error: {e}")
                logging.error(traceback.format_exc())
                if self.disconnect_screen is None:
                    self.show_disconnect(
                        "disconnect.lost", self._format_connection_error(e)
                    )
                break

    @staticmethod
    def _format_connection_error(error: BaseException | None) -> str:
        if error is None:
            return "ConnectionError"
        message = str(error).strip()
        return f"{type(error).__name__}: {message}" if message else type(error).__name__

    def show_disconnect(self, title_key: str, reason: str | Text) -> None:
        """Stop gameplay and show exactly one connection failure screen."""
        if self.is_shutting_down or self.disconnect_screen is not None:
            return
        self.socket_connected.clear()
        self.in_game = False
        self.world_loading = False
        self.loading_screen = None
        self.hold_mouse_buttons = [False, False, False]
        for gui in self.render.drawing_GUIs[:]:
            self.render.close_gui(gui)
        self.death_screen = None
        self.disconnect_screen = DisconnectScreen(self.render, title_key, reason)
        self.render.show_gui(self.disconnect_screen)

    def sent_packet(self, obj, obj_type = None, *args) -> bool:
        """
        发送数据包到服务器

        参数：
        - obj: 要编码的对象
        - obj_type: 包类型
        - *args: 额外参数（如 location）
        """
        try:
            # 在子进程模式下，服务端需要时间启动并监听端口，
            # 此时套接字可能尚未连接，直接跳过发送，避免 WinError 10057
            if not self.socket_connected.is_set():
                return False

            # if obj_type == "BreakBlock":
            #     location: Location = obj.location
            #     print(get_light_levels_at(self.client_world.light_map, location.x, location.y))
            packet_dict = encode_packet(obj, obj_type, list(args))

            # 检查是否编码成功
            if not packet_dict:
                logging.warning(f"Failed to encode packet: obj={type(obj)}, type={obj_type}")
                return False

            packet_data = msgpack.packb(packet_dict, use_bin_type=True)
            length = len(packet_data)
            packet = struct.pack('>I', length) + packet_data

            # Movement, chunk acknowledgements and GUI actions originate on
            # different threads.  Serialize whole frames so TCP packets cannot
            # interleave at byte level.
            with self._send_lock:
                self.client_sock.sendall(packet)

            # logging.debug(f"Sent {obj_type} packet ({length} bytes)")
            return True
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError) as e:
            logging.warning(f"Connection lost while sending {obj_type}: {e}")
            return False
        except Exception as e:
            if not self.is_shutting_down:
                logging.error(f"Error sending {obj_type} packet: {e}")
                logging.error(traceback.format_exc())
            return False

    def start(self):
        self.render.start()

    def start_game(self, save_id: str | None = None):
        if self.game_started:
            return

        if save_id is None:
            save_id = save_manager.create_save(
                self.resources_manager.get_translation_key("selectWorld.newWorld"),
                version=self.version,
            )["id"]
        self.current_save_id = save_id
        self.disconnect_screen = None
        self.death_screen = None
        self.save_complete_event.clear()
        self.game_started = True
        self.in_game = False
        self.world_loading = True
        self.loaded_chunk_regions.clear()
        self.required_spawn_regions.clear()
        self.pending_teleport_id = None
        self.initial_sync_received = False
        self.initial_load_started = False
        if hasattr(self, "main_menu") and self.main_menu in self.render.drawing_GUIs:
            self.render.close_gui(self.main_menu)
        if self.saves_menu is not None and self.saves_menu in self.render.drawing_GUIs:
            self.render.close_gui(self.saves_menu)
        level = save_manager.load_level(save_id) or {}
        requested_mode = str(level.get("game_mode", "survival")).lower()
        self.current_game_mode = requested_mode if requested_mode in ("creative", "survival") else "survival"
        self.client_player = ClientPlayer(self, self.current_game_mode)
        self._install_game_controls()
        # ClientPlayer's game-mode constructor rebuilds the in-game GUI list,
        # so install the join screen after it has finished doing that.
        self.loading_screen = LoadingScreen(self.render)
        self.render.show_gui(self.loading_screen)

        if self.server_mode == "subprocess":
            self._start_server_subprocess()
        else:
            self._start_server_thread()
        self.socket_thread.start()

    def on_chunk_loaded(self, rx: int) -> None:
        """Called after the decoder atomically installed a chunk."""
        self.loaded_chunk_regions.add(int(rx))
        if self.client_player is not None:
            self.sent_packet({'__class__': 'ChunkReady', 'rx': int(rx)})
        self._try_finish_world_loading()

    def handle_initial_world_complete(self, regions) -> None:
        """Arm the final join gate after the server queued the initial batch."""
        try:
            loaded_targets = {int(rx) for rx in regions}
        except (TypeError, ValueError):
            loaded_targets = set()
        if not loaded_targets:
            return
        self.required_spawn_regions = loaded_targets
        self.initial_sync_received = True
        self._try_finish_world_loading()

    def handle_initial_world_start(self, regions) -> None:
        try:
            targets = {int(rx) for rx in regions}
        except (TypeError, ValueError):
            targets = set()
        if targets:
            self.required_spawn_regions = targets
            self.initial_load_started = True

    def handle_server_teleport(self, teleport_id: int | None) -> None:
        self.pending_teleport_id = int(teleport_id) if teleport_id is not None else None
        if self.client_player is None:
            return
        center = int(self.client_player.x // 16)
        if not self.initial_load_started or self.initial_sync_received:
            self.required_spawn_regions = {center - 1, center, center + 1}
        self.world_loading = True
        self._try_finish_world_loading()

    def _try_finish_world_loading(self) -> None:
        if not self.world_loading or self.client_player is None:
            return
        if not self.initial_sync_received:
            return
        if not self.required_spawn_regions.issubset(self.loaded_chunk_regions):
            return
        if self.pending_teleport_id is not None:
            self.sent_packet({'__class__': 'TeleportConfirm', 'teleport_id': self.pending_teleport_id})
            self.pending_teleport_id = None
        # The first visible frame should already be at the authoritative
        # position/time; do not expose camera or sky interpolation behind the
        # loading screen.
        player = self.client_player
        visual_mid_y = player.y + player.skeleton.size * player.skeleton.AUTHORED_HEIGHT_BLOCKS / 2
        self.render.camera.snap_to(
            player.x + player.width / 2 - 0.5,
            visual_mid_y + 0.5,
        )
        self.render.day_time = float(self.client_world.world_time)
        self.render.total_day_ticks = float(self.client_world.world_time)
        self.render._last_daytime_update = pygame.time.get_ticks()
        self.world_loading = False
        self.initial_load_started = False
        self.in_game = True
        if self.loading_screen is not None:
            self.render.close_gui(self.loading_screen)
            self.loading_screen = None

    def can_simulate_player(self, player: ClientPlayer) -> bool:
        """Collision queries must never treat an unreceived chunk as air."""
        if self.world_loading:
            return False
        x_values = (player.x, player.x + player.width - 1e-6,
                    player.x + player.motion.x,
                    player.x + player.motion.x + player.width - 1e-6)
        return all(int(x // 16) in self.loaded_chunk_regions for x in x_values)

    def open_pause_menu(self):
        if not self.in_game or self.death_screen is not None:
            return
        for gui in self.render.drawing_GUIs:
            if isinstance(gui, PauseMenu):
                return
        self.capture_save_icon()
        self.render.show_gui(PauseMenu(self.render))

    def show_death_screen(
        self, death_message: dict | None = None, *, score: int | None = None
    ) -> None:
        if self.client_player is None:
            return
        self.client_player.dead = True
        if self.death_screen is not None:
            self.death_screen.update_death_message(death_message)
            if score is not None:
                self.death_screen.score = max(0, int(score))
            return
        for gui in self.render.drawing_GUIs[:]:
            self.render.close_gui(gui)
        if score is None:
            score = int(getattr(self.client_player, "score", 0))
        self.death_screen = DeathScreen(self.render, death_message, score=score)
        self.render.show_gui(self.death_screen)

    def close_death_screen(self) -> None:
        if self.death_screen is None:
            return
        self.render.close_gui(self.death_screen)
        self.death_screen = None
        if self.client_player is not None:
            self.client_player.game_mode.update_gui()

    def capture_save_icon(self):
        if not self.current_save_id or self.render.screen is None:
            return
        try:
            screen = self.render.screen.copy()
            width, height = screen.get_size()
            side = min(width, height)
            crop = pygame.Rect((width - side) // 2, (height - side) // 2, side, side)
            icon = screen.subsurface(crop).copy()
            icon = pygame.transform.smoothscale(icon, (64, 64))
            path = save_manager.icon_path(self.current_save_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(icon, str(path))
        except Exception as e:
            logging.warning(f"Failed to save world icon: {e}")

    def return_to_main_menu(self):
        if not self.game_started:
            return
        self.in_game = False
        self._request_server_save(timeout=8.0)
        self._close_current_game_transport()
        self.chunk_load_pool.shutdown(wait=True)
        self.chunk_load_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ChunkLoader")
        self.client_world = client_world.ClientWorld(self)
        self.render.client_world = self.client_world
        self.client_player = None
        self.world_loading = False
        self.loading_screen = None
        self.disconnect_screen = None
        self.death_screen = None
        self.loaded_chunk_regions.clear()
        self.required_spawn_regions.clear()
        self.pending_teleport_id = None
        self.initial_sync_received = False
        self.initial_load_started = False
        self.server_player_uuid = None
        self.chat_gui = None
        self.chat_messages.clear()
        self.particle_manager = ParticleManager(self)
        self.hold_mouse_buttons = [False, False, False]
        self.hold_key_map = {}
        self.key_map = {}
        self.game_manager.reset_game_input()
        self.game_manager.last_pressed_time.clear()
        self.current_save_id = None
        self.current_game_mode = "survival"
        self.server = None
        self.server_process = None
        self.game_started = False
        self.render.drawing_GUIs.clear()
        self.main_menu = MainMenu(self.render)
        self.render.show_gui(self.main_menu)
        self.render.request_text_input(False)
        self._prepare_socket_transport()
        self._prepare_server_thread()

    def _install_game_controls(self):
        if self.client_player is not None:
            self.hold_mouse_buttons = [False, False, False]
            self.hold_key_map = {
                "mouse_left": self.client_player.game_mode.left_click_on_block,
                "mouse_right": self.client_player.game_mode.right_click_on_block,
                pygame.K_d: self.client_player.move_right,
                pygame.K_a: self.client_player.move_left,
                pygame.K_w: self.client_player.jump,
                pygame.K_SPACE: self.client_player.jump,
                pygame.K_LSHIFT: self.client_player.handle_shift,
                pygame.K_s: self.client_player.handle_shift,
            }
            self.key_map = {
                pygame.K_F3: self.render.debug_mode,
                pygame.K_e: self.client_player.game_mode.open_inventory,
                pygame.K_LCTRL: self.client_player.switch_sprint,
            }
            if self.fore_place_switch_mode == "switch":
                self.key_map[pygame.K_q] = lambda: setattr(
                    self.client_player, 'fore_place', not self.client_player.fore_place
                )

    @staticmethod
    def _get_resource_path(relative_path):
        """
        获取资源文件的绝对路径，兼容开发环境和 Nuitka 打包环境。
        """
        # Nuitka 打包后会将资源解压到 sys._MEIPASS（如果有）
        if getattr(sys, '_MEIPASS', False):
            base_path = sys._MEIPASS
        else:
            # 开发环境下，根据当前文件位置推算（这里根据你的目录结构）
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_path, relative_path)

    def _start_server_subprocess(self):
        """以子进程方式启动服务端，绕过 GIL，客户端不受服务端运算影响。"""
        logging.info("Server is running on subprocess mode.")
        try:
            # 1. 获取正确的脚本路径（兼容打包）
            server_script = self._get_resource_path("start_server.py")

            # 2. 构建启动参数
            # 开发环境：sys.executable 是 Python 解释器，可直接运行脚本
            # 打包后：sys.executable 是主程序 .exe，无法直接运行 .py 文件。
            # 因此，你需要额外处理（见下方注意事项）。
            args = [sys.executable, server_script, "--integrated"]
            if self.current_save_id:
                args.extend(["--save-id", self.current_save_id])

            # 3. 启动子进程（建议传递干净的环境副本，避免 Nuitka 注入变量干扰）
            clean_env = os.environ.copy()
            # 移除可能引起冲突的环境变量（可选）
            keys_to_remove = ['PYTHONPATH', 'PYTHONHOME', 'NUITKA_ONEFILE_PARENT',
                              'NUITKA_RESUME_FILENAME', 'TCL_LIBRARY', 'TK_LIBRARY']
            for key in keys_to_remove:
                clean_env.pop(key, None)

            self.server_process = subprocess.Popen(
                args,
                env=clean_env,
            )
            logging.info(f"Server subprocess started (PID: {self.server_process.pid})")
        except FileNotFoundError:
            logging.error(f"Server script not found: {server_script}")
        except Exception as e:
            logging.error(f"Failed to start server subprocess: {e}")
            logging.info("Trying to connect to an existing server...")

    def _start_server_thread(self):
        """以线程方式启动服务端（同一进程，受 GIL 影响）。"""
        logging.warning("Server is running on threading mode, if you are not debugging your client/server, please use subprocess mode instead to have a better performance.")
        try:
            self.server = Server(True, self, self.current_save_id)
            self.server_thread.start()
        except OSError:  # 端口已被占用，尝试加入已有服务端
            logging.info("Port already in use, trying to join existing server")

    def start_server(self):
        self.server.init()

    def add_chat_message(self, text, color=(255, 255, 255)):
        """添加聊天消息到历史记录"""
        self.chat_messages.append({
            'text': text,
            'color': color,
            'time': time.time()
        })
        if len(self.chat_messages) > self.max_chat_messages:
            self.chat_messages = self.chat_messages[-self.max_chat_messages:]

    def _close_current_game_transport(self):
        self.socket_thread_running = False
        try:
            self.client_sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.client_sock.close()
        except Exception:
            pass
        if self.socket_thread.is_alive():
            self.socket_thread.join(timeout=2.0)
            if self.socket_thread.is_alive():
                logging.warning("Socket thread did not exit cleanly")
        self.socket_connected.clear()

        if self.server_mode == "subprocess":
            self._shutdown_server_subprocess()
        else:
            self._shutdown_server_thread()

    def shutdown(self):
        """优雅地关闭客户端。

        保存、关闭 socket 和线程池都可能阻塞一段时间，
        因此统一交给独立清理线程执行。pygame 的关闭由渲染
        主线程在离开渲染循环时完成。
        """
        with self._shutdown_lock:
            if self._shutdown_started:
                return
            self._shutdown_started = True
            # 先设置标志，让渲染和游戏循环尽快停止接收新事件。
            self.is_shutting_down = True
            self.game_manager.running = False

        # 无论调用来自 GUI 游戏线程还是渲染主线程，都不在原线程阻塞。
        threading.Thread(
            target=self._finish_shutdown,
            name="ShutdownThread",
            daemon=False,
        ).start()

    def _finish_shutdown(self):
        """执行可能阻塞的关闭清理；由 shutdown() 选择合适的线程调用。"""
        self._request_server_save()
        self._close_current_game_transport()

        # 清理始终在独立线程中，可以安全等待游戏线程。
        if self.game_thread.is_alive():
            self.game_thread.join(timeout=2.0)

        # 关闭区块加载线程池
        self.chunk_load_pool.shutdown(wait=True)

        # 清理音频设备
        if hasattr(self, 'audio_device'):
            try:
                self.audio_device.stop()
            except Exception:
                pass

        logging.info("Client Closed.")

    def _shutdown_server_subprocess(self):
        """终止服务端子进程。"""
        if not self.server_process:
            return
        try:
            self.server_process.terminate()
            self.server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logging.warning("Server subprocess did not terminate in time, force killing")
            self.server_process.kill()
            self.server_process.wait()
        except Exception:
            pass
        self.server_process = None

    def _shutdown_server_thread(self):
        """关闭线程模式下的服务端。"""
        if self.server:
            try:
                self.server.close_server()
            except Exception:
                pass
        if self.server_thread.is_alive():
            self.server_thread.join(timeout=2.0)
            if self.server_thread.is_alive():
                logging.warning("Server thread did not exit cleanly")
        self.server = None

    def play_sound(self, sound_id: str):
        self.resources_manager.get_resource(sound_id).play()

    def _request_server_save(self, timeout: float = 5.0):
        if not self.socket_connected.is_set():
            return
        try:
            self.save_complete_event.clear()
            self.sent_packet({'__class__': 'ClientShutdown'})
            self.save_complete_event.wait(timeout=timeout)
        except Exception:
            pass


