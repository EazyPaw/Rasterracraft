from resources.server.world_class import Chunk


def encode_packet(obj, obj_type = None, args = None) -> dict:
    if args is None:
        args = []
    if type(obj) == Chunk:
        return obj.to_dict()
    return {}

def decode_packet(packet: dict):
    if '__class__' not in dict: return
