# Commented and arranged by ChatGPT
import logging
from typing import TYPE_CHECKING

from src.client.client_player import ClientPlayer
from src.client.game_mode import get_gamemode_by_id
from src.server.block_class import Block
from src.server.blocks import get_block_by_id
from src.server.inventory import payload_to_stack, restore_inventory
from src.server.location import Location
from src.server.text import Text
from src.server.status_effects import StatusEffectInstance, get_status_effect
from src.protocol import (
    CLIENTBOUND,
    SERVERBOUND,
    Packet,
    PacketDecodeError,
    PacketDispatcher,
    encode_payload,
    make_packet,
)

if TYPE_CHECKING:
    from src.client.client_main import Client


def _set_inventory_cursor(client: "Client", cursor) -> None:
    player = client.client_player
    if player is None:
        return
    player.inventory_cursor = cursor
    candidates = list(getattr(client.render, "drawing_GUIs", []))
    game_mode = getattr(player, "game_mode", None)
    if game_mode is not None:
        candidates.extend(
            value
            for value in vars(game_mode).values()
            if hasattr(value, "dragging_item")
        )
    for gui in candidates:
        if hasattr(gui, "dragging_item"):
            gui.dragging_item = cursor


def _set_crafting_grid(client: "Client", payload) -> None:
    player = client.client_player
    if player is None:
        return
    game_mode = getattr(player, "game_mode", None)
    if game_mode is None:
        return
    for gui in vars(game_mode).values():
        if hasattr(gui, "crafting_slots"):
            restore_inventory(gui.crafting_slots, payload)
            refresh = getattr(gui, "_refresh_crafting", None)
            if refresh is not None:
                refresh()


def _set_equipment(player, payload) -> None:
    if not isinstance(payload, dict):
        return
    for slot in ("offhand", "head", "chest", "legs", "feet"):
        if slot in payload:
            player.equipment[slot] = payload_to_stack(payload[slot])


def _apply_local_attribute_snapshot(player, payload) -> None:
    # Snapshot application removes and re-adds modifiers. Preserve absorption
    # across that transient max_absorption=0 state, then clamp once atomically.
    absorption_amount = max(0.0, float(getattr(player, "absorption_amount", 0.0)))
    player.attributes.apply_sync_snapshot(payload)
    try:
        maximum_absorption = player.get_attribute_value("max_absorption")
    except (AttributeError, KeyError, TypeError, ValueError):
        maximum_absorption = 0.0
    player.absorption_amount = min(absorption_amount, maximum_absorption)
    reconcile = getattr(
        getattr(player, "game_mode", None),
        "reconcile_attribute_predictions",
        None,
    )
    if callable(reconcile):
        reconcile()


def _apply_effect_snapshot(entity, payload) -> None:
    effects = {}
    if isinstance(payload, list):
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            try:
                instance = StatusEffectInstance.from_dict(entry)
            except (TypeError, ValueError):
                continue
            effect = get_status_effect(instance.effect_id)
            if effect is not None and instance.duration != 0:
                effects[effect.id] = instance
    entity.active_effects = effects


CLIENT_PACKET_DISPATCHER = PacketDispatcher["Client"](CLIENTBOUND)


def decode_packet(packet: dict, client: "Client") -> None:
    """Validate and dispatch one server-to-client packet."""
    try:
        CLIENT_PACKET_DISPATCHER.dispatch(packet, client)
    except PacketDecodeError as exc:
        logging.warning("Rejected clientbound packet: %s", exc)


@CLIENT_PACKET_DISPATCHER.handler("Disconnect")
def _handle_disconnect(packet: dict, client: "Client") -> None:
    reason = packet.get("reason", "")
    if packet.get("reason_is_translation_key") and isinstance(reason, str):
        reason = client.resources_manager.get_translation_key(reason)
    elif isinstance(reason, dict):
        try:
            reason = Text.from_dict(reason)
        except (KeyError, TypeError, ValueError):
            logging.warning("Received malformed disconnect reason")
            reason = client.resources_manager.get_translation_key(
                "disconnect.closed"
            )
    elif not isinstance(reason, str):
        reason = str(reason)

    client.sent_packet(make_packet("DisconnectAck"))
    client.show_disconnect("disconnect.disconnected", reason)


