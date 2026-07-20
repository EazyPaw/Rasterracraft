import logging
from typing import TYPE_CHECKING

from resources.client.client_player import ClientPlayer
from resources.client.game_mode import get_gamemode_by_id
from resources.server.block_class import Block
from resources.server.blocks import get_block_by_id
from resources.server.inventory import payload_to_stack, restore_inventory
from resources.server.location import Location
from resources.server.text import Text

if TYPE_CHECKING:
    from resources.client.client_main import Client


def _set_inventory_cursor(client: 'Client', cursor) -> None:
    player = client.client_player
    if player is None:
        return
    player.inventory_cursor = cursor
    candidates = list(getattr(client.render, 'drawing_GUIs', []))
    game_mode = getattr(player, 'game_mode', None)
    if game_mode is not None:
        candidates.extend(value for value in vars(game_mode).values() if hasattr(value, 'dragging_item'))
    for gui in candidates:
        if hasattr(gui, 'dragging_item'):
            gui.dragging_item = cursor


def _set_crafting_grid(client: 'Client', payload) -> None:
    player = client.client_player
    if player is None:
        return
    game_mode = getattr(player, 'game_mode', None)
    if game_mode is None:
        return
    for gui in vars(game_mode).values():
        if hasattr(gui, 'crafting_slots'):
            restore_inventory(gui.crafting_slots, payload)
            refresh = getattr(gui, '_refresh_crafting', None)
            if refresh is not None:
                refresh()


