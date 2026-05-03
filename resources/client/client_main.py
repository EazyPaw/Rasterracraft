import logging
import socket
import struct
import threading
import traceback

import miniaudio
import msgpack
import pygame

from resources.client import render, client_world
from resources.client.client_packets import decode_packet, encode_packet
from resources.client.resources_loader import ResourcesManager
from resources.server.socket_utils import recv_exact
from resources.client.game_manager import GameManager
from resources.client.main_player import ClientPlayer
from resources.server.server_main import Server


class Client:
    def __init__(self):
        self.is_shutting_down = False
        self.version = "0.0.1 SNAPSHOT"
        self.client_world = client_world.ClientWorld(self)
        self.render = render.Render(self)
        self.client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_thread_running = True
        self.socket_thread = threading.Thread(target=self.start_socket)
        self.socket_thread.daemon = True
        self.server_thread = threading.Thread(target=self.start_server)
        self.server_thread.daemon = True
        self.server = None
        self.in_game = True
        self.resources_manager = ResourcesManager()
        self.resources_manager.load_sounds_json('assets/minecraft/sounds.json')
        self.start_game()
        self.rate = 20
        self.client_player = ClientPlayer(self)
        self.game_manager = GameManager(self)
        self.game_thread = threading.Thread(target=self.game_manager.start_game_loop)
        self.game_thread.daemon = True
        self.audio_device = miniaudio.PlaybackDevice()
        self.hold_mouse_buttons = [False, False, False]
        self.key_map = {
            "mouse_left": self.client_player.game_mode.left_click_on_block,
            "mouse_right": self.client_player.game_mode.right_click_on_block,
            pygame.K_d: self.client_player.move_right,
            pygame.K_a: self.client_player.move_left,
            pygame.K_w: self.client_player.jump,
            pygame.K_SPACE: self.client_player.jump
        }
        self.game_thread.start()

    def start_socket(self):
        try:
            self.client_sock.connect(("127.0.0.1", 14525))
        except ConnectionRefusedError:
            logging.error("Could not connect to integrated server")
            return

        logging.info("Connected to integrated server")
        while self.socket_thread_running:
            try:
                raw_len = recv_exact(self.client_sock, 4)  # 先读 4 字节长度头
                msg_len = struct.unpack('>I', raw_len)[0]  # 解析出长度（大端序）
                msg_body = recv_exact(self.client_sock, msg_len)  # 再读消息体

                # logging.debug(f"Received {msg_len} data from server")
                obj_dict = msgpack.unpackb(msg_body, raw=False)
                decode_packet(obj_dict, self)
            except (ConnectionAbortedError, ConnectionResetError, OSError) as e:
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

    def sent_packet(self, obj, obj_type = None, *args):
        """
        发送数据包到服务器
        
        参数：
        - obj: 要编码的对象
        - obj_type: 包类型
        - *args: 额外参数（如 location）
        """
        try:
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

    def start_game(self):
        self.server = Server(False)
        self.server_thread.start()
        self.socket_thread.start()

    def start_server(self):
        self.server.init()

    def shutdown(self):
        """优雅地关闭客户端"""
        # 1. 先设置标志，让循环知道要退出
        self.socket_thread_running = False

        self.is_shutting_down = True
        
        # 2. 关闭 socket（这会中断阻塞的 recv() 调用）
        try:
            self.client_sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.client_sock.close()
        except Exception:
            pass
        
        # 3. 等待 socket 线程结束（现在它会快速退出）
        if self.socket_thread.is_alive():
            self.socket_thread.join(timeout=2.0)
            if self.socket_thread.is_alive():
                logging.warning("Socket thread did not exit cleanly")
        
        # 4. 停止游戏循环
        self.game_manager.running = False
        
        # 5. 等待游戏线程
        if self.game_thread.is_alive():
            self.game_thread.join(timeout=2.0)
        
        # 6. 关闭服务器
        if self.server:
            try:
                self.server.close_server()
            except Exception:
                pass
        
        # 7. 清理音频设备
        if hasattr(self, 'audio_device'):
            try:
                self.audio_device.stop()
            except Exception:
                pass
        
        # 8. 退出 pygame
        pygame.quit()

    def play_sound(self, sound_id: str):
        self.resources_manager.get_resource(sound_id).play()


