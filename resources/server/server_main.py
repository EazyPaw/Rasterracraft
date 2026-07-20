import logging
import random
import socket
import struct
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypedDict

import msgpack
import numpy as np

import resources.server.generator as generator
from resources.server import save_manager
from resources.server.commands import CommandExecutor
from resources.server.inventory import (
    Inventory, normalize_inventory_payload, payload_to_stack,
    restore_inventory, serialize_inventory, stack_to_payload,
)
from resources.server.player import Player
from resources.server.server_packets import encode_packet, decode_packet
from resources.server.text import Text
from resources.server.utils import recv_exact, set_client, set_server
from resources.server.world_class import Weather, World, WorldAttribute


class EventDict(TypedDict):
    tick: int
    func: Callable
    args: tuple

class Server:
    def __init__(self, integrated = False, client = None, save_id: str | None = None):
        self.running = True
        self.main_world_id = "overworld"
        self.worlds: dict[str, World] = {}
        self.ready = threading.Event()  # 用于等待初始化完成
        self.TPS = 0
        self.rate = 20
        self.ticks = 0
        self.server_ticks = 0
        self.view_distance = 4
        self.chunk_unload_margin = 2
        self.players: list[Player] = []
        self.max_players = 20
        self.integrated = integrated
        self.save_id = save_id
        self.level_data: dict[str, Any] | None = None
        self._save_lock = threading.RLock()
        self.autosave_interval_ticks = self.rate * 5
        self.socket_server = self.SocketServer(self)
        self.initialized = False
        self.input_thread = threading.Thread(target=self.check_input, name="Command thread")
        self.input_thread.daemon = True
        self.commands_error_traceback = False
        self.input_thread.start()
        self.command_executor = CommandExecutor(self)
        self.client = client
        # 区块生成线程池：generate_chunk 是 CPU 密集型操作（噪声计算），
        # noise 库（C 扩展）和 numpy 在计算时会释放 GIL，因此多线程有实际收益。
        self.chunk_gen_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ChunkGen")
        self.registered_events: list[EventDict] = []
        if client is not None:
            set_client(client)
        set_server(self)

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

    def register_event(self, func, *args, ticks = 1):
        tick = self.ticks + ticks
        event: EventDict = {"tick": tick, "func": func, "args": args}
        self.registered_events.append(event)

    class SocketServer:
        def __init__(self, server):
            self.server = server
            self.running = True
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.bind(("0.0.0.0", 14525))
            self.server_sock.listen(5)
            self.connections: dict[Player, tuple[socket.socket, Any]] = {}
            self.send_locks: dict[Player, threading.Lock] = {}
            self.thread = threading.Thread(target=self.run, name="SocketServerThread")
            self.thread.daemon = True
            self.thread.start()

        def run(self):
            logging.info("Socket server started, waiting for server initialization...")
            # 等待服务器初始化完成（worlds 已创建）
            self.server.ready.wait()
            logging.info("Server ready, accepting connections.")
            while self.running:

                try:
                    client_sock, client_addr = self.server_sock.accept()
                except OSError:
                    if self.running:
                        logging.error("Socket server accept failed")
                    break

                # This hook intentionally runs before a Player is created or
                # added to the server.  Server implementations can override
                # ``check_player_connection`` to reject an address, token,
                # whitelist entry, etc.  Returning None accepts the client;
                # returning Text or str sends a Disconnect packet instead.
                try:
                    rejection_reason = self.server.check_player_connection(
                        client_sock, client_addr
                    )
                except Exception:
                    logging.exception("Player connection check failed for %s", client_addr)
                    self.server.reject_connection(client_sock, None)
                    continue
                if rejection_reason is not None:
                    self.server.reject_connection(client_sock, rejection_reason)
                    continue

                spawn_x, spawn_y = self.server.get_player_spawn()
                player = Player(spawn_x, spawn_y, self.server.worlds["overworld"])
                # The first local integrated player is the only implicit
                # operator. Standalone/network players require an explicit
                # server-side permission assignment.
                player.is_operator = bool(self.server.integrated and not self.server.players)
                self.server.restore_player_state(player)
                self.connections[player] = (client_sock, client_addr)
                self.send_locks[player] = threading.Lock()
                self.server.players.append(player)
                logging.info(f"Client {client_addr} connected")
                for other in self.server.players:
                    if other is not player and other.is_loading_position(int(player.x), int(player.y), 0):
                        self.server.send_client_socket(other, player, "EntitySpawn")
                self.server.broadcast_chat(f"{player.name} joined the game", (255, 255, 85))
                initial_center = int(player.x // 16)
                self.server.send_client_socket(
                    player,
                    {
                        '__class__': 'WorldLoadStart',
                        'regions': list(range(
                            initial_center - self.server.view_distance,
                            initial_center + self.server.view_distance + 1,
                        )),
                    },
                    "Forward",
                )
                # Use Player.teleport_to even for the initial position so the
                # first client movement cannot race ahead of its spawn packet.
                player.teleport_to(player.x, player.y)
                self.server.send_client_socket(player, player.world.get_weather_packet(), "Forward")
                self.server.send_client_socket(
                    player,
                    {'__class__': 'TimeUpdate', 'time': int(player.world.world_time)},
                    "Forward",
                )
                self.server.send_client_socket(player, player, "GamemodeUpdate")
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

    def process_events(self):
        for i in range(len(self.registered_events) - 1, -1, -1):
            e = self.registered_events[i]
            if e["tick"] == self.ticks:
                e["func"](*e["args"])  # 解包参数
                del self.registered_events[i]

    def integrated_check(self):
        """
        检测 subprocess 模式下否因为客户端意外结束导致服务端持续运行，成为僵尸线程
        :return:
        """
        if not self.players: # 无玩家
            logging.warning("Null client, closing integrated server.")
            self.close_server()
            self.register_event(self.integrated_check, ticks=20)

    def run(self):

        logging.info(f"Server initialized")

        if self.integrated and self.client is None:
            self.register_event(self.integrated_check, ticks=200)

        next_time = time.perf_counter()
        over_ticks = 0

        while self.running:
            interval = 1.0 / self.rate

            self.tick()
            self.process_events()

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
            self.ticks += 1

    def init(self):
        logging.info("Initializing server")
        seed = random.randint(-23767, 23767)
        world_time = 0
        if self.save_id:
            self.level_data = save_manager.ensure_level(self.save_id)
            world_meta = self.level_data.setdefault("worlds", {}).setdefault(self.main_world_id, {})
            seed = int(world_meta.get("seed", seed))
            world_time = int(world_meta.get("world_time", 0))
            world_meta["seed"] = seed
            world_meta["generator"] = "MinecraftLike2D"
            world_meta["max_build_height"] = 256
            save_manager.save_level(self.save_id, self.level_data)
        self.worlds["overworld"] = World(self
                                         ,"overworld"
                                         , generator.MinecraftLike2D
                                         , WorldAttribute()
                                         , seed)
        self.worlds["overworld"].world_time = world_time
        weather_name = str(world_meta.get("weather", Weather.CLEAR.value)) if self.save_id else Weather.CLEAR.value
        try:
            self.worlds["overworld"].weather = Weather(weather_name)
        except ValueError:
            self.worlds["overworld"].weather = Weather.CLEAR
        if self.save_id:
            self.worlds["overworld"].weather_tick = max(
                1, int(world_meta.get("weather_tick", self.worlds["overworld"].weather_tick))
            )
        self.initialized = True
        self.ready.set()  # 通知 socket 线程服务器已就绪
        self.run()

    def tick(self):
        self.server_ticks += 1
        for player in tuple(self.players):
            player.tick_damage_state()
        for world in self.worlds.values():
            world.world_time = (world.world_time + 1) % 24000
            world.tick_weather()
            world.tick_random_blocks()
        if self.server_ticks % 5 == 0:
            for player in self.players:
                self.send_client_socket(
                    player,
                    {'__class__': 'TimeUpdate', 'time': int(player.world.world_time)},
                    "Forward"
                )
        self.load_chunks()
        for world in self.worlds.values():
            world.tick_fluids()
        for world in self.worlds.values():
            world.update_entities()
        for world in self.worlds.values():
            world.flush_light_updates()
        self.unload_far_chunks()
        if self.save_id and self.server_ticks % self.autosave_interval_ticks == 0:
            self.save_all()

    def get_player_spawn(self) -> tuple[float, float]:
        if not self.level_data:
            return 0.0, 100.0
        player_data = self.level_data.get("player", {})
        return float(player_data.get("x", 0.0)), float(player_data.get("y", 100.0))

    def restore_player_state(self, player: Player) -> None:
        if not self.level_data:
            return
        data = self.level_data.get("player", {})
        player.health = max(0.0, min(player.max_health, float(data.get("health", player.max_health))))
        player.food_level = max(0, min(20, int(data.get("food_level", 20))))
        player.saturation = max(0.0, min(float(player.food_level), float(data.get("saturation", 5.0))))
        player.experience = max(0, int(data.get("experience", 0)))
        player.experience_level = max(0, int(data.get("experience_level", 0)))
        # 恢复玩家的游戏模式（优先读取玩家存档，回退到世界默认模式）
        saved_gamemode = data.get("gamemode") or self.level_data.get("game_mode")
        if saved_gamemode:
            from resources.client.game_mode import get_gamemode_by_id
            player.gamemode = get_gamemode_by_id(saved_gamemode)
        saved_inventory = data.get("inventory")
        if isinstance(saved_inventory, list):
            restore_inventory(player.inventory, saved_inventory)
        else:
            player.inventory = Inventory(36)
            player._initialize_inventory()
        restore_inventory(player.crafting_grid, data.get("crafting", []))
        player.cursor_stack = payload_to_stack(data.get("cursor", {}))
        try:
            player.selected_slot = max(0, min(8, int(data.get("selected_slot", 0))))
        except (TypeError, ValueError):
            player.selected_slot = 0

    def save_all(self, last_player: Player | None = None, *, force: bool = False):
        if not self.save_id:
            return
        with self._save_lock:
            for world in self.worlds.values():
                self._save_world_chunks(world, world.take_dirty_chunks())
            self._save_level_metadata(last_player)
            if force:
                logging.info(f"Saved world '{self.save_id}'")

    def _save_world_chunks(self, world: World, chunk_rxs) -> bool:
        if not self.save_id:
            return False
        with self._save_lock:
            rxs = [int(rx) for rx in chunk_rxs]
            chunks = [world.regions[rx] for rx in rxs if rx in world.regions]
            if not chunks:
                return True
            try:
                save_manager.save_chunks(self.save_id, world.id_name, chunks)
                for chunk in chunks:
                    world.clear_chunk_dirty(chunk.x)
                return True
            except Exception as e:
                for rx in rxs:
                    world.mark_chunk_dirty(rx)
                logging.error(f"Failed to save {world.id_name} chunks {rxs}: {e}")
                logging.error(traceback.format_exc())
                return False

    def _save_level_metadata(self, last_player: Player | None = None):
        if not self.save_id:
            return
        if self.level_data is None:
            self.level_data = save_manager.ensure_level(self.save_id)
        worlds_meta = self.level_data.setdefault("worlds", {})
        for world in self.worlds.values():
            worlds_meta[world.id_name] = {
                "seed": int(world.seed),
                "world_time": int(world.world_time),
                "generator": type(world.generator).__name__,
                "max_build_height": int(world.attribute.MAX_BUILD_HEIGHT),
                "weather": world.weather.value,
                "weather_tick": int(world.weather_tick),
            }
        player = last_player
        if player is None and self.players:
            player = self.players[0]
        if player is not None:
            player_data = {"x": float(player.x), "y": float(player.y), "health": float(player.health),
                           "food_level": int(getattr(player, "food_level", 20)),
                           "saturation": float(getattr(player, "saturation", 5.0)),
                           "experience": int(getattr(player, "experience", 0)),
                           "experience_level": int(getattr(player, "experience_level", 0)),
                           "gamemode": player.gamemode.name_id if hasattr(player.gamemode, "name_id") else "survival",
                           "selected_slot": max(0, min(8, int(getattr(player, "selected_slot", 0)))),
                           "cursor": stack_to_payload(player.cursor_stack), "inventory": normalize_inventory_payload(
                    serialize_inventory(player.inventory)
                ), "crafting": normalize_inventory_payload(
                    serialize_inventory(player.crafting_grid), 9
                )}
            self.level_data["player"] = player_data
        save_manager.save_level(self.save_id, self.level_data)

    def _resolve_chat_msg(self, msg, color=None):
        """解析聊天消息参数，统一处理 str 和 Text 对象。

        Returns (text: str | dict, color: tuple). Text 会保留逐段样式。
        """
        if isinstance(msg, Text):
            text = msg.to_dict()
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

    def broadcast_sound(self, sound_id: str, x: float, y: float, z: float = 0.0, *, volume: float = 1.0) -> None:
        """Broadcast a server-authoritative sound event to every player."""
        packet = {
            "__class__": "SoundEffect",
            "sound_id": str(sound_id),
            "x": float(x), "y": float(y), "z": float(z),
            "volume": float(volume),
            "global": True,
        }
        for player in tuple(self.players):
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
            if (
                getattr(player, '_disconnecting', False)
                and encoded_obj.get('__class__') != 'Disconnect'
            ):
                return False
            
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
            packet_data = msgpack.packb(clean_obj, use_bin_type=True)
            
            length = len(packet_data)
            connection = self.socket_server.connections[player][0]
            with self.socket_server.send_locks.setdefault(player, threading.Lock()):
                connection.sendall(struct.pack('>I', length) + packet_data)
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
            # Send the spawn column first.  The old left-to-right order waited
            # for several distant chunks before the client received ground.
            region_order = sorted(
                range(rx - self.view_distance, rx + self.view_distance + 1),
                key=lambda value: (abs(value - rx), value),
            )
            for x in region_order:
                if x not in player.loading_regions:
                    if x not in player.world.regions:
                        # 避免对同一区块重复提交生成任务（多个玩家共享同一 World）
                        key = (x, player.world)
                        if key not in gen_futures:
                            gen_futures[key] = self.chunk_gen_pool.submit(
                                player.world.generate_chunk, x
                            )
                    new_chunks.append((player, x))

        # 阶段二：按距离逐个等待并发送。远处区块继续在后台生成，不会
        # 阻塞出生区块到达客户端。
        for player, x in new_chunks:
            future = gen_futures.get((x, player.world))
            if future is not None:
                try:
                    future.result(timeout=30)
                except Exception as e:
                    logging.error(f"Chunk generation failed for region {x}: {e}")
            if x in player.world.regions:
                # Mark it as sent before writing the frame: the client can
                # decode and acknowledge a small compact packet immediately.
                player.loading_regions.append(x)
                self.send_client_socket(player, player.world.regions[x])
                player.world.mark_chunk_dirty(x)
                player.world.send_entities_in_chunk_to_player(player, x)
                self._send_players_in_chunk_to_player(player, x)
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

        # Tell the client that the complete initial view-distance batch has
        # been queued.  It still waits for every corresponding ChunkReady, so
        # this packet cannot make the loading screen disappear early.
        for player in self.players:
            if player.initial_load_complete_sent:
                continue
            center_rx = int(player.x // 16)
            initial_regions = set(range(
                center_rx - self.view_distance,
                center_rx + self.view_distance + 1,
            ))
            if initial_regions.issubset(set(player.loading_regions)):
                self.send_client_socket(
                    player,
                    {'__class__': 'WorldLoadComplete', 'regions': sorted(initial_regions)},
                    "Forward",
                )
                player.initial_load_complete_sent = True

    def unload_far_chunks(self):
        if not self.save_id:
            return
        keep_margin = self.view_distance + self.chunk_unload_margin
        for player in self.players:
            center_rx = int(player.x // 16)
            keep_min = center_rx - keep_margin
            keep_max = center_rx + keep_margin
            for rx in list(player.loading_regions):
                if rx < keep_min or rx > keep_max:
                    self.send_client_socket(player, {"rx": rx}, "UnloadChunk")
                    player.loading_regions.remove(rx)
                    player.client_loaded_regions.discard(rx)

        for world in self.worlds.values():
            protected: set[int] = set()
            for player in self.players:
                if player.world is world:
                    protected.update(player.loading_regions)
            unload_rxs = [rx for rx in list(world.regions.keys()) if rx not in protected]
            if not unload_rxs:
                continue
            if self._save_world_chunks(world, unload_rxs):
                for rx in unload_rxs:
                    world.regions.pop(rx, None)

    def _send_players_in_chunk_to_player(self, player: Player, rx: int):
        for other in self.players:
            if other is player or other.world is not player.world:
                continue
            if int(other.x // 16) == rx:
                self.send_client_socket(player, other, "EntitySpawn")

    def close_server(self):
        self.save_all(force=True)
        self.running = False
        self.socket_server.running = False
        try:
            self.socket_server.server_sock.close()
        except Exception:
            pass
        self.chunk_gen_pool.shutdown(wait=True)
        logging.info("Server closed")

    def check_player_connection(self, client_sock, client_addr) -> Text | str | None:
        """连接准入接口。

        返回 ``None`` 接受连接；返回 ``Text`` 或字符串则拒绝连接并把
        返回值显示在客户端断开界面。这里保留了一个可直接改写的示例：
        将 ``some_condition`` 换成白名单、人数上限或认证检查即可。
        """
        # 一个可用的准入示例：服务器满员时拒绝新连接。
        if len(self.players) >= self.max_players:
            return "disconnect.serverFull"
        # 其它规则示例（默认关闭）：
        # if some_condition(client_addr):
        #     return Text("This server is not accepting your connection")
        return None

    def reject_connection(self, client_sock, reason: Text | str | None) -> bool:
        """向尚未成为 Player 的客户端发送拒绝原因并关闭连接。"""
        packet = self._disconnect_packet(reason, default_key="disconnect.loginFailed")
        try:
            payload = msgpack.packb(packet, use_bin_type=True)
            client_sock.sendall(struct.pack('>I', len(payload)) + payload)
            try:
                client_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client_sock.close()
            return True
        except (ConnectionError, OSError):
            logging.info("Rejected client disconnected before receiving the response")
            try:
                client_sock.close()
            except OSError:
                pass
            return False

    @staticmethod
    def _disconnect_packet(reason: Text | str | None, *, default_key: str) -> dict:
        if reason is None:
            reason = default_key
            reason_is_translation_key = True
        elif isinstance(reason, Text):
            reason = reason.to_dict()
            reason_is_translation_key = False
        else:
            reason = str(reason)
            reason_is_translation_key = reason.startswith(
                ("disconnect.", "connect.", "gui.")
            )
        return {
            '__class__': 'Disconnect',
            'reason': reason,
            'reason_is_translation_key': reason_is_translation_key,
        }

    def kick_player(self, player: Player, reason: Text | str | None = None) -> bool:
        """主动断开一个已加入玩家的连接（游戏内踢出接口）。"""
        if player not in self.players or getattr(player, '_disconnecting', False):
            return False
        setattr(player, '_disconnecting', True)
        sent = self.send_client_socket(
            player,
            self._disconnect_packet(reason, default_key="disconnect.kicked"),
            "Forward",
        )
        if sent:
            # Normal path: the client acknowledges the Disconnect packet and
            # acknowledge_disconnect closes the socket. This timeout handles a
            # frozen or malicious client that never sends the acknowledgement.
            self.register_event(
                self._force_kicked_disconnect,
                player,
                ticks=max(1, self.rate * 2),
            )
        else:
            self._force_kicked_disconnect(player)
        return sent

    def acknowledge_disconnect(self, player: Player) -> None:
        """Finish a kick after the client confirms the reason was decoded."""
        if not getattr(player, '_disconnecting', False):
            return
        self._close_player_connection(player)
        self.on_player_disconnect(player)

    def _force_kicked_disconnect(self, player: Player) -> None:
        if player not in self.players and player not in self.socket_server.connections:
            return
        self._close_player_connection(player)
        self.on_player_disconnect(player)

    def _close_player_connection(self, player: Player) -> None:
        connection_info = self.socket_server.connections.get(player)
        if connection_info is None:
            return
        connection = connection_info[0]
        try:
            connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            connection.close()
        except OSError:
            pass

    def on_player_disconnect(self, player: Player):
        if player not in self.players and player not in self.socket_server.connections:
            return
        self.save_all(player, force=True)
        # 广播离开消息（黄色，排除已离开的玩家）
        self.broadcast_chat(f"{player.name} left the game", (255, 255, 85), exclude=player)
        for other in self.players:
            if other is not player:
                self.send_client_socket(other, player, "EntityRemove")
        if player in self.players:
            self.players.remove(player)
        self.socket_server.connections.pop(player, None)
        self.socket_server.send_locks.pop(player, None)
