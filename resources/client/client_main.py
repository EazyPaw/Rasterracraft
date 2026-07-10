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
from resources.client.particles import ParticleManager
from resources.client.resources_manager import ResourcesManager
from resources.server import save_manager
from resources.server.server_main import Server
from resources.server.utils import recv_exact, set_client

class Client:
    def __init__(self):
        # 初始化剪贴板（Ctrl+V 粘贴用）
        try:
            pygame.scrap.init()
        except Exception:
            pass
        self.is_shutting_down = False
        self.version = "0.0.1 SNAPSHOT"
        self.language = "en_US"
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
        self.chunk_load_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ChunkLoader")
        self.save_complete_event = threading.Event()
        self.in_game = False
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
        self.saves_menu: SavesMenu | None = None
        self.main_menu = MainMenu(self.render)
        self.render.show_gui(self.main_menu)
        self.game_thread.start()
        pygame.key.stop_text_input()

        # 简写方法
        # self.transkey = self.resources_manager.get_translation_key

    def _prepare_socket_transport(self):
        self.client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
        for attempt in range(max_retries):
            try:
                self.client_sock.connect(("127.0.0.1", 14525))
                break
            except ConnectionRefusedError:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logging.error("Could not connect to integrated server after retries")
                    return
            except OSError as e:
                if not self.socket_thread_running or self.is_shutting_down:
                    return
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logging.error(f"Could not connect to integrated server: {e}")
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
            except (ConnectionAbortedError, ConnectionResetError, OSError):
                # socket 被关闭或连接中断，正常退出
                logging.info(f"Socket connection closed.")
                break
            except Exception as e:
                if not self.socket_thread_running:
                    # 正在关闭，忽略错误
                    break
                logging.error(f"Socket error: {e}")
                logging.error(traceback.format_exc())
                break

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

            packet_data = msgpack.packb(packet_dict)
            length = len(packet_data)
            packet = struct.pack('>I', length) + packet_data

            # 确保发送所有数据（TCP send 可能只发送部分数据）
            total_sent = 0
            while total_sent < len(packet):
                sent = self.client_sock.send(packet[total_sent:])
                if sent == 0:
                    raise ConnectionError("Socket connection broken")
                total_sent += sent

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
        self.save_complete_event.clear()
        self.game_started = True
        if hasattr(self, "main_menu") and self.main_menu in self.render.drawing_GUIs:
            self.render.close_gui(self.main_menu)
        if self.saves_menu is not None and self.saves_menu in self.render.drawing_GUIs:
            self.render.close_gui(self.saves_menu)

        self.client_player = ClientPlayer(self)
        self._install_game_controls()

        if self.server_mode == "subprocess":
            self._start_server_subprocess()
        else:
            self._start_server_thread()
        self.socket_thread.start()
        self.in_game = True

    def open_pause_menu(self):
        if not self.in_game:
            return
        for gui in self.render.drawing_GUIs:
            if isinstance(gui, PauseMenu):
                return
        self.capture_save_icon()
        self.render.show_gui(PauseMenu(self.render))

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
        self.chunk_load_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ChunkLoader")
        self.client_world = client_world.ClientWorld(self)
        self.render.client_world = self.client_world
        self.client_player = None
        self.server_player_uuid = None
        self.chat_gui = None
        self.chat_messages.clear()
        self.particle_manager = ParticleManager(self)
        self.hold_mouse_buttons = [False, False, False]
        self.hold_key_map = {}
        self.key_map = {}
        self.game_manager.ing_mouse_lock = 0
        self.game_manager.last_pressed_time.clear()
        self.current_save_id = None
        self.server = None
        self.server_process = None
        self.game_started = False
        self.render.drawing_GUIs.clear()
        self.main_menu = MainMenu(self.render)
        self.render.show_gui(self.main_menu)
        pygame.key.stop_text_input()
        pygame.key.set_repeat(0, 0)
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

    def _start_server_subprocess(self):
        """以子进程方式启动服务端，绕过 GIL，客户端不受服务端运算影响。"""
        logging.info("Server is running on subprocess mode.")
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            server_script = os.path.join(project_root, "start_server.py")
            args = [sys.executable, server_script, "--integrated"]
            if self.current_save_id:
                args.extend(["--save-id", self.current_save_id])
            self.server_process = subprocess.Popen(
                args,
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

    def add_chat_message(self, text: str, color=(255, 255, 255)):
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
        """优雅地关闭客户端"""
        # 1. 先设置标志，让循环知道要退出
        self.is_shutting_down = True
        self._request_server_save()
        self._close_current_game_transport()

        # 4. 停止游戏循环
        self.game_manager.running = False

        # 5. 等待游戏线程
        if self.game_thread.is_alive():
            self.game_thread.join(timeout=2.0)

        # 6. 关闭区块加载线程池
        self.chunk_load_pool.shutdown(wait=True)

        # 8. 清理音频设备
        if hasattr(self, 'audio_device'):
            try:
                self.audio_device.stop()
            except Exception:
                pass

        # 9. 退出 pygame
        pygame.quit()

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