@CLIENT_PACKET_DISPATCHER.handler("Chunk")
def _handle_chunk(packet: dict, client: "Client") -> None:
    pool = client.chunk_load_pool
    load_version = client.client_world.begin_chunk_load(packet["x"])
    pool.submit(client.client_world.load_chunk_packet, packet, load_version)


@CLIENT_PACKET_DISPATCHER.handler("Teleport")
def _handle_teleport(packet: dict, client: "Client") -> None:
    client.server_player_uuid = packet.get(
        "uuid", getattr(client, "server_player_uuid", None)
    )
    if packet.get("name") and client.client_player is not None:
        client.client_player.name = packet["name"]
    client.client_player.x = packet["x"]
    client.client_player.y = packet["y"]
    client.client_player.blocking = bool(packet.get("blocking", False))
    apply_bow_state = getattr(
        client.client_player.game_mode, "apply_server_bow_state", None
    )
    using_bow = bool(packet.get("using_bow", False))
    bow_draw_ticks = max(0, int(packet.get("bow_draw_ticks", 0)))
    if callable(apply_bow_state):
        apply_bow_state(using_bow, bow_draw_ticks)
    else:
        client.client_player.using_bow = using_bow
        client.client_player.bow_draw_ticks = bow_draw_ticks
    client.client_player.sleeping = bool(packet.get("sleeping", False))
    client.client_player.sleeping_bed = packet.get("sleeping_bed")

    client.client_player.motion.x = 0
    client.client_player.motion.y = 0
    if client.client_player is not None:
        for key in (
            "health",
            "absorption_amount",
            "hurt_time",
            "last_hurt_damage",
            "food_level",
            "saturation",
            "experience",
            "experience_level",
            "experience_total",
            "score",
        ):
            if key in packet:
                setattr(client.client_player, key, packet[key])
        if "inventory" in packet:
            restore_inventory(client.client_player.inventory, packet["inventory"])
        _set_equipment(client.client_player, packet.get("equipment"))
        if "crafting" in packet:
            _set_crafting_grid(client, packet["crafting"])
        if "cursor" in packet:
            cursor = payload_to_stack(packet["cursor"])
            _set_inventory_cursor(client, cursor)
        if "selected_slot" in packet:
            try:
                client.client_player.selected_slot = max(
                    0, min(8, int(packet["selected_slot"]))
                )
            except (TypeError, ValueError):
                client.client_player.selected_slot = 0
        if "attributes" in packet:
            _apply_local_attribute_snapshot(
                client.client_player, packet["attributes"]
            )
        _apply_effect_snapshot(
            client.client_player, packet.get("active_effects", [])
        )
        client.client_player.dead = False
        client.close_death_screen()

    teleport_id = packet.get("teleport_id")
    client.handle_server_teleport(teleport_id)


def _notify_break_result(client: "Client", x: int, y: int, z: int) -> None:
    game_mode = getattr(getattr(client, "client_player", None), "game_mode", None)
    handle_result = getattr(game_mode, "handle_break_result", None)
    if callable(handle_result):
        handle_result(int(x), int(y), int(z))


@CLIENT_PACKET_DISPATCHER.handler("BreakBlock")
def _handle_break_block(packet: dict, client: "Client") -> None:
    world = client.client_world
    if 0 <= packet["y"] < world.y_max:
        world.clear_break_progress_at(packet["x"], packet["y"], packet["z"])
        world.break_block(packet["x"], packet["y"], packet["z"])
        _notify_break_result(client, packet["x"], packet["y"], packet["z"])


@CLIENT_PACKET_DISPATCHER.handler("BlockBreakProgress")
def _handle_block_break_progress(packet: dict, client: "Client") -> None:
    if str(packet.get("miner_uuid", "")) != str(
        getattr(client, "server_player_uuid", "")
    ):
        client.client_world.update_break_progress(packet)