def decode_packet(packet: dict, client: 'Client') -> None:
    """
    将服务器数据包转化为相应对象并执行对应操作
    """
    if '__class__' not in packet:
        logging.warning("Received unknown packet")
        return
    elif packet['__class__'] == 'Disconnect':
        reason = packet.get('reason', '')
        if packet.get('reason_is_translation_key') and isinstance(reason, str):
            reason = client.resources_manager.get_translation_key(reason)
        elif isinstance(reason, dict):
            try:
                reason = Text.from_dict(reason)
            except (KeyError, TypeError, ValueError):
                logging.warning("Received malformed disconnect reason")
                reason = client.resources_manager.get_translation_key("disconnect.closed")
        elif not isinstance(reason, str):
            reason = str(reason)
        # Confirm receipt before show_disconnect clears socket_connected. The
        # server waits for this acknowledgement instead of closing immediately,
        # which avoids Windows turning the close into a TCP reset that can race
        # ahead of the Disconnect frame.
        client.sent_packet({'__class__': 'DisconnectAck'})
        client.show_disconnect("disconnect.disconnected", reason)
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
        #     "biome_array": {"x,y": str}
        # }
        # 通过线程池异步加载，避免频繁创建/销毁线程，同时限制并发数
        pool = client.chunk_load_pool
        load_version = client.client_world.begin_chunk_load(packet['x'])
        pool.submit(client.client_world.load_chunk_packet, packet, load_version)

    elif packet['__class__'] == 'Teleport':
        # {
        #     '__class__': 'Teleport',
        #     'x': obj.x,
        #     'y': obj.y,
        # }
        client.server_player_uuid = packet.get('uuid', getattr(client, "server_player_uuid", None))
        if packet.get('name') and client.client_player is not None:
            client.client_player.name = packet['name']
        client.client_player.x = packet['x']
        client.client_player.y = packet['y']
        # Teleports replace the local physics state as well as the position.
        # In particular, a player who died while falling must not carry the
        # old downward velocity into the respawn position.
        client.client_player.motion.x = 0
        client.client_player.motion.y = 0
        if client.client_player is not None:
            for key in (
                'health', 'hurt_time', 'last_hurt_damage', 'food_level',
                'saturation', 'experience', 'experience_level',
            ):
                if key in packet:
                    setattr(client.client_player, key, packet[key])
            if 'inventory' in packet:
                restore_inventory(client.client_player.inventory, packet['inventory'])
            if 'crafting' in packet:
                _set_crafting_grid(client, packet['crafting'])
            if 'cursor' in packet:
                cursor = payload_to_stack(packet['cursor'])
                _set_inventory_cursor(client, cursor)
            if 'selected_slot' in packet:
                try:
                    client.client_player.selected_slot = max(0, min(8, int(packet['selected_slot'])))
                except (TypeError, ValueError):
                    client.client_player.selected_slot = 0
            client.client_player.dead = False
            client.close_death_screen()
        # Do not acknowledge until the destination and its immediate neighbours
        # are fully installed.  This is the actual client-ready handshake; a
        # received TCP packet alone does not mean collision data is usable yet.
        teleport_id = packet.get('teleport_id')
        client.handle_server_teleport(teleport_id)
    elif packet['__class__'] == 'BreakBlock':
        # {
        #     '__class__': 'BreakBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        # }
        world = client.client_world
        if 0 <= packet['y'] < world.y_max:
            world.clear_break_progress_at(packet['x'], packet['y'], packet['z'])
            world.break_block(packet['x'], packet['y'], packet['z'])
            game_mode = getattr(getattr(client, 'client_player', None), 'game_mode', None)
            handle_result = getattr(game_mode, 'handle_break_result', None)
            if callable(handle_result):
                handle_result(int(packet['x']), int(packet['y']), int(packet['z']))
    elif packet['__class__'] == 'BlockBreakProgress':
        if str(packet.get('miner_uuid', '')) != str(getattr(client, 'server_player_uuid', '')):
            client.client_world.update_break_progress(packet)
    elif packet['__class__'] == 'BlockBreakCorrection':
        world = client.client_world
        try:
            x, y, z = int(packet['x']), int(packet['y']), int(packet['z'])
            block_data = packet['block_data']
            block = get_block_by_id(block_data['id'])
            if isinstance(block_data.get('nbt'), dict):
                block.write_nbt(block_data['nbt'])
        except (KeyError, TypeError, ValueError):
            return
        world.set_block(block, x, y, z)
        world.clear_break_progress_at(x, y, z)
        game_mode = getattr(getattr(client, 'client_player', None), 'game_mode', None)
        handle_result = getattr(game_mode, 'handle_break_result', None)
        if callable(handle_result):
            handle_result(x, y, z)
    elif packet['__class__'] == 'PlaceBlock':
        # {
        #     '__class__': 'PlaceBlock',
        #     'x': location.x,
        #     'y': location.y,
        #     'z': location.z,
        #     'block_id': obj.block_id,
        #     'nbt': optional placement state (e.g. torch facing),
        # }
        world = client.client_world
        if 0 <= packet['y'] < world.y_max:
            block = get_block_by_id(packet['block_id'])
            if isinstance(packet.get('nbt'), dict):
                block.write_nbt(packet['nbt'])
            world.set_block(block, packet['x'], packet['y'], packet['z'])
    elif packet['__class__'] == 'BlockUpdate':
        # {
        #     '__class__': 'BlockUpdate',
        #     'x': int,
        #     'y': int,
        #     'z': int,
        #     'block_data': {'id': str, 'nbt': dict (可选)},
        # }
        world = client.client_world
        x, y, z = packet['x'], packet['y'], packet['z']
        if 0 <= y < world.y_max:
            previous = world.get_block(x, y, z)
            block_data = packet['block_data']
            block = get_block_by_id(block_data['id'])
            if 'nbt' in block_data:
                block.write_nbt(block_data['nbt'])
            world.set_block(block, x, y, z)
            world.clear_break_progress_at(x, y, z)
            game_mode = getattr(getattr(client, 'client_player', None), 'game_mode', None)
            handle_result = getattr(game_mode, 'handle_break_result', None)
            if callable(handle_result):
                handle_result(int(x), int(y), int(z))
            if (
                getattr(previous, 'block_id', None) == 'lava'
                and getattr(block, 'block_id', None) in {'stone', 'cobblestone', 'obsidian'}
            ):
                world.play_sound('random.fizz', x + 0.5, y + 0.5, z, volume=0.8)
    elif packet['__class__'] == 'LightUpdate':
        # {
        #     '__class__': 'LightUpdate',
        #     'rx': chunk_x,
        #     'light_array': {"x,y": int}
        # }
        client.client_world.update_lights(
            packet['rx'],
            packet['light_array'],
            packet.get('sky_light_array'),
            packet.get('block_light_array'),
        )
    elif packet['__class__'] == 'BiomeUpdate':
        # {
        #     '__class__': 'BiomeUpdate',
        #     'rx': chunk_x,
        #     'biome_array': {"x,y": str}
        # }
        if 'rx' in packet and 'biome_array' in packet:
            client.client_world.update_biomes(packet['rx'], packet['biome_array'])
    elif packet['__class__'] == 'UnloadChunk':
        if 'rx' in packet:
            client.client_world.unload_chunk(packet['rx'])
    elif packet['__class__'] == 'TimeUpdate':
        client.client_world.world_time = packet.get('time', 0) % 24000
    elif packet['__class__'] == 'WorldLoadStart':
        client.handle_initial_world_start(packet.get('regions', []))
    elif packet['__class__'] == 'WorldLoadComplete':
        client.handle_initial_world_complete(packet.get('regions', []))
    elif packet['__class__'] == 'WeatherUpdate':
        weather = str(packet.get('weather', 'clear')).lower()
        client.client_world.weather = weather if weather in ('clear', 'rain') else 'clear'
        client.client_world.weather_remaining_ticks = max(0, int(packet.get('remaining_ticks', 0)))
    elif packet['__class__'] == 'Particle':
        client.particle_manager.handle_packet(packet)
    elif packet['__class__'] == 'SoundEffect':
        sound_id = packet.get('sound_id', '')
        volume = float(packet.get('volume', 1.0))
        if packet.get('global', False):
            client.resources_manager.play_sound(sound_id, volume=volume)
        else:
            client.client_world.play_sound(
                sound_id,
                float(packet.get('x', 0.0)),
                float(packet.get('y', 0.0)),
                float(packet.get('z', 0.0)),
                volume=volume,
            )
    elif packet['__class__'] == 'InventoryUpdate':
        player = client.client_player
        if player is not None:
            restore_inventory(player.inventory, packet.get('inventory', []))
            _set_crafting_grid(client, packet.get('crafting', []))
            for key in ('health', 'food_level', 'saturation'):
                if key in packet:
                    setattr(player, key, packet[key])
            try:
                player.selected_slot = max(0, min(8, int(packet.get('selected_slot', 0))))
            except (TypeError, ValueError):
                player.selected_slot = 0
            cursor = payload_to_stack(packet.get('cursor', {}))
            _set_inventory_cursor(client, cursor)
    elif packet['__class__'] == 'PlayerHurt':
        player = client.client_player
        if player is not None:
            player.health = max(0.0, min(player.max_health, float(packet.get('health', player.health))))
            player.hurt_time = max(player.hurt_time, int(packet.get('hurt_time', player.HURT_FLASH_TICKS)))
            player.last_hurt_damage = float(packet.get('last_hurt_damage', player.last_hurt_damage))
            motion = packet.get('motion', {})
            player.motion.x = float(motion.get('x', player.motion.x))
            player.motion.y = float(motion.get('y', player.motion.y))
            if player.health <= 0:
                client.show_death_screen(packet.get('death_message'))
    elif packet['__class__'] == 'PlayerVelocity':
        player = client.client_player
        if player is not None:
            motion = packet.get('motion', {})
            player.motion.x = float(motion.get('x', player.motion.x))
            player.motion.y = float(motion.get('y', player.motion.y))
    elif packet['__class__'] == 'Experience':
        if client.client_player is not None:
            client.client_player.add_experience(int(packet.get('amount', 0)))
    elif packet['__class__'] in ('EntitySpawn', 'EntityUpdate'):
        client.client_world.update_entity(packet)
    elif packet['__class__'] == 'EntityRemove':
        client.client_world.remove_entity(packet.get('uuid', ''))
    elif packet['__class__'] == 'ChatMessage':
        # {
        #     '__class__': 'ChatMessage',
        #     'text': 'formatted message text',
        #     'color': [r, g, b],  # 可选颜色
        # }
        text_payload = packet.get('text', '')
        if isinstance(text_payload, dict):
            try:
                text_payload = Text.from_dict(text_payload)
            except (KeyError, TypeError, ValueError):
                logging.warning("Received malformed formatted chat message")
                text_payload = ''
        elif isinstance(text_payload, list):
            try:
                text_payload = Text.from_dict({'text': text_payload})
            except (KeyError, TypeError, ValueError):
                logging.warning("Received malformed formatted chat message")
                text_payload = ''

        color_raw = packet.get('color', [255, 255, 255])
        color = tuple(color_raw) if isinstance(color_raw, list) else color_raw
        client.add_chat_message(text_payload, color)
    elif packet['__class__'] == 'SaveComplete':
        if hasattr(client, "save_complete_event"):
            client.save_complete_event.set()
    elif packet['__class__'] == 'GamemodeUpdate':
        if client.client_player is None:
            return
        gamemode_type = get_gamemode_by_id(packet['new_mode'])
        client.client_player.game_mode = gamemode_type(client.client_player)
        # Mouse and keyboard callbacks store bound methods, so changing only
        # game_mode would leave them pointing at the old SurvivalMode object.
        client._install_game_controls()
        # GameMode.update_gui rebuilds the GUI list.  During the initial join it
        # must not accidentally discard the still-active loading screen.
        if client.loading_screen is not None:
            client.render.show_gui(client.loading_screen)
    # logging.debug(f"Received {packet['__class__']} packet.")

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
            'sneaking': obj.sneaking,
            'sprinting': obj.sprinting,
            'facing': obj.facing,
            'on_ground': obj.on_ground,
            'flying': obj.flying,
            'look_angle': obj.look_angle,
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
        packet = {
            '__class__': 'PlaceBlock',
            'x': location.x,
            'y': location.y,
            'z': location.z,
            'block_id': obj.block_id,
        }
        nbt = obj.parse_nbt()
        if nbt:
            packet['nbt'] = nbt
        return packet
    elif isinstance(obj, dict) and '__class__' in obj:
        # 直传已构建好的数据包（如 ChatMessage）
        return obj
    logging.warning("Unknown packet to encode")
    logging.debug(f"Encoding{type(obj)},{obj_type} packet.")
    return {}
