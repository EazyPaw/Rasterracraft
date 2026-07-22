import logging
import math

from resources.server.entity import Entity
from resources.server.location import Location
from resources.server.inventory import payload_to_stack, serialize_inventory, stack_to_payload
from resources.server.item_class import EmptyItemStack
from resources.server.particles import ParticleEffect
from resources.server.player import Player
from resources.server.world_class import Chunk


def encode_packet(obj, obj_type, args) -> dict:
    if args is None:
        args = []
    if type(obj) == Chunk:
        return obj.to_dict()
    elif isinstance(obj, Player) and obj_type == "Teleport":
        obj.refresh_attribute_modifiers()
        packet = {'__class__': 'Teleport', 'x': obj.x, 'y': obj.y, 'uuid': str(obj.uuid), 'name': obj.name,
                  'health': obj.health, 'hurt_time': obj.hurt_time, 'last_hurt_damage': obj.last_hurt_damage,
                  'food_level': getattr(obj, 'food_level', 20), 'saturation': getattr(obj, 'saturation', 5.0),
                  'experience': getattr(obj, 'experience', 0), 'experience_level': getattr(obj, 'experience_level', 0),
                  'selected_slot': getattr(obj, 'selected_slot', 0),
                  'teleport_id': getattr(obj, '_pending_teleport_id', None),
                  'inventory': serialize_inventory(obj.inventory), 'cursor': stack_to_payload(obj.cursor_stack),
                  'equipment': {
                      slot: stack_to_payload(stack) for slot, stack in obj.equipment.items()
                  },
                  'attributes': obj.attributes.sync_snapshot()}
        return packet
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
        if obj.get('format') == 2:
            return {
                '__class__': 'LightUpdate',
                'rx': obj['rx'],
                'format': 2,
                'height': obj['height'],
                'sky_light': obj['sky_light'],
                'block_light': obj['block_light'],
            }
        # Legacy dict layout remains accepted for compatibility.
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
    elif obj_type == "GamemodeUpdate" and isinstance(obj, Player):
        return {
            '__class__': 'GamemodeUpdate',
            'new_mode': obj.gamemode.name_id
        }
    logging.warning("Unknown packet type to encode")
    return {}

def _find_attack_target(player: Player, target_uuid: str):
    target_uuid = str(target_uuid)
    target = player.world.entities.get(target_uuid)
    if target is not None:
        return target
    for candidate in tuple(player.world.server.players):
        if str(getattr(candidate, "uuid", "")) == target_uuid:
            return candidate
    return None


def _can_player_reach_entity(player: Player, target: Entity) -> bool:
    if target is player or getattr(target, "world", None) is not player.world:
        return False
    if getattr(target, "removed", False) or getattr(target, "health", 0) <= 0:
        return False
    if int(getattr(player, "z", 0)) != int(getattr(target, "z", 0)):
        return False
    mode = getattr(getattr(player, "gamemode", None), "name_id", "survival")
    if mode == "spectator":
        return False
    horizontal_gap = max(
        target.x - (player.x + player.width),
        player.x - (target.x + target.width),
        0.0,
    )
    vertical_gap = max(
        target.y - (player.y + player.height),
        player.y - (target.y + target.height),
        0.0,
    )
    reach = max(0.0, float(getattr(player, "interact_range", 5.0)))
    return horizontal_gap * horizontal_gap + vertical_gap * vertical_gap <= reach * reach


def _can_player_reach_block(player: Player, x: int, y: int, z: int) -> bool:
    return player.can_reach_block(x, y, z)


def _read_block_position(packet: dict) -> tuple[int, int, int] | None:
    try:
        values = packet.get('x'), packet.get('y'), packet.get('z')
        if any(isinstance(value, bool) for value in values):
            return None
        numeric = tuple(float(value) for value in values)
        if not all(math.isfinite(value) and value.is_integer() for value in numeric):
            return None
        return tuple(int(value) for value in numeric)
    except (TypeError, ValueError, OverflowError):
        return None


def _reject_player_move(player: Player) -> None:
    # A Teleport confirmation gates stale movement already queued by the
    # client, so one correction cannot immediately be overwritten.
    player.teleport_to(player.x, player.y)


def _allow_action_this_tick(player: Player, action: str) -> bool:
    current_tick = int(getattr(player.world.server, 'server_ticks', 0))
    action_ticks = getattr(player, '_last_action_ticks', None)
    if action_ticks is None:
        action_ticks = {}
        player._last_action_ticks = action_ticks
    if action_ticks.get(action) == current_tick:
        return False
    action_ticks[action] = current_tick
    return True