@CLIENT_PACKET_DISPATCHER.handler("BlockBreakCorrection")
def _handle_block_break_correction(packet: dict, client: "Client") -> None:
    world = client.client_world
    try:
        x, y, z = int(packet["x"]), int(packet["y"]), int(packet["z"])
        block_data = packet["block_data"]
        block = get_block_by_id(block_data["id"])
        if isinstance(block_data.get("nbt"), dict):
            block.write_nbt(block_data["nbt"])
    except (KeyError, TypeError, ValueError):
        return
    world.set_block(block, x, y, z)
    world.clear_break_progress_at(x, y, z)
    _notify_break_result(client, x, y, z)


@CLIENT_PACKET_DISPATCHER.handler("BlockUpdate")
def _handle_block_update(packet: dict, client: "Client") -> None:
    world = client.client_world
    x, y, z = packet["x"], packet["y"], packet["z"]
    if 0 <= y < world.y_max:
        previous = world.get_block(x, y, z)
        block_data = packet["block_data"]
        block = get_block_by_id(block_data["id"])
        if "nbt" in block_data:
            block.write_nbt(block_data["nbt"])
        world.set_block(block, x, y, z)
        world.clear_break_progress_at(x, y, z)
        _notify_break_result(client, x, y, z)
        if getattr(previous, "block_id", None) == "lava" and getattr(
            block, "block_id", None
        ) in {"stone", "cobblestone", "obsidian"}:
            world.play_sound("random.fizz", x + 0.5, y + 0.5, z, volume=0.8)


@CLIENT_PACKET_DISPATCHER.handler("LightUpdate")
def _handle_light_update(packet: dict, client: "Client") -> None:
    if packet.get("format") == 2:
        client.client_world.update_lights_compact(
            packet["rx"], packet["height"], packet["sky_light"], packet["block_light"]
        )
        return
    client.client_world.update_lights(
        packet["rx"],
        packet["light_array"],
        packet.get("sky_light_array"),
        packet.get("block_light_array"),
    )


@CLIENT_PACKET_DISPATCHER.handler("BiomeUpdate")
def _handle_biome_update(packet: dict, client: "Client") -> None:
    client.client_world.update_biomes(packet["rx"], packet["biome_array"])


@CLIENT_PACKET_DISPATCHER.handler("UnloadChunk")
def _handle_unload_chunk(packet: dict, client: "Client") -> None:
    client.client_world.unload_chunk(packet["rx"])


@CLIENT_PACKET_DISPATCHER.handler("TimeUpdate")
def _handle_time_update(packet: dict, client: "Client") -> None:
    client.client_world.world_time = packet["time"] % 24000


@CLIENT_PACKET_DISPATCHER.handler("WorldLoadStart")
def _handle_world_load_start(packet: dict, client: "Client") -> None:
    client.handle_initial_world_start(packet["regions"])


@CLIENT_PACKET_DISPATCHER.handler("WorldLoadComplete")
def _handle_world_load_complete(packet: dict, client: "Client") -> None:
    client.handle_initial_world_complete(packet["regions"])


@CLIENT_PACKET_DISPATCHER.handler("WeatherUpdate")
def _handle_weather_update(packet: dict, client: "Client") -> None:
    weather = str(packet.get("weather", "clear")).lower()
    client.client_world.weather = weather if weather in ("clear", "rain") else "clear"
    client.client_world.weather_remaining_ticks = max(
        0, int(packet.get("remaining_ticks", 0))
    )


@CLIENT_PACKET_DISPATCHER.handler("Particle")
def _handle_particle(packet: dict, client: "Client") -> None:
    client.particle_manager.handle_packet(packet)


@CLIENT_PACKET_DISPATCHER.handler("SoundEffect")
def _handle_sound_effect(packet: dict, client: "Client") -> None:
    sound_id = packet.get("sound_id", "")
    volume = float(packet.get("volume", 1.0))
    if packet.get("global", False):
        client.resources_manager.play_sound(sound_id, volume=volume)
    else:
        client.client_world.play_sound(
            sound_id,
            float(packet.get("x", 0.0)),
            float(packet.get("y", 0.0)),
            float(packet.get("z", 0.0)),
            volume=volume,
        )


