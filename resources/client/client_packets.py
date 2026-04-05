import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from resources.client.client_main import Client

def decode_packet(packet: dict, client: 'Client') -> None:
    """
    :param packet:
    :param client:
    :return:
    """
    if '__class__' not in packet:
        logging.warning("Received unknown packet")
        return
    if packet['__class__'] == 'Chunk':
        # {
        #     "__Class__": "Chunk",  # 约 10 字节
        #     "x": rx,  # 整数，约 4-8 字节
        #     "region_array": {  # 包含 8192 个键值对
        #         "0,0,0": {"id": "air", "nbt": {}},
        #         "0,0,1": {"id": "air", "nbt": {}},
        #         ...
        #         "15,255,1": {"id": "air", "nbt": {}}
        #     }
        # }
        # 处理 Chunk 包
        client.client_world.load_chunk(packet['x'], packet['region_array'])