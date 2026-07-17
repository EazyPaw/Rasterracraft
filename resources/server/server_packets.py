import logging

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
        packet = {
            '__class__': 'Teleport',
            'x': obj.x,
            'y': obj.y,
            'uuid': str(obj.uuid),
            'name': obj.name,
            'health': obj.health,
            'food_level': getattr(obj, 'food_level', 20),
            'saturation': getattr(obj, 'saturation', 5.0),
            'experience': getattr(obj, 'experience', 0),
            'experience_level': getattr(obj, 'experience_level', 0),
            'selected_slot': getattr(obj, 'selected_slot', 0),
            'teleport_id': getattr(obj, '_pending_teleport_id', None),
        }
        packet['inventory'] = serialize_inventory(obj.inventory)
        packet['cursor'] = stack_to_payload(obj.cursor_stack)
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
    elif obj_type == "GamemodeUpdate" and isinstance(obj, Player):
        return {
            '__class__': 'GamemodeUpdate',
            'new_mode': obj.gamemode.name_id
        }
    logging.warning("Unknown packet type to encode")
    return {}

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
        destination_rx = int(float(packet['x']) // 16)
        if (
            not player.world.is_chunk_loaded(destination_rx)
            or destination_rx not in player.client_loaded_regions
        ):
            player.teleport_to(player.x, player.y)
            return
        player.x = packet['x']
        player.y = packet['y']
        player.sneaking = packet.get('sneaking', False)
        player.sprinting = packet.get('sprinting', False)
        player.facing = packet.get('facing', 0)
        player.on_ground = packet.get('on_ground', False)
        # Integrated clients simulate survival locally; clamp state on receipt
        # so it persists safely and cannot corrupt the save format.
        player.health = max(0.0, min(player.max_health, float(packet.get('health', player.health))))
        player.food_level = max(0, min(20, int(packet.get('food_level', getattr(player, 'food_level', 20)))))
        player.saturation = max(0.0, min(float(player.food_level), float(packet.get('saturation', getattr(player, 'saturation', 5.0)))))
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
    elif packet['__class__'] == 'BreakBlock':
        # {
        #     '__class__': 'BreakBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        # }
        world = player.world
        if 0 <= packet['y'] < world.attribute.MAX_BUILD_HEIGHT:
            tool = player.inventory[player.selected_slot].material
            experience = world.break_block(packet['x'], packet['y'], packet['z'], tool=tool)
            if experience:
                player.experience += experience
                player.world.server.send_client_socket(
                    player, {'__class__': 'Experience', 'amount': experience}, 'Forward'
                )

    elif packet['__class__'] == 'PickupItem':
        from resources.server.entities.item import Item
        entity = player.world.entities.get(str(packet.get('uuid', '')))
        if isinstance(entity, Item):
            entity.pick_up(player)

    elif packet['__class__'] == 'PlaceBlock':
        # {
        #     '__class__': 'PlaceBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        #     'block_id': obj.block_id,
        # }
        world = player.world
        held = player.inventory[player.selected_slot]
        target_block = getattr(held.material, 'target_block', None)
        if 0 <= packet['y'] < world.attribute.MAX_BUILD_HEIGHT and not held.is_empty() and callable(target_block):
            block = target_block()
            if isinstance(packet.get('nbt'), dict):
                apply_placement_nbt = getattr(block, 'apply_placement_nbt', None)
                if callable(apply_placement_nbt):
                    try:
                        apply_placement_nbt(packet['nbt'])
                    except (TypeError, ValueError):
                        return
            # Ignore the client-provided block id; the selected server slot is
            # the only authority for what can be placed.
            if block.place_at(Location(world, packet['x'], packet['y'], packet['z'])) is not False:
                if getattr(player.gamemode, 'name_id', 'survival') != 'creative':
                    held.reduce_amount(1)
                player.sync_inventory()

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
        try:
            player.selected_slot = max(0, min(8, int(packet.get('slot'))))
        except (TypeError, ValueError):
            pass
        player.sync_inventory()
    elif packet['__class__'] == 'ConsumeItem':
        held = player.inventory[player.selected_slot]
        food = int(getattr(held.material, 'food_value', 0))
        if food > 0 and player.food_level < 20 and not held.is_empty():
            saturation = float(getattr(held.material, 'saturation_modifier', 0.0))
            player.food_level = min(20, player.food_level + food)
            player.saturation = min(float(player.food_level), player.saturation + food * saturation * 2)
            held.reduce_amount(1)
        player.sync_inventory()
    elif packet['__class__'] == 'RequestRespawn':
        player.health = player.max_health
        player.food_level = 20
        player.saturation = 5.0
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