@CLIENT_PACKET_DISPATCHER.handler("InventoryUpdate")
def _handle_inventory_update(packet: dict, client: "Client") -> None:
    player = client.client_player
    if player is not None:
        restore_inventory(player.inventory, packet.get("inventory", []))
        _set_equipment(player, packet.get("equipment"))
        _set_crafting_grid(client, packet.get("crafting", []))
        for key in (
            "health",
            "absorption_amount",
            "food_level",
            "saturation",
        ):
            if key in packet:
                setattr(player, key, packet[key])
        player.blocking = bool(packet.get("blocking", False))
        apply_bow_state = getattr(player.game_mode, "apply_server_bow_state", None)
        using_bow = bool(packet.get("using_bow", False))
        bow_draw_ticks = max(0, int(packet.get("bow_draw_ticks", 0)))
        if callable(apply_bow_state):
            apply_bow_state(using_bow, bow_draw_ticks)
        else:
            player.using_bow = using_bow
            player.bow_draw_ticks = bow_draw_ticks
        try:
            player.selected_slot = max(
                0, min(8, int(packet.get("selected_slot", 0)))
            )
        except (TypeError, ValueError):
            player.selected_slot = 0
        cursor = payload_to_stack(packet.get("cursor", {}))
        _set_inventory_cursor(client, cursor)
        if "attributes" in packet:
            _apply_local_attribute_snapshot(player, packet["attributes"])
        _apply_effect_snapshot(player, packet.get("active_effects", []))


def _furnace_type():
    from src.client.GUI.inventory.furnace import Furnace

    return Furnace


def _close_block_container_guis(client: "Client") -> None:
    container_types = (_furnace_type(), _chest_type())
    for gui in list(client.render.drawing_GUIs):
        if isinstance(gui, container_types):
            gui._server_closed = True
            client.render.close_gui(gui)


@CLIENT_PACKET_DISPATCHER.handler("FurnaceOpen")
def _handle_furnace_open(packet: dict, client: "Client") -> None:
    furnace_type = _furnace_type()
    _close_block_container_guis(client)
    client.render.show_gui(furnace_type(client.render, packet))


@CLIENT_PACKET_DISPATCHER.handler("FurnaceUpdate")
def _handle_furnace_update(packet: dict, client: "Client") -> None:
    furnace_type = _furnace_type()
    for gui in list(client.render.drawing_GUIs):
        if isinstance(gui, furnace_type) and gui.container_id == str(
            packet.get("container", "")
        ):
            gui.apply_update(packet)


@CLIENT_PACKET_DISPATCHER.handler("FurnaceClosed")
def _handle_furnace_closed(packet: dict, client: "Client") -> None:
    furnace_type = _furnace_type()
    for gui in list(client.render.drawing_GUIs):
        if isinstance(gui, furnace_type) and gui.container_id == str(
            packet.get("container", "")
        ):
            gui._server_closed = True
            client.render.close_gui(gui)


def _chest_type():
    from src.client.GUI.inventory.chest import Chest

    return Chest


@CLIENT_PACKET_DISPATCHER.handler("ChestOpen")
def _handle_chest_open(packet: dict, client: "Client") -> None:
    chest_type = _chest_type()
    _close_block_container_guis(client)
    client.render.show_gui(chest_type(client.render, packet))


@CLIENT_PACKET_DISPATCHER.handler("ChestUpdate")
def _handle_chest_update(packet: dict, client: "Client") -> None:
    chest_type = _chest_type()
    for gui in list(client.render.drawing_GUIs):
        if isinstance(gui, chest_type) and gui.container_id == str(
            packet.get("container", "")
        ):
            gui.apply_update(packet)


@CLIENT_PACKET_DISPATCHER.handler("ChestClosed")
def _handle_chest_closed(packet: dict, client: "Client") -> None:
    chest_type = _chest_type()
    for gui in list(client.render.drawing_GUIs):
        if isinstance(gui, chest_type) and gui.container_id == str(
            packet.get("container", "")
        ):
            gui._server_closed = True
            client.render.close_gui(gui)


