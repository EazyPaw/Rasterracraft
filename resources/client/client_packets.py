import logging
from typing import TYPE_CHECKING

from resources.client.client_player import ClientPlayer
from resources.server.block_class import Block
from resources.server.blocks import get_block_by_id
from resources.server.location import Location

if TYPE_CHECKING:
    from resources.client.client_main import Client


def decode_packet(packet: dict, client: 'Client') -> None:
    """
    将服务器数据包转化为相应对象并执行对应操作
    """
    if '__class__' not in packet:
        logging.warning("Received unknown packet")
        return
    elif packet['__class__'] == 'Chunk':
        # {
        #     "__Class__": "Chunk",  # 约 10 字节
        #     "x": rx,  # 整数，约 4-8 字节
        #     "region_array": {  # 包含 8192 个键值对
        #         "0,0,0": {"id": "air", "nbt": {}},
        #         "0,0,1": {"id": "air", "nbt": {}},
        #         ...
        #         "15,255,1": {"id": "air", "nbt": {}}
        #     }
        #     "light_array" : {"x,y": int}
        # }
        # 通过线程池异步加载，避免频繁创建/销毁线程，同时限制并发数
        pool = client.chunk_load_pool
        pool.submit(client.client_world.load_chunk, packet['x'], packet['region_array'])
        if 'light_array' in packet:
            pool.submit(client.client_world.load_lights, packet['x'], packet['light_array'])

    elif packet['__class__'] == 'Teleport':
        # {
        #     '__class__': 'Teleport',
        #     'x': obj.x,
        #     'y': obj.y,
        # }
        client.client_player.x = packet['x']
        client.client_player.y = packet['y']
    elif packet['__class__'] == 'BreakBlock':
        # {
        #     '__class__': 'BreakBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        # }
        world = client.client_world
        if 0 <= packet['y'] < world.y_max:
            world.break_block(packet['x'], packet['y'], packet['z'])
    elif packet['__class__'] == 'PlaceBlock':
        # {
        #     '__class__': 'PlaceBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        #     'block_id': obj.block_id,
        # }
        world = client.client_world
        if 0 <= packet['y'] < world.y_max:
            block = get_block_by_id(packet['block_id'])
            block.place_at(Location(world, packet['x'], packet['y'], packet['z']))
    elif packet['__class__'] == 'LightUpdate':
        # {
        #     '__class__': 'LightUpdate',
        #     'rx': chunk_x,
        #     'light_array': {"x,y": int}
        # }
        client.client_world.update_lights(packet['rx'], packet['light_array'])
    logging.debug(f"Received {packet['__class__']} packet.")

def encode_packet(obj, obj_type = None, args = None) -> dict:
    """
    将客户端数据包编码为字典发送至服务器
    """
    if args is None:
        args = []
    if type(obj) == ClientPlayer and obj_type == 'PlayerMove':
        return {
            '__class__': 'PlayerMove',
            'x': obj.x,
            'y': obj.y,
        }
    elif  isinstance(obj, Block) and obj_type == 'BreakBlock':
        location: Location = obj.location
        return {
            '__class__': 'BreakBlock',
            'x': location.x,
            'y': location.y,
            'z': location.z,
        }
    elif  isinstance(obj, Block) and obj_type == 'PlaceBlock':
        location: Location = obj.location
        return {
            '__class__': 'PlaceBlock',
            'x': location.x,
            'y': location.y,
            'z': location.z,
            'block_id': obj.block_id,
        }
    logging.warning("Unknown packet to encode")
    logging.debug(f"Encoding{type(obj)},{obj_type} packet.")
    return {}