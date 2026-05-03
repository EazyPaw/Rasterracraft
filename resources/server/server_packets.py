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
    elif type(obj) == Player and obj_type == "Teleport":
        return {
            '__class__': 'Teleport',
            'x': obj.x,
            'y': obj.y,
        }
    elif obj_type == "Forward":
        return obj
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
        player.x = packet['x']
        player.y = packet['y']
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
            print(world.get_sky_light(packet['x'], packet['y']))
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
    if packet['__class__'] != 'PlayerMove':
        logging.debug(f"Received {packet['__class__']} packet.")
        logging.debug(packet)

def forward_packet_to_others(packet: dict, player: Player, mode = 0):
    if mode == 0:
        for other_player in player.world.server.players:
            if other_player != player:
                other_player.world.server.send_client_socket(other_player, packet, "Forward")


