import logging

from resources.server.blocks import get_block_by_id
from resources.server.location import Location
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
        }
    elif obj_type == "Forward": # 转发给服务器内其它玩家
        return obj
    elif obj_type == "LightUpdate":
        # obj 应该是 {'rx': int, 'light_array': dict}
        return {
            '__class__': 'LightUpdate',
            'rx': obj['rx'],
            'light_array': obj['light_array']
        }
    elif obj_type == "BiomeUpdate":
        # obj 应该是 {'rx': int, 'biome_array': dict}
        return {
            '__class__': 'BiomeUpdate',
            'rx': obj['rx'],
            'biome_array': obj['biome_array']
        }
    elif isinstance(obj, Location) and obj_type == 'BreakBlock':
        return {
            '__class__': 'BreakBlock',
            'x': obj.x,
            'y': obj.y,
            'z': obj.z,
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
        player.on_moving()
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
            forward_packet_to_others(packet, player)

            # 发送光照更新（主区块 + 相邻区块）
            _send_light_updates_for_boundary(world, player, packet['x'] // 16)
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
            forward_packet_to_others(packet, player)

            # 发送光照更新（主区块 + 相邻区块）
            _send_light_updates_for_boundary(world, player, packet['x'] // 16)
    if packet['__class__'] != 'PlayerMove':
        logging.debug(f"Received {packet['__class__']} packet.")
        logging.debug(packet)

def _send_light_updates_for_boundary(world, player, rx: int):
    """发送主区块及其相邻区块的光照更新数据包"""
    for chunk_rx in (rx - 1, rx, rx + 1):
        chunk = world.regions.get(chunk_rx)
        if chunk is not None:
            light_update = {
                'rx': chunk_rx,
                'light_array': chunk.get_full_light_dict()
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

def forward_packet_to_others(packet: dict, player: Player, mode = 0):
    if mode == 0:
        for other_player in player.world.server.players:
            if other_player != player:
                other_player.world.server.send_client_socket(other_player, packet, "Forward")