@CLIENT_PACKET_DISPATCHER.handler("CraftingTableOpen")
def _handle_crafting_table_open(packet: dict, client: "Client") -> None:
    player = client.client_player
    game_mode = getattr(player, "game_mode", None)
    gui = getattr(game_mode, "crafting_table", None)
    if gui is not None and gui not in client.render.drawing_GUIs:
        client.render.show_gui(gui)


@CLIENT_PACKET_DISPATCHER.handler("PlayerHurt")
def _handle_player_hurt(packet: dict, client: "Client") -> None:
    player = client.client_player
    if player is not None:
        player.health = max(
            0.0, min(player.max_health, float(packet.get("health", player.health)))
        )
        player.absorption_amount = max(
            0.0,
            float(packet.get("absorption_amount", player.absorption_amount)),
        )
        player.hurt_time = max(
            player.hurt_time, int(packet.get("hurt_time", player.HURT_FLASH_TICKS))
        )
        player.last_hurt_damage = float(
            packet.get("last_hurt_damage", player.last_hurt_damage)
        )
        motion = packet.get("motion", {})
        player.motion.x = float(motion.get("x", player.motion.x))
        player.motion.y = float(motion.get("y", player.motion.y))
        if player.health <= 0:
            client.show_death_screen(
                packet.get("death_message"),
                score=int(packet.get("score", getattr(player, "score", 0))),
            )


@CLIENT_PACKET_DISPATCHER.handler("AttributeUpdate")
def _handle_attribute_update(packet: dict, client: "Client") -> None:
    player = client.client_player
    target_uuid = str(packet.get("uuid", ""))
    if player is not None and target_uuid in {
        "",
        str(player.uuid),
        str(getattr(client, "server_player_uuid", "")),
    }:
        _apply_local_attribute_snapshot(player, packet.get("attributes", []))
    else:
        entity = client.client_world.entities.get(target_uuid)
        if entity is not None:
            entity.attributes.apply_sync_snapshot(packet.get("attributes", []))
            entity.max_health = float(packet.get("max_health", entity.max_health))


@CLIENT_PACKET_DISPATCHER.handler("EffectUpdate")
def _handle_effect_update(packet: dict, client: "Client") -> None:
    player = client.client_player
    target_uuid = str(packet.get("uuid", ""))
    if player is not None and target_uuid in {
        "",
        str(player.uuid),
        str(getattr(client, "server_player_uuid", "")),
    }:
        _apply_effect_snapshot(player, packet.get("active_effects", []))
        if "attributes" in packet:
            _apply_local_attribute_snapshot(player, packet["attributes"])
        player.health = max(
            0.0, min(player.max_health, float(packet.get("health", player.health)))
        )
        player.absorption_amount = max(
            0.0,
            float(packet.get("absorption_amount", player.absorption_amount)),
        )


@CLIENT_PACKET_DISPATCHER.handler("PlayerVelocity")
def _handle_player_velocity(packet: dict, client: "Client") -> None:
    player = client.client_player
    if player is not None:
        motion = packet.get("motion", {})
        player.motion.x = float(motion.get("x", player.motion.x))
        player.motion.y = float(motion.get("y", player.motion.y))
        if "sprinting" in packet:
            player.sprinting = packet.get("sprinting") is True


@CLIENT_PACKET_DISPATCHER.handler("Experience")
def _handle_experience(packet: dict, client: "Client") -> None:
    if client.client_player is not None:
        player = client.client_player
        if "experience" in packet and "experience_level" in packet:
            player.experience = max(0, int(packet["experience"]))
            player.experience_level = max(0, int(packet["experience_level"]))
            player.experience_total = max(
                0, int(packet.get("experience_total", player.experience_total))
            )
            player.score = max(0, int(packet.get("score", player.score)))
        else:
            player.add_experience(int(packet.get("amount", 0)))


@CLIENT_PACKET_DISPATCHER.handler("EntitySpawn")
@CLIENT_PACKET_DISPATCHER.handler("EntityUpdate")
def _handle_entity_update(packet: dict, client: "Client") -> None:
    client.client_world.update_entity(packet)


@CLIENT_PACKET_DISPATCHER.handler("EntityRemove")
def _handle_entity_remove(packet: dict, client: "Client") -> None:
    client.client_world.remove_entity(packet.get("uuid", ""))


