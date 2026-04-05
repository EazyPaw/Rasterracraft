import logging
import socket
import struct
import time
import threading
import traceback
from typing import Any

import msgpack

from resources.server.commands import CommandExecutor
from resources.server.generator import get_block_origin
from resources.server.packets import encode_packet
from resources.server.player import Player
from resources.server.world_class import World, WorldAttribute


class Server:
    def __init__(self, integrated = False):
        self.worlds: dict[str, World] = {}
        self.socket_server = self.SocketServer(self)
        self.TPS = 0
        self.rate = 20
        self.view_distance = 4
        self.players: list[Player] = []
        self.max_players = 20
        self.integrated = integrated
        self.initialized = False
        self.input_thread = threading.Thread(target=self.check_input)
        self.input_thread.daemon = True
        self.input_thread.start()
        self.command_executor = CommandExecutor(self)

    def check_input(self):
        if self.integrated:
            logging.info("Integrated server, input is disabled")
            return
        while True:
            inp = input(">_ ")
            if inp == "":
                continue
            cmd = inp.split(" ")
            result = self.command_executor.execute_command(cmd)
            logging.info(result)


    class SocketServer:
        def __init__(self, server):
            self.server = server
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.bind(("0.0.0.0", 14525))
            self.server_sock.listen(5)
            self.connections: dict[Player, tuple[socket.socket, Any]] = {}
            self.thread = threading.Thread(target=self.run)
            self.thread.daemon = True
            self.thread.start()

        def run(self):
            logging.info("Socket server started.")
            while True:

                client_sock, client_addr = self.server_sock.accept()

                player = Player(0, 100 ,self.server.worlds["overworld"])
                self.connections[player] = (client_sock, client_addr)
                self.server.players.append(player)

                logging.info(f"Client {client_addr} connected")
                client_thread = threading.Thread(target=self.handle_client, args=(client_sock, client_addr))
                client_thread.daemon = True
                client_thread.start()

        def handle_client(self, client_sock, client_addr):
            while True:
                try:
                    data = client_sock.recv(1048576)
                    if not data:  # 客户端正常关闭（发送了空数据）
                        logging.info(f"Client {client_addr} disconnected")
                        break

                    obj_dict = msgpack.unpackb(data, raw=False, object_hook=encode_packet)

                except ConnectionResetError:
                    logging.info(f"Client {client_addr} disconnected accidentally")
                    break
                except Exception as e:
                    logging.error(f"Client {client_addr} error: {e}, disconnected")
                    break


    def run(self):

        self.initialized = True

        logging.info(f"Server initialized")

        next_time = time.perf_counter()
        over_ticks = 0

        while True:
            interval = 1.0 / self.rate

            self.tick()

            next_time += interval
            sleep_time = next_time - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                over_ticks += 1
                if over_ticks > 50:
                    sleep_time = -sleep_time
                    logging.warning(f"Overloaded! Server is {sleep_time}ms behind!")
                    over_ticks = 0

    def init(self):
        logging.info("Initializing server")
        self.worlds["overworld"] = World("overworld"
                                         , get_block_origin
                                         , WorldAttribute()
                                         , 0)
        self.run()

    def tick(self):
        self.load_chunks()

    def send_client_socket(self, player: Player, obj) -> bool:
        try:
            packet_data = msgpack.packb(encode_packet(obj))
            length = len(packet_data)
            self.socket_server.connections[player][0].send(
                struct.pack('>I', length) + packet_data
            )
            logging.debug(f"Sent {length} data to client {self.socket_server.connections[player][1]}")
            return True
        except Exception as e:
            logging.error(f"Error sending data to client {self.socket_server.connections[player][1]}: {e}")
            logging.error(traceback.format_exc())
            return False

    def load_chunks(self):
        for player in self.players:
            rx = player.x // 16
            for x in range(rx - self.view_distance, rx + self.view_distance + 1):
                if x not in player.world.regions:
                    player.world.generate_chunk(x)
                    self.send_client_socket(player, player.world.regions[x])