def _block_intersects_entity(world, block, x: int, y: int, z: int) -> bool:
    get_shape = getattr(block, 'get_collision_box', None)
    shape = get_shape() if callable(get_shape) else None
    if not shape:
        return False
    entities = list(getattr(world, 'entities', {}).values())
    entities.extend(getattr(world.server, 'players', ()))
    seen = set()
    for entity in entities:
        identity = id(entity)
        if identity in seen or getattr(entity, 'removed', False):
            continue
        seen.add(identity)
        if not getattr(entity, 'blocks_block_placement', True):
            continue
        if int(getattr(entity, 'z', 0)) != z:
            continue
        min_x = float(entity.x)
        min_y = float(entity.y)
        max_x = min_x + float(getattr(entity, 'width', 1.0))
        max_y = min_y + float(getattr(entity, 'height', 1.0))
        if any(box.translated(x, y).overlaps(min_x, min_y, max_x, max_y) for box in shape):
            return True
    return False


def decode_packet(packet: dict, player: Player):
    if '__class__' not in packet:
        logging.warning("Received unknown packet")
        logging.debug(packet)
        return
    if packet['__class__'] == 'DisconnectAck':
        player.world.server.acknowledge_disconnect(player)
        return
    if getattr(player, '_disconnecting', False):
        # Once a Disconnect packet has been queued, only its acknowledgement
        # matters. Ignoring movement/GUI packets prevents more outbound state
        # from being generated behind the disconnect reason.
        return
    if packet['__class__'] == 'PlayerMove':
        # {
        #     '__class__': 'PlayerMove',
        #     'x': obj.x,
        #     'y': obj.y,
        # }
        # Ignore movement that was sent before a server-side teleport.  TCP
        # preserves ordering in each direction, but it cannot remove movement
        # packets the client had already sent before it received Teleport.
        if player.is_awaiting_teleport_confirmation:
            return
        if player.health <= 0:
            return
        try:
            new_x = float(packet.get('x'))
            new_y = float(packet.get('y'))
        except (TypeError, ValueError, OverflowError):
            _reject_player_move(player)
            return
        if not math.isfinite(new_x) or not math.isfinite(new_y):
            _reject_player_move(player)
            return
        if not -64.0 <= new_y <= player.world.attribute.MAX_BUILD_HEIGHT + 64.0:
            _reject_player_move(player)
            return
        destination_rx = int(new_x // 16)
        if (
            not player.world.is_chunk_loaded(destination_rx)
            or destination_rx not in player.client_loaded_regions
        ):
            _reject_player_move(player)
            return

        current_tick = int(getattr(player.world.server, 'server_ticks', 0))
        last_tick = int(getattr(player, '_last_move_tick', -1))
        if last_tick == current_tick:
            return
        elapsed_ticks = 1 if last_tick < 0 else max(1, current_tick - last_tick)
        mode = getattr(getattr(player, 'gamemode', None), 'name_id', 'survival')
        if mode == 'creative' and player.flying:
            movement_scale = max(1.0, player.get_attribute_value("flying_speed") / 0.4)
        else:
            movement_scale = max(1.0, player.get_attribute_value("movement_speed") / 0.1)
        # The base envelope is intentionally generous for jitter, but any
        # expansion comes only from server-owned effective attributes.
        max_horizontal = (
            (4.0 if mode == 'creative' else 2.0)
            * movement_scale
            * elapsed_ticks
        )
        max_vertical = (6.0 if mode == 'creative' else 3.0) * elapsed_ticks
        dx = new_x - player.x
        dy = new_y - player.y
        if abs(dx) > max_horizontal or abs(dy) > max_vertical:
            _reject_player_move(player)
            return
        # A player who is already intersecting a block (piston/world edit,
        # legacy save, etc.) must still be able to move and mine their way
        # out.  Only reject movement that enters collision from a free state.
        if (
            player._check_collision_at(new_x, new_y)
            and not player._check_collision_at(player.x, player.y)
        ):
            _reject_player_move(player)
            return

        previous_y = player.y
        was_on_ground = bool(player.on_ground)
        player.x = new_x
        player.y = new_y
        player.motion.x = dx
        player.motion.y = dy
        player.sneaking = packet.get('sneaking') is True
        player.sprinting = (
            packet.get('sprinting') is True
            and (mode != 'survival' or player.food_level > 6)
        )
        try:
            facing = int(packet.get('facing', player.facing))
        except (TypeError, ValueError):
            facing = player.facing
        if facing in (0, 1):
            player.facing = facing
        try:
            look_angle = float(packet.get('look_angle', player.look_angle))
        except (TypeError, ValueError, OverflowError):
            look_angle = player.look_angle
        if math.isfinite(look_angle):
            player.look_angle = max(-45.0, min(80.0, look_angle))
        player.flying = mode == 'creative' and packet.get('flying') is True
        player.in_fluid = bool(player._get_fluid_interaction()[0])
        player.in_water = player.in_fluid
        player.on_ground = bool(player._check_support_at())
        player._last_move_tick = current_tick
        player.record_server_movement(previous_y, was_on_ground, abs(dx))
        player.on_moving()
        forward_packet_to_others(player, player, mode="entity_update")
    elif packet['__class__'] == 'TeleportConfirm':
        player.confirm_teleport(packet.get('teleport_id'))
    elif packet['__class__'] == 'ChunkReady':
        try:
            rx = int(packet.get('rx'))
        except (TypeError, ValueError):
            return
        if rx in player.loading_regions and rx in player.world.regions:
            player.client_loaded_regions.add(rx)
    elif packet['__class__'] == 'PlayerAction':
        action = packet.get('action')
        if action == 'abort_breaking':
            player.clear_breaking()
            return
        if action == 'continue_eating':
            player.request_eating()
            return
        if action == 'stop_eating':
            player.clear_eating()
            return
        if action != 'continue_breaking':
            return
        position = _read_block_position(packet)
        if position is not None:
            player.request_breaking(*position)

    elif packet['__class__'] == 'BreakBlock':
        position = _read_block_position(packet)
        if position is not None:
            player.finish_breaking(*position)

    elif packet['__class__'] == 'UseBlock':
        if not _allow_action_this_tick(player, 'use_block'):
            return
        position = _read_block_position(packet)
        if position is None:
            return
        x, y, z = position
        world = player.world
        if not (0 <= y < world.attribute.MAX_BUILD_HEIGHT):
            return
        if (
            x // 16 not in player.client_loaded_regions
            or not world.is_chunk_loaded(x // 16)
            or not _can_player_reach_block(player, x, y, z)
        ):
            return
        held = player.inventory[player.selected_slot]
        if held.is_empty():
            return
        block = world.get_block(x, y, z)
        handled = block.on_right_click(player)
        if not handled:
            handled = block.on_use(player, held.material)
        if not handled:
            return
        player.clear_eating()
        player.attack_animation_ticks = max(player.attack_animation_ticks, 6)
        forward_packet_to_others(player, player, mode="entity_update")

    elif packet['__class__'] == 'PickupItem':
        from resources.server.entities.item import Item
        entity = player.world.entities.get(str(packet.get('uuid', '')))
        if isinstance(entity, Item):
            entity.pick_up(player)

    elif packet['__class__'] == 'AttackEntity':
        target = _find_attack_target(player, packet.get('uuid', ''))
        current_tick = int(getattr(player.world.server, 'server_ticks', 0))
        if (
            target is not None
            and current_tick != int(getattr(player, '_last_attack_tick', -1))
            and _can_player_reach_entity(player, target)
        ):
            player._last_attack_tick = current_tick
            player.clear_eating()
            player.attack_animation_ticks = player.attack_animation_duration
            player.attack(target)
            forward_packet_to_others(player, player, mode="entity_update")

    elif packet['__class__'] == 'InteractEntity':
        target = _find_attack_target(player, packet.get('uuid', ''))
        if target is not None and _can_player_reach_entity(player, target):
            slot = max(0, min(len(player.inventory) - 1, int(player.selected_slot)))
            held = player.inventory[slot]
            if target.interact(player, held):
                player.attack_animation_ticks = max(player.attack_animation_ticks, 6)
                forward_packet_to_others(player, player, mode="entity_update")

    elif packet['__class__'] == 'SelfDamage':
        # Fall, hunger and regeneration are advanced by Player.tick_server().
        # Never accept a client-authored damage amount.
        return

    elif packet['__class__'] == 'PlaceBlock':
        # {
        #     '__class__': 'PlaceBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        #     'block_id': obj.block_id,
        # }
        position = _read_block_position(packet)
        if position is None:
            return
        if not _allow_action_this_tick(player, 'place_block'):
            return
        x, y, z = position
        world = player.world
        held = player.inventory[player.selected_slot]
        create_block = getattr(held.material, 'create_block', None)
        if (
            0 <= y < world.attribute.MAX_BUILD_HEIGHT
            and z in (0, 1)
            and x // 16 in player.client_loaded_regions
            and world.is_chunk_loaded(x // 16)
            and _can_player_reach_block(player, x, y, z)
            and not held.is_empty()
            and callable(create_block)
        ):
            player.clear_eating()
            block = create_block()
            if isinstance(packet.get('nbt'), dict):
                apply_placement_nbt = getattr(block, 'apply_placement_nbt', None)
                if callable(apply_placement_nbt):
                    try:
                        apply_placement_nbt(packet['nbt'])
                    except (TypeError, ValueError):
                        return
            # Ignore the client-provided block id; the selected server slot is
            # the only authority for what can be placed.
            if _block_intersects_entity(world, block, x, y, z):
                player.sync_inventory()
                return
            if block.place_at(Location(world, x, y, z)) is not False:
                if getattr(player.gamemode, 'name_id', 'survival') != 'creative':
                    held.reduce_amount(1)
                player.sync_inventory()
                player.attack_animation_ticks = max(player.attack_animation_ticks, 6)
                forward_packet_to_others(player, player, mode="entity_update")

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
    elif packet['__class__'] == 'InventoryClick':
        try:
            player.inventory_click(int(packet.get('slot')), int(packet.get('button')))
        except (TypeError, ValueError):
            player.sync_inventory()
    elif packet['__class__'] == 'CreativeSetSlot':
        if getattr(player.gamemode, 'name_id', 'survival') != 'creative':
            player.sync_inventory()
            return
        try:
            slot = int(packet.get('slot'))
            if not 0 <= slot < len(player.inventory):
                raise ValueError
            item_payload = packet.get('item', packet)
            item = payload_to_stack(item_payload)
            player.inventory[slot] = EmptyItemStack() if item.is_empty() else item
        except (TypeError, ValueError):
            pass
        player.sync_inventory()
    elif packet['__class__'] == 'InventoryDrag':
        try:
            button = int(packet.get('button'))
        except (TypeError, ValueError):
            button = 0
        player.inventory_drag(packet.get('slots', []), button)
    elif packet['__class__'] == 'CraftingDrag':
        try:
            button = int(packet.get('button'))
        except (TypeError, ValueError):
            button = 0
        player.crafting_drag(packet.get('slots', []), button)
    elif packet['__class__'] == 'InventoryDrop':
        cursor = bool(packet.get('cursor', True))
        slot = packet.get('slot')
        try:
            if not cursor:
                slot = int(slot)
                if not 0 <= slot < len(player.inventory):
                    raise ValueError
            amount = packet.get('amount')
            player.drop_inventory(cursor=cursor, slot=slot, amount=amount)
        except (TypeError, ValueError, IndexError):
            player.sync_inventory()
    elif packet['__class__'] == 'InventoryResyncRequest':
        player.sync_inventory()
    elif packet['__class__'] == 'CraftingClick':
        try:
            player.crafting_click(int(packet.get('slot')), int(packet.get('button')))
        except (TypeError, ValueError):
            player.sync_inventory()
    elif packet['__class__'] == 'CraftingTake':
        try:
            width, height = int(packet.get('width', 2)), int(packet.get('height', 2))
        except (TypeError, ValueError):
            width, height = 2, 2
        player.crafting_take(width, height)
    elif packet['__class__'] == 'CraftingClose':
        player.crafting_close()
    elif packet['__class__'] == 'SelectHotbarSlot':
        old_slot = player.selected_slot
        try:
            player.selected_slot = max(0, min(8, int(packet.get('slot'))))
        except (TypeError, ValueError):
            pass
        if player.selected_slot != old_slot:
            player.clear_breaking()
            player.clear_eating()
        player.sync_inventory()
    elif packet['__class__'] == 'ConsumeItem':
        # Legacy instant-consume claims are not authoritative.  New clients
        # keep the eating action alive and Player.tick_eating performs it.
        player.sync_inventory()
    elif packet['__class__'] == 'RequestRespawn':
        if player.health > 0:
            return
        player.health = player.max_health
        player.hurt_time = 0
        player.last_hurt_damage = 0.0
        player.last_damage_source = None
        player.last_damage_type = None
        player._death_handled = False
        player.motion.x = 0.0
        player.motion.y = 0.0
        player.food_level = 20
        player.saturation = 5.0
        player.exhaustion = 0.0
        player.food_tick_timer = 0
        player.fall_distance = 0.0
        player.clear_breaking()
        player.clear_eating()
        block = player.world.find_top_block(player.spawn_point, 0)
        if block is not None:
            player.teleport_to(0.0, block.location.y + 1)
    # if packet['__class__'] not in ('PlayerMove', 'ChatMessage'):
    #     logging.debug(f"Received {packet['__class__']} packet.")
    #     logging.debug(packet)

def _send_light_updates_for_boundary(world, player, rx: int):
    """发送主区块及其相邻区块的光照更新数据包"""
    for chunk_rx in (rx - 1, rx, rx + 1):
        chunk = world.regions.get(chunk_rx)
        if chunk is not None:
            player.world.server.send_client_socket(
                player, chunk.get_light_update_packet(), "LightUpdate"
            )

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
