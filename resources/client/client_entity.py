import math
import time

from resources.client.entity_skeleton import PlayerSkeleton
from resources.server.entities.falling_block import FallingBlockSkeleton
from resources.server.entities.primed_tnt import PrimedTNTSkeleton
from resources.server.entities.zombie import ZombieSkeleton
from resources.server.entities.chicken import ChickenSkeleton
from resources.server.entities.cow import CowSkeleton
from resources.server.entities.pig import PigSkeleton
from resources.server.entities.sheep import SheepSkeleton
from resources.server.blocks import get_block_by_id
from resources.server.item_class import ItemStack
from resources.server.location import Location, Vector
from resources.server.materials import get_material_by_id
from resources.server.utils import client_method
from resources.server.attributes import AttributeMap


class ItemEntityRenderer:
    """Small, bobbing world item renderer for server-synchronised drops."""
    # Minecraft resets its item-render random source to a fixed seed, which
    # makes equal stacks use the same copy layout on every frame.  In the 2D
    # renderer an explicit table is clearer and preserves that determinism.
    COPY_OFFSETS = (
        (0.000, 0.000),
        (-0.095, 0.035),
        (0.080, 0.070),
        (-0.040, -0.075),
        (0.070, -0.040),
    )

    @client_method
    def __init__(self, entity, client = None):
        self.client = client
        self.entity = entity
        self.created_at = time.perf_counter()

    def update(self):
        pass

    @staticmethod
    def get_render_copy_count(amount: int) -> int:
        amount = max(0, int(amount))
        if amount >= 49:
            return 5
        if amount >= 33:
            return 4
        if amount >= 17:
            return 3
        if amount >= 2:
            return 2
        return 1

    @classmethod
    def get_copy_offsets(cls, amount: int):
        return cls.COPY_OFFSETS[:cls.get_render_copy_count(amount)]

    def draw(self):
        item = getattr(self.entity, "item", None)
        if item is None or item.is_empty():
            return
        render = self.client.render
        texture = item.get_texture(render.trans_scale * 0.36, shadow=True)
        if texture is None:
            return
        bob = math.sin((time.perf_counter() - self.created_at) * 4.0) * render.block_size * 0.04
        sx, sy = render.trans_world_location((self.entity.x, self.entity.y + 0.22))
        # Item entities deliberately do not use the living-entity red hurt
        # flash.  World lighting still applies to every rendered copy.
        tint = render.get_world_light_tint(self.entity.x, self.entity.y)
        texture = render.get_tinted_surface(texture, tint)
        origin_x = sx - texture.get_width() / 2
        origin_y = sy - texture.get_height() / 2 + bob
        for offset_x, offset_y in self.get_copy_offsets(item.amount):
            render.blit(texture, (
                round(origin_x + offset_x * render.block_size),
                round(origin_y + offset_y * render.block_size),
            ))


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
        self.health = float(packet.get('health', 20))
        self.max_health = float(packet.get('max_health', 20))
        self.attributes = AttributeMap()
        self.hurt_time = int(packet.get('hurt_time', 0))
        self.aggressive = bool(packet.get('aggressive', False))
        self.look_angle = float(packet.get('look_angle', 0.0))
        self.attack_animation_ticks = int(packet.get('attack_animation_ticks', 0))
        self.is_baby = bool(packet.get('is_baby', False))
        self.age_scale = float(packet.get('age_scale', 1.0))
        self.flap_speed = float(packet.get('flap_speed', 0.0))
        self.sheared = bool(packet.get('sheared', False))
        self.wool_color = packet.get('wool_color', 'white')
        self.eat_animation_ticks = int(packet.get('eat_animation_ticks', 0))
        self.saddled = bool(packet.get('saddled', False))
        self.breaking = bool(packet.get('breaking', False))
        self.eating = bool(packet.get('eating', False))
        self.break_progress = float(packet.get('break_progress', 0.0))
        raw_break_target = packet.get('break_target')
        self.break_target = tuple(raw_break_target[:3]) if isinstance(raw_break_target, (list, tuple)) else None
        self.fuse = int(packet.get('fuse', 0))
        self.initial_fuse = int(packet.get('initial_fuse', self.fuse))
        self.name = packet.get('name', self.uuid[:8])
        self.block = None
        self.skeleton = None
        self.apply_packet(packet, initial=True)

    def apply_packet(self, packet: dict, *, initial: bool = False):
        old_attack_animation_ticks = self.attack_animation_ticks
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
        self.health = float(packet.get('health', self.health))
        self.max_health = float(packet.get('max_health', self.max_health))
        if 'attributes' in packet:
            self.attributes.apply_sync_snapshot(packet['attributes'])
        self.hurt_time = int(packet.get('hurt_time', self.hurt_time))
        self.aggressive = bool(packet.get('aggressive', self.aggressive))
        self.look_angle = float(packet.get('look_angle', self.look_angle))
        self.attack_animation_ticks = int(packet.get(
            'attack_animation_ticks', self.attack_animation_ticks
        ))
        self.is_baby = bool(packet.get('is_baby', self.is_baby))
        self.age_scale = float(packet.get('age_scale', self.age_scale))
        self.flap_speed = float(packet.get('flap_speed', self.flap_speed))
        self.sheared = bool(packet.get('sheared', self.sheared))
        self.wool_color = packet.get('wool_color', self.wool_color)
        self.eat_animation_ticks = int(packet.get('eat_animation_ticks', self.eat_animation_ticks))
        self.saddled = bool(packet.get('saddled', self.saddled))
        self.breaking = bool(packet.get('breaking', self.breaking))
        self.eating = bool(packet.get('eating', self.eating))
        self.break_progress = float(packet.get('break_progress', self.break_progress))
        if 'break_target' in packet:
            raw_break_target = packet.get('break_target')
            self.break_target = (
                tuple(raw_break_target[:3])
                if isinstance(raw_break_target, (list, tuple)) and len(raw_break_target) >= 3
                else None
            )
        elif not self.breaking:
            self.break_target = None
        self.fuse = int(packet.get('fuse', self.fuse))
        self.initial_fuse = int(packet.get('initial_fuse', self.initial_fuse))
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
        item_data = packet.get('item_data')
        if item_data:
            self.item = ItemStack(
                get_material_by_id(item_data.get('id', 'air')),
                int(item_data.get('amount', 1)),
                item_data.get('nbt', {}),
            )
        held_item_data = packet.get('held_item_data')
        if held_item_data is not None:
            self.held_item = ItemStack(
                get_material_by_id(held_item_data.get('id', 'air')),
                int(held_item_data.get('amount', 0)),
                held_item_data.get('nbt', {}),
            )
        self._ensure_skeleton()
        if (
            self.entity_id == "player"
            and self.skeleton is not None
            and (
                (initial and self.attack_animation_ticks > 0)
                or self.attack_animation_ticks > old_attack_animation_ticks
            )
        ):
            self.skeleton.trigger_swing()

    def _ensure_skeleton(self):
        if self.skeleton is not None:
            return
        if self.entity_id == "player":
            self.skeleton = PlayerSkeleton(self, pinned=False)
        elif self.entity_id == "falling_block":
            self.skeleton = FallingBlockSkeleton(self)
        elif self.entity_id == "item":
            self.skeleton = ItemEntityRenderer(self)
        elif self.entity_id == "zombie":
            self.skeleton = ZombieSkeleton(self)
        elif self.entity_id == "chicken":
            self.skeleton = ChickenSkeleton(self)
        elif self.entity_id == "cow":
            self.skeleton = CowSkeleton(self)
        elif self.entity_id == "pig":
            self.skeleton = PigSkeleton(self)
        elif self.entity_id == "sheep":
            self.skeleton = SheepSkeleton(self)
        elif self.entity_id == "primed_tnt":
            self.skeleton = PrimedTNTSkeleton(self)
