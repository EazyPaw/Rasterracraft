import math

from resources.client.entity_skeleton import FallingBlockSkeleton, PlayerSkeleton
from resources.server.blocks import get_block_by_id
from resources.server.location import Location, Vector


class ClientEntity:
    def __init__(self, client, packet: dict):
        self.client = client
        self.uuid = str(packet.get('uuid', ''))
        self.entity_id = packet.get('entity_id', 'null')
        self.x = float(packet.get('x', 0.0))
        self.y = float(packet.get('y', 0.0))
        self.z = int(packet.get('z', 0))
        self.width = float(packet.get('width', 1.0))
        self.height = float(packet.get('height', 1.0))
        self.motion = Vector(0.0, 0.0)
        self.facing = int(packet.get('facing', 0))
        self.sneaking = bool(packet.get('sneaking', False))
        self.sprinting = bool(packet.get('sprinting', False))
        self.on_ground = bool(packet.get('on_ground', False))
        self.name = packet.get('name', self.uuid[:8])
        self.block = None
        self.skeleton = None
        self.apply_packet(packet, initial=True)

    def apply_packet(self, packet: dict, *, initial: bool = False):
        new_x = float(packet.get('x', self.x))
        new_y = float(packet.get('y', self.y))

        self.entity_id = packet.get('entity_id', self.entity_id)
        self.x = new_x
        self.y = new_y
        self.z = int(packet.get('z', self.z))
        self.width = float(packet.get('width', self.width))
        self.height = float(packet.get('height', self.height))
        motion = packet.get('motion', {})
        self.motion.x = float(motion.get('x', self.motion.x))
        self.motion.y = float(motion.get('y', self.motion.y))
        self.facing = int(packet.get('facing', self.facing))
        self.sneaking = bool(packet.get('sneaking', self.sneaking))
        self.sprinting = bool(packet.get('sprinting', self.sprinting))
        self.on_ground = bool(packet.get('on_ground', self.on_ground))
        self.name = packet.get('name', self.name)

        block_data = packet.get('block_data')
        if block_data:
            block = get_block_by_id(block_data['id'])
            block.write_nbt(block_data.get('nbt', {}))
            block.location = Location(
                self.client.client_world,
                math.floor(self.x),
                math.floor(self.y),
                self.z,
            )
            self.block = block
        self._ensure_skeleton()

    def _ensure_skeleton(self):
        if self.skeleton is not None:
            return
        if self.entity_id == "player":
            self.skeleton = PlayerSkeleton(self.client, self, pinned=False)
        elif self.entity_id == "falling_block":
            self.skeleton = FallingBlockSkeleton(self.client, self)
