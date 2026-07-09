import logging

from resources.server.blocks import get_block_by_id
from resources.server.entity import Entity
from resources.server.location import Location
from resources.server.particles import ParticleEffect
from resources.server.player import Player
from resources.server.world_class import Chunk


def encode_packet(obj, obj_type, args) -> dict:
    if args is None:
        args = []
    if type(obj) == Chunk:
        return obj.to_dict()
    elif isinstance(obj, Player) and obj_type == "Teleport":
        return {
            '__class__': 'Teleport',
            'x': obj.x,
            'y': obj.y,
            'uuid': str(obj.uuid),
            'name': obj.name,
        }
    elif isinstance(obj, Entity) and obj_type in ("EntitySpawn", "EntityUpdate"):
        packet = obj.to_entity_data()
        packet['__class__'] = obj_type
        return packet
    elif obj_type == "EntityRemove":
        return {
            '__class__': 'EntityRemove',
            'uuid': str(obj.uuid) if isinstance(obj, Entity) else str(obj['uuid']),
        }
    elif obj_type == "Forward": # 转发给服务器内其它玩家
        return obj
    elif isinstance(obj, ParticleEffect):
        return obj.to_packet()
    elif obj_type == "LightUpdate":
        # obj 应该是 {'rx': int, 'light_array': dict}
        return {
            '__class__': 'LightUpdate',
            'rx': obj['rx'],
            'light_array': obj['light_array'],
            'sky_light_array': obj.get('sky_light_array'),
            'block_light_array': obj.get('block_light_array'),
        }
    elif obj_type == "BiomeUpdate":
        # obj 应该是 {'rx': int, 'biome_array': dict}
        return {
            '__class__': 'BiomeUpdate',
            'rx': obj['rx'],
            'biome_array': obj['biome_array']
        }
    elif obj_type == "UnloadChunk":
        return {
            '__class__': 'UnloadChunk',
            'rx': obj['rx'],
        }
    elif isinstance(obj, Location) and obj_type == 'BreakBlock':
        return {
            '__class__': 'BreakBlock',
            'x': obj.x,
            'y': obj.y,
            'z': obj.z,
        }
    elif obj_type == "BlockUpdate":
        # obj 是 Block 实例，发送单个方块的更新数据
        return {
            '__class__': 'BlockUpdate',
            'x': obj.location.x,
            'y': obj.location.y,
            'z': obj.location.z,
            'block_data': obj.to_dict(),
        }
    logging.warning("Unknown packet type to encode")
    return {}

def decode_packet(packet: dict, player: Player):
    if '__class__' not in packet:
        logging.warning("Received unknown packet")
        logging.debug(packet)
        return
    elif packet['__class__'] == 'PlayerMove':
        # {
        #     '__class__': 'PlayerMove',
        #     'x': obj.x,
        #     'y': obj.y,
        # }
        if not player.world.is_chunk_loaded(packet['x']//16):
            player.teleport_to(player.x, player.y)
            return
        player.x = packet['x']
        player.y = packet['y']
        player.sneaking = packet.get('sneaking', False)
        player.sprinting = packet.get('sprinting', False)
        player.facing = packet.get('facing', 0)
        player.on_ground = packet.get('on_ground', False)
        player.on_moving()
        forward_packet_to_others(player, player, mode="entity_update")
    elif packet['__class__'] == 'BreakBlock':
        # {
        #     '__class__': 'BreakBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        # }
        world = player.world
        if 0 <= packet['y'] < world.attribute.MAX_BUILD_HEIGHT:
            world.break_block(packet['x'], packet['y'], packet['z'])

    elif packet['__class__'] == 'PlaceBlock':
        # {
        #     '__class__': 'PlaceBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        #     'block_id': obj.block_id,
        # }
        world = player.world
        if 0 <= packet['y'] < world.attribute.MAX_BUILD_HEIGHT:
            block = get_block_by_id(packet['block_id'])
            block.place_at(Location(world, packet['x'], packet['y'], packet['z']))

    elif packet['__class__'] == 'ChatMessage':
        # 客户端发送的聊天消息
        text = packet.get('text', '')
        # 截断过长消息（服务端防御）
        if len(text) > 128:
            text = text[:128]
        # 以 "/" 开头的内容交由命令系统处理
        if text.startswith("/"):
            cmd_text = text[1:]
            args = cmd_text.split()
            if args:
                server = player.world.server
                try:
                    result = server.command_executor.execute_command(player, args)
                    # 检查是否为错误回显（§c 开头）
                    if result.startswith("§c"):
                        color = (255, 85, 85)  # 红色
                    else:
                        color = (255, 255, 255)  # 白色
                except Exception:
                    result = f"§c命令执行错误: {cmd_text}"
                    color = (255, 85, 85)
                # 回显仅发送给执行者
                server.send_chat_to_player(player, result, color)
            return
        # 普通聊天：广播给所有玩家
        formatted = f"<{player.name}> {text}"
        player.world.server.broadcast_chat(formatted, (255, 255, 255))
    elif packet['__class__'] == 'ClientShutdown':
        player.world.server.save_all(player, force=True)
        player.world.server.send_client_socket(player, {'__class__': 'SaveComplete'}, "Forward")
    # if packet['__class__'] not in ('PlayerMove', 'ChatMessage'):
    #     logging.debug(f"Received {packet['__class__']} packet.")
    #     logging.debug(packet)

def _send_light_updates_for_boundary(world, player, rx: int):
    """发送主区块及其相邻区块的光照更新数据包"""
    for chunk_rx in (rx - 1, rx, rx + 1):
        chunk = world.regions.get(chunk_rx)
        if chunk is not None:
            light_update = {
                'rx': chunk_rx,
                'light_array': chunk.get_full_light_dict(),
                'sky_light_array': chunk.get_full_sky_light_dict(),
                'block_light_array': chunk.get_full_block_light_dict(),
            }
            player.world.server.send_client_socket(player, light_update, "LightUpdate")

def _send_biome_updates_for_boundary(world, player, rx: int):
    """发送主区块及其相邻区块的生物群系更新数据包"""
    for chunk_rx in (rx - 1, rx, rx + 1):
        chunk = world.regions.get(chunk_rx)
        if chunk is not None:
            biome_update = {
                'rx': chunk_rx,
                'biome_array': chunk.get_full_biome_dict()
            }
            player.world.server.send_client_socket(player, biome_update, "BiomeUpdate")

def forward_packet_to_others(packet, player: Player, mode = 0):
    if mode == 0:
        for other_player in player.world.server.players:
            if other_player != player:
                other_player.world.server.send_client_socket(other_player, packet, "Forward")
    elif mode == "entity_update":
        for other_player in player.world.server.players:
            if other_player != player and other_player.is_loading_position(int(player.x), int(player.y), 0):
                other_player.world.server.send_client_socket(other_player, packet, "EntityUpdate")


