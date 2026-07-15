import logging
from typing import TYPE_CHECKING

from resources.client.client_player import ClientPlayer
from resources.client.game_mode import get_gamemode_by_id
from resources.server.block_class import Block
from resources.server.blocks import get_block_by_id
from resources.server.item_class import ItemStack
from resources.server.location import Location
from resources.server.materials import get_material_by_id

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
        client.client_player.fall_distance = 0.0
        if client.client_player is not None:
            for key in ('health', 'food_level', 'saturation', 'experience', 'experience_level'):
                if key in packet:
                    setattr(client.client_player, key, packet[key])
            client.client_player.dead = False
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
            block_data = packet['block_data']
            block = get_block_by_id(block_data['id'])
            if 'nbt' in block_data:
                block.write_nbt(block_data['nbt'])
            world.set_block(block, x, y, z)
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
    elif packet['__class__'] == 'ItemPickup':
        player = client.client_player
        item_data = packet.get('item', {})
        if player is not None:
            player.add_item_stack(ItemStack(
                get_material_by_id(item_data.get('id', 'air')),
                int(item_data.get('amount', 1)),
                item_data.get('nbt', {}),
            ))
            player.world.play_sound("random.pop", player.x, player.y, 0)
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
        color_raw = packet.get('color', [255, 255, 255])
        color = tuple(color_raw) if isinstance(color_raw, list) else color_raw
        client.add_chat_message(packet.get('text', ''), color)
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
            'health': obj.health,
            'food_level': obj.food_level,
            'saturation': obj.saturation,
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
    elif isinstance(obj, dict) and '__class__' in obj:
        # 直传已构建好的数据包（如 ChatMessage）
        return obj
    logging.warning("Unknown packet to encode")
    logging.debug(f"Encoding{type(obj)},{obj_type} packet.")
    return {}