@CLIENT_PACKET_DISPATCHER.handler("ChatMessage")
def _handle_chat_message(packet: dict, client: "Client") -> None:
    text_payload = packet.get("text", "")
    if isinstance(text_payload, dict):
        try:
            text_payload = Text.from_dict(text_payload)
        except (KeyError, TypeError, ValueError):
            logging.warning("Received malformed formatted chat message")
            text_payload = ""
    elif isinstance(text_payload, list):
        try:
            text_payload = Text.from_dict({"text": text_payload})
        except (KeyError, TypeError, ValueError):
            logging.warning("Received malformed formatted chat message")
            text_payload = ""

    color_raw = packet.get("color", [255, 255, 255])
    color = tuple(color_raw) if isinstance(color_raw, list) else color_raw
    client.add_chat_message(text_payload, color)


@CLIENT_PACKET_DISPATCHER.handler("SaveComplete")
def _handle_save_complete(packet: dict, client: "Client") -> None:
    if hasattr(client, "save_complete_event"):
        client.save_complete_event.set()


@CLIENT_PACKET_DISPATCHER.handler("GamemodeUpdate")
def _handle_gamemode_update(packet: dict, client: "Client") -> None:
    if client.client_player is None:
        return
    gamemode_type = get_gamemode_by_id(packet["new_mode"])
    client.client_player.game_mode = gamemode_type(client.client_player)

    client._install_game_controls()

    if client.loading_screen is not None:
        client.render.show_gui(client.loading_screen)


@CLIENT_PACKET_DISPATCHER.handler("StructureBuildState")
def _handle_structure_build_state(packet: dict, client: "Client") -> None:
    client.structure_build_mode = packet.get("mode") is True
    bounds = packet.get("bounds")
    if isinstance(bounds, (list, tuple)) and len(bounds) == 4:
        try:
            client.structure_bounds = tuple(int(value) for value in bounds)
        except (TypeError, ValueError):
            client.structure_bounds = None
    else:
        client.structure_bounds = None
    def read_cells(key):
        cells = set()
        for value in packet.get(key, ()):
            if not isinstance(value, (list, tuple)) or len(value) != 3:
                continue
            try:
                cells.add(tuple(int(part) for part in value))
            except (TypeError, ValueError):
                continue
        return cells

    if packet.get("full", True):
        client.structure_void_cells = read_cells("void_cells")
    else:
        client.structure_void_cells.update(read_cells("void_add"))
        client.structure_void_cells.difference_update(read_cells("void_remove"))
    if client.structure_build_mode and client.client_player is not None:
        client.client_player.flyable = True
        client.client_player.flying = True


CLIENT_PACKET_DISPATCHER.validate_handlers()


def encode_packet(obj, obj_type=None, args=None) -> dict:
    """Adapt gameplay objects and validate the serverbound contract once."""
    return encode_payload(_encode_packet_object(obj, obj_type, args), SERVERBOUND)


def _encode_packet_object(obj, obj_type=None, args=None) -> Packet | dict:
    """
    将客户端数据包编码为字典发送至服务器
    """
    if args is None:
        args = []
    if type(obj) == ClientPlayer and obj_type == "PlayerMove":
        return {
            "__class__": "PlayerMove",
            "x": obj.x,
            "y": obj.y,
            "sneaking": obj.sneaking,
            "sprinting": obj.sprinting,
            "facing": obj.facing,
            "on_ground": obj.on_ground,
            "flying": obj.flying,
            "look_angle": obj.look_angle,
        }
    elif isinstance(obj, Block) and obj_type == "BreakBlock":
        location: Location = obj.location
        return {
            "__class__": "BreakBlock",
            "x": location.x,
            "y": location.y,
            "z": location.z,
        }
    elif isinstance(obj, Packet):
        return obj
    elif isinstance(obj, dict) and "__class__" in obj:
        # 直传已构建好的数据包（如 ChatMessage）
        return obj
    logging.warning("Unknown packet to encode")
    logging.debug(f"Encoding{type(obj)},{obj_type} packet.")
    return {}
