import logging
import random
import socket
import struct
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import msgpack
import numpy as np

import resources.server.generator as generator
from resources.server.commands import CommandExecutor
from resources.server.player import Player
from resources.server.text import Text
from resources.server.server_packets import encode_packet, decode_packet
from resources.server.utils import recv_exact, set_client
from resources.server.world_class import World, WorldAttribute, Chunk


class Server:
    def __init__(self, integrated = False, client = None):
        self.running = True
        self.main_world_id = "overworld"
        self.worlds: dict[str, World] = {}
        self.ready = threading.Event()  # 用于等待初始化完成
        self.socket_server = self.SocketServer(self)
        self.TPS = 0
        self.rate = 20
        self.server_ticks = 0
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
        # 区块生成线程池：generate_chunk 是 CPU 密集型操作（噪声计算），
        # noise 库（C 扩展）和 numpy 在计算时会释放 GIL，因此多线程有实际收益。
        self.chunk_gen_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ChunkGen")
        if client is not None:
            set_client(client)

    def check_input(self):
        if self.integrated:
            logging.info("Integrated server, input is disabled.")
            return
        while True:
            inp = input()
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
            logging.info("Socket server started, waiting for server initialization...")
            # 等待服务器初始化完成（worlds 已创建）
            self.server.ready.wait()
            logging.info("Server ready, accepting connections.")
            while self.running:

                client_sock, client_addr = self.server_sock.accept()

                player = Player(0, 100, self.server.worlds["overworld"])
                self.connections[player] = (client_sock, client_addr)
                self.server.players.append(player)
                logging.info(f"Client {client_addr} connected")
                self.server.broadcast_chat(f"{player.name} joined the game", (255, 255, 85))
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
                                         , generator.MinecraftLike2D
                                         , WorldAttribute()
                                         , random.randint(-23767, 23767))
        self.initialized = True
        self.ready.set()  # 通知 socket 线程服务器已就绪
        self.run()

    def tick(self):
        self.server_ticks += 1
        for world in self.worlds.values():
            world.world_time = (world.world_time + 1) % 24000
        if self.server_ticks % 5 == 0:
            for player in self.players:
                self.send_client_socket(
                    player,
                    {'__class__': 'TimeUpdate', 'time': int(player.world.world_time)},
                    "Forward"
                )
        self.load_chunks()

    def _resolve_chat_msg(self, msg, color=None):
        """解析聊天消息参数，统一处理 str 和 Text 对象。

        Returns (text: str, color: tuple).
        """
        if isinstance(msg, Text):
            text = msg.to_plain_string()
            if color is None and msg.text:
                color = msg.text[0]['color'].value
        else:
            text = str(msg)
        if color is None:
            color = (255, 255, 255)
        if isinstance(color, list):
            color = tuple(color)
        return text, color

    def send_chat_to_player(self, player: Player, msg, color=None):
        """向单个玩家发送聊天消息。

        Parameters
        ----------
        player : Player
            目标玩家。
        msg : str | Text
            消息文本或 Text 对象。Text 对象会提取第一段的颜色。
        color : tuple | None
            RGB 颜色元组。若为 None 且 msg 为 Text，使用 Text 的颜色。
        """
        text, color = self._resolve_chat_msg(msg, color)
        packet = {'__class__': 'ChatMessage', 'text': text, 'color': list(color)}
        self.send_client_socket(player, packet, "Forward")

    def broadcast_chat(self, msg, color=None, exclude=None):
        """向所有玩家广播聊天消息。

        Parameters
        ----------
        msg : str | Text
            消息文本或 Text 对象。
        color : tuple | None
            RGB 颜色元组。若为 None 且 msg 为 Text，使用 Text 的颜色。
        exclude : Player | None
            要排除的玩家。
        """
        text, color = self._resolve_chat_msg(msg, color)
        packet = {'__class__': 'ChatMessage', 'text': text, 'color': list(color)}
        for p in self.players:
            if p != exclude:
                self.send_client_socket(p, packet, "Forward")

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
                elif isinstance(o, np.bool_):
                    return bool(o)
                elif isinstance(o, (np.str_, np.bytes_)):
                    return str(o)
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
        # 阶段一：收集需要生成的区块，提交到线程池并行生成（噪声计算是主要瓶颈）
        gen_futures: dict[tuple[int, World], Any] = {}
        new_chunks: list[tuple[Player, int]] = []  # (player, rx) 待发送的新区块

        for player in self.players:
            rx = int(player.x // 16)
            for x in range(rx - self.view_distance, rx + self.view_distance + 1):
                if x not in player.loading_regions:
                    if x not in player.world.regions:
                        # 避免对同一区块重复提交生成任务（多个玩家共享同一 World）
                        key = (x, player.world)
                        if key not in gen_futures:
                            gen_futures[key] = self.chunk_gen_pool.submit(
                                player.world.generate_chunk, x
                            )
                    new_chunks.append((player, x))

        # 阶段二：等待所有生成任务完成
        for (rx, world), future in gen_futures.items():
            try:
                future.result(timeout=30)
            except Exception as e:
                logging.error(f"Chunk generation failed for region {rx}: {e}")

        # 阶段三：发送新区块给客户端，并标记为已加载
        for player, x in new_chunks:
            if x in player.world.regions:
                self.send_client_socket(player, player.world.regions[x])
                player.loading_regions.append(x)
                # 新区块可能影响了相邻已加载区块的光照，发送邻居的光照更新
                for neighbor_rx in (x - 1, x + 1):
                    if neighbor_rx in player.loading_regions:
                        neighbor = player.world.regions.get(neighbor_rx)
                        if neighbor is not None:
                            light_update = {
                                'rx': neighbor_rx,
                                'light_array': neighbor.get_full_light_dict(),
                                'sky_light_array': neighbor.get_full_sky_light_dict(),
                                'block_light_array': neighbor.get_full_block_light_dict(),
                            }
                            self.send_client_socket(player, light_update, "LightUpdate")

    def close_server(self):
        self.running = False
        self.socket_server.running = False
        self.chunk_gen_pool.shutdown(wait=True)

    def on_player_disconnect(self, player: Player):
        # 广播离开消息（黄色，排除已离开的玩家）
        self.broadcast_chat(f"{player.name} left the game", (255, 255, 85), exclude=player)
        self.players.remove(player)
        self.socket_server.connections.pop(player)
