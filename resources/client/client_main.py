import logging
import socket
import struct
import threading
import msgpack
import pygame

from resources.client import render, client_world
from resources.client.client_packets import decode_packet
from resources.client.client_socket import recv_exact
from resources.client.game_manager import start_inner_game
from resources.client.main_player import ClientPlayer
from resources.server.server_main import Server


class Client:
    def __init__(self):
        self.version = "0.0.1 SNAPSHOT"
        self.client_world = client_world.ClientWorld()
        self.render = render.Render(self.client_world)
        self.client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_thread = threading.Thread(target=self.start_socket)
        self.socket_thread.daemon = True
        self.server_thread = threading.Thread(target=self.start_server)
        self.server_thread.daemon = True
        self.server = None
        self.start_game()
        self.rate = 20
        self.client_player = ClientPlayer(self)
        self.game_thread = threading.Thread(target=start_inner_game, args=(self,))
        self.game_thread.daemon = True
        self.key_map = {
            pygame.K_d: self.client_player.move_right,
            pygame.K_a: self.client_player.move_left,
        }
        self.game_thread.start()

    def start_socket(self):
        try:
            self.client_sock.connect(("127.0.0.1", 14525))
        except ConnectionRefusedError:
            logging.error("Could not connect to integrated server")
            return

        logging.info("Connected to integrated server")
        while True:
            raw_len = recv_exact(self.client_sock, 4)  # 先读 4 字节长度头
            msg_len = struct.unpack('>I', raw_len)[0]  # 解析出长度（大端序）
            msg_body = recv_exact(self.client_sock, msg_len)  # 再读消息体

            logging.debug(f"Received {msg_len} data from server")
            obj_dict = msgpack.unpackb(msg_body, raw=False)
            decode_packet(obj_dict, self)
            # print(obj_dict)


    def start(self):
        self.render.start()

    def start_game(self):
        self.server = Server(True)

        # while not self.server.initialized:
        #     time.sleep(0.01)
        self.server_thread.start()
        self.socket_thread.start()

    def start_server(self):
        self.server.init()


