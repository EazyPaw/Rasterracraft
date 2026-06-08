import logging
import socket
import struct
import threading
import time
import traceback
from typing import Any

import msgpack
import numpy as np

import resources.server.generator as generator
from resources.server.commands import CommandExecutor
from resources.server.player import Player
from resources.server.server_packets import encode_packet, decode_packet
from resources.server.utils import recv_exact
from resources.server.world_class import World, WorldAttribute


class Server:
    def __init__(self, integrated = False, client = None):
        self.running = True
        self.main_world_id = "overworld"
        self.worlds: dict[str, World] = {}
        self.socket_server = self.SocketServer(self)
        self.TPS = 0
        self.rate = 20
        self.view_distance = 4
        self.players: list[Player] = []
        self.max_players = 20
        self.integrated = integrated
        self.initialized = False
        self.input_thread = threading.Thread(target=self.check_input, name="Command thread")
        self.input_thread.daemon = True
        self.commands_error_traceback = True
        self.input_thread.start()
        self.command_executor = CommandExecutor(self)
        self.client = client

    def check_input(self):
        if self.integrated:
            logging.info("Integrated server, input is disabled")
            return
        while True:
            inp = input(">_ ")
            if inp == "":
                continue
            if inp[0] == "/":
                inp = inp[1:]
            cmd = inp.split(" ")
            result = self.command_executor.execute_command("server_cmd", cmd)
            result = result.replace("§c", "\x1b[31;21m")
            logging.info(result)


    class SocketServer:
        def __init__(self, server):
            self.server = server
            self.running = True
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.bind(("0.0.0.0", 14525))
            self.server_sock.listen(5)
            self.connections: dict[Player, tuple[socket.socket, Any]] = {}
            self.thread = threading.Thread(target=self.run, name="SocketServerThread")
            self.thread.daemon = True
            self.thread.start()

        def run(self):
            logging.info("Socket server started.")
            while self.running:

                client_sock, client_addr = self.server_sock.accept()

                player = Player(0, 100 ,self.server.worlds["overworld"])
                self.connections[player] = (client_sock, client_addr)
                self.server.players.append(player)
                logging.info(f"Client {client_addr} connected")
                client_thread = threading.Thread(target=self.handle_client, args=(client_sock, client_addr, player), name="SocketClientThread")
                client_thread.daemon = True
                client_thread.start()

        def handle_client(self, client_sock, client_addr, player: Player):
            while True:
                try:
                    # 严格按照协议读取：先读4字节长度头
                    raw_len = recv_exact(client_sock, 4)
                    if not raw_len or len(raw_len) < 4:
                        # 客户端关闭或连接中断
                        logging.info(f"Client {client_addr} disconnected")
                        self.server.on_player_disconnect(player)
                        break
                    
                    msg_len = struct.unpack('>I', raw_len)[0]
                    
                    # 验证长度合理性（防止恶意数据或损坏）
                    if msg_len <= 0 or msg_len > 1048576:  # 最大1MB
                        logging.error(f"Invalid message length: {msg_len} from {client_addr}")
                        self.server.on_player_disconnect(player)
                        break
                    
                    # 读取消息体
                    msg_body = recv_exact(client_sock, msg_len)
                    if not msg_body or len(msg_body) < msg_len:
                        logging.error(f"Incomplete message from {client_addr}")
                        self.server.on_player_disconnect(player)
                        break

                    # 解包并处理
                    obj_dict = msgpack.unpackb(msg_body, raw=False)
                    decode_packet(obj_dict, player)

                except ConnectionResetError:
                    logging.info(f"Client {client_addr} disconnected (reset)")
                    self.server.on_player_disconnect(player)
                    break
                except ConnectionAbortedError:
                    logging.info(f"Client {client_addr} connection aborted")
                    self.server.on_player_disconnect(player)
                    break
                except ConnectionError:
                    logging.info(f"Client {client_addr} disconnected (aborted)")
                    self.server.on_player_disconnect(player)
                    break
                except Exception as e:
                    logging.error(f"Client {client_addr} error: {e}")
                    logging.error(traceback.format_exc())
                    self.server.on_player_disconnect(player)
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
        self.worlds["overworld"] = World(self
                                         ,"overworld"
                                         , generator.bedrock_flat_generator
                                         , WorldAttribute()
                                         , 0)
        self.run()

    def tick(self):
        self.load_chunks()

    def send_client_socket(self, player: Player, obj, obj_type = None, args = None) -> bool:
        """
        发送数据包至客户端
        :param player: 发送的玩家
        :param obj: 发送的对象
        :param obj_type: 发送数据包的类型（可不填写）
        :param args: 参数（可不填写）
        :return:
        """

        try:
            encoded_obj = encode_packet(obj, obj_type, args)
            
            # 辅助函数：将嵌套结构中的 numpy 类型转换为 python 原生类型
            def convert_numpy_types(o):
                if isinstance(o, np.integer):
                    return int(o)
                elif isinstance(o, np.floating):
                    return float(o)
                elif isinstance(o, np.ndarray):
                    return o.tolist()
                elif isinstance(o, dict):
                    return {k: convert_numpy_types(v) for k, v in o.items()}
                elif isinstance(o, (list, tuple)):
                    return [convert_numpy_types(i) for i in o]
                return o

            clean_obj = convert_numpy_types(encoded_obj)
            packet_data = msgpack.packb(clean_obj)
            
            length = len(packet_data)
            self.socket_server.connections[player][0].send(
                struct.pack('>I', length) + packet_data
            )
            # logging.debug(f"Sent {length} data to client {self.socket_server.connections[player][1]}")
            return True
        except KeyError:
            # 玩家已断开连接，不在 connections 中
            return False
        except Exception as e:
            # 安全地获取客户端地址
            try:
                client_addr = self.socket_server.connections[player][1]
            except KeyError:
                client_addr = "unknown (disconnected)"
            logging.error(f"Error sending data to client {client_addr}: {e}")
            logging.error(traceback.format_exc())
            return False

    def load_chunks(self):
        for player in self.players:
            rx = int(player.x // 16)
            for x in range(rx - self.view_distance, rx + self.view_distance + 1):
                if x not in player.loading_regions:
                    if x not in player.world.regions:
                        player.world.generate_chunk(x)
                    self.send_client_socket(player, player.world.regions[x])
                    player.loading_regions.append(x)

    def close_server(self):
        self.running = False
        self.socket_server.running = False

    def on_player_disconnect(self, player: Player):
        self.players.remove(player)
        self.socket_server.connections.pop(player)
