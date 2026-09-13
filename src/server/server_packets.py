# Commented and arranged by ChatGPT
import logging
import math

from src.server.entity import Entity
from src.server.block_class import PlacementContext
from src.server.location import Location
from src.server.inventory import (
    payload_to_stack,
    serialize_inventory,
    stack_to_payload,
)
from src.server.item_class import EmptyItemStack
from src.server.particles import ParticleEffect
from src.server.player import Player
from src.server.world_class import Chunk
from src.server.structure import apply_structure_mask
from src.protocol import (
    CLIENTBOUND,
    SERVERBOUND,
    Packet,
    PacketDecodeError,
    PacketDispatcher,
    decode_payload,
    encode_payload,
    make_packet,
)


def encode_packet(obj, obj_type=None, args=None) -> dict:
    """Adapt gameplay objects and validate the clientbound contract once."""
    return encode_payload(_encode_packet_object(obj, obj_type, args), CLIENTBOUND)


def _encode_packet_object(obj, obj_type, args) -> Packet | dict:
    if args is None:
        args = []
    if isinstance(obj, Packet):
        return obj
    if isinstance(obj, dict) and "__class__" in obj and obj_type in (None, "Forward"):
        return obj
    if type(obj) == Chunk:
        return obj.to_dict()
    elif isinstance(obj, Player) and obj_type == "Teleport":
        obj.refresh_attribute_modifiers()
        packet = {
            "__class__": "Teleport",
            "x": obj.x,
            "y": obj.y,
            "uuid": str(obj.uuid),
            "name": obj.name,
            "health": obj.health,
            "absorption_amount": getattr(obj, "absorption_amount", 0.0),
            "hurt_time": obj.hurt_time,
            "last_hurt_damage": obj.last_hurt_damage,
            "food_level": getattr(obj, "food_level", 20),
            "saturation": getattr(obj, "saturation", 5.0),
            "experience": getattr(obj, "experience", 0),
            "experience_level": getattr(obj, "experience_level", 0),
            "experience_total": getattr(obj, "experience_total", 0),
            "score": getattr(obj, "score", 0),
            "sleeping": bool(getattr(obj, "sleeping", False)),
            "sleeping_bed": getattr(obj, "sleeping_bed", None),
            "selected_slot": getattr(obj, "selected_slot", 0),
            "teleport_id": getattr(obj, "_pending_teleport_id", None),
            "inventory": serialize_inventory(obj.inventory),
            "cursor": stack_to_payload(obj.cursor_stack),
            "equipment": {
                slot: stack_to_payload(stack) for slot, stack in obj.equipment.items()
            },
            "attributes": obj.attributes.sync_snapshot(),
            "active_effects": obj.status_effects_payload(),
        }
        return packet
    elif isinstance(obj, Entity) and obj_type in ("EntitySpawn", "EntityUpdate"):
        packet = obj.to_entity_data()
        packet["__class__"] = obj_type
        return packet
    elif obj_type == "EntityRemove":
        return {
            "__class__": "EntityRemove",
            "uuid": str(obj.uuid) if isinstance(obj, Entity) else str(obj["uuid"]),
        }
    elif isinstance(obj, ParticleEffect):
        return obj.to_packet()
    elif obj_type == "LightUpdate":
        if obj.get("format") == 2:
            return {
                "__class__": "LightUpdate",
                "rx": obj["rx"],
                "format": 2,
                "height": obj["height"],
                "sky_light": obj["sky_light"],
                "block_light": obj["block_light"],
            }

        return {
            "__class__": "LightUpdate",
            "rx": obj["rx"],
            "light_array": obj["light_array"],
            "sky_light_array": obj.get("sky_light_array"),
            "block_light_array": obj.get("block_light_array"),
        }
    elif obj_type == "BiomeUpdate":
        # obj 应该是 {'rx': int, 'biome_array': dict}
        return {
            "__class__": "BiomeUpdate",
            "rx": obj["rx"],
            "biome_array": obj["biome_array"],
        }
    elif obj_type == "UnloadChunk":
        return {
            "__class__": "UnloadChunk",
            "rx": obj["rx"],
        }
    elif isinstance(obj, Location) and obj_type == "BreakBlock":
        return {
            "__class__": "BreakBlock",
            "x": obj.x,
            "y": obj.y,
            "z": obj.z,
        }
    elif obj_type == "BlockUpdate":
        # obj 是 Block 实例，发送单个方块的更新数据
        return {
            "__class__": "BlockUpdate",
            "x": obj.location.x,
            "y": obj.location.y,
            "z": obj.location.z,
            "block_data": obj.to_dict(),
        }
    elif obj_type == "GamemodeUpdate" and isinstance(obj, Player):
        return {"__class__": "GamemodeUpdate", "new_mode": obj.gamemode.name_id}
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
    if not bool(getattr(target, "attackable", True)):
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
    return (
        horizontal_gap * horizontal_gap + vertical_gap * vertical_gap <= reach * reach
    )


def _can_player_reach_block(player: Player, x: int, y: int, z: int) -> bool:
    return player.can_reach_block(x, y, z)


def _read_block_position(packet: dict) -> tuple[int, int, int] | None:
    try:
        values = packet.get("x"), packet.get("y"), packet.get("z")
        if any(isinstance(value, bool) for value in values):
            return None
        numeric = tuple(float(value) for value in values)
        if not all(math.isfinite(value) and value.is_integer() for value in numeric):
            return None
        return tuple(int(value) for value in numeric)
    except (TypeError, ValueError, OverflowError):
        return None


def _read_placement_context(
    packet: dict, player: Player, target_z: int
) -> PlacementContext | None:
    raw = packet.get("context")
    if raw is None:
        return PlacementContext(None, (0.0, 0.0), (0.0, 0.0), target_z, False)
    if not isinstance(raw, dict):
        return None
    hit_face = raw.get("hit_face")
    if hit_face not in (None, "top", "bottom", "left", "right"):
        return None
    try:
        direction = tuple(
            float(value) for value in raw.get("ray_direction", (0.0, 0.0))
        )
        if len(direction) != 2 or not all(math.isfinite(value) for value in direction):
            return None
        reported_target_z = int(raw.get("target_z", target_z))
    except (TypeError, ValueError, OverflowError):
        return None
    if reported_target_z not in (0, 1):
        return None
    eye = (
        float(player.x) + float(player.width) * 0.5,
        float(player.y) + float(getattr(player, "eye_height", player.height * 0.85)),
    )
    return PlacementContext(
        hit_face,
        eye,
        direction,
        # 目标层以服务端读取的方块坐标为准。旧客户端在前景放置模式下
        # 可能上报 0；这里兼容它们，但不让该值改变背景层的射线语义。
        target_z,
        raw.get("fore_place") is True,
    )


def _process_right_click(packet: dict, player: Player) -> None:
    if not _allow_action_this_tick(player, "right_click"):
        return
    if player.health <= 0 or player.sleeping:
        return

    position_keys = ("x", "y", "z")
    has_position = any(key in packet for key in position_keys)
    position = _read_block_position(packet) if has_position else None
    if has_position and position is None:
        return

    player.clear_breaking()
    target = None
    context = None
    if position is not None:
        x, y, z = position
        world = player.world
        position_loaded = (
            0 <= y < world.attribute.MAX_BUILD_HEIGHT
            and z in (0, 1)
            and x // 16 in player.client_loaded_regions
            and world.is_chunk_loaded(x // 16)
        )
        if position_loaded:
            context = _read_placement_context(packet, player, z)
            if context is None:
                return
            target = world.get_block(x, y, z)
            target_is_air = getattr(target, "block_id", "air") == "air"

            # AIR 坐标是方块物品的放置目标，而不是可交互方块。它的最终
            # 距离会在 Player.place_block_item 中按放置位置再次校验。
            if not target_is_air:
                if not _can_player_reach_block(player, x, y, z):
                    return
                held = player.inventory[player.selected_slot]
                item_used_on_block = not held.is_empty() and bool(
                    target.accepts_item_use(held.material)
                )
                handled = bool(target.on_right_click(player))
                if not handled and not held.is_empty():
                    handled = bool(target.on_use(player, held.material))
                    item_used_on_block = handled
                if handled:
                    if item_used_on_block:
                        player.apply_item_event(
                            held, "on_successful_block_use", target
                        )
                    player.clear_eating()
                    player.clear_blocking()
                    player.sync_inventory()
                    player.attack_animation_ticks = max(
                        player.attack_animation_ticks, 6
                    )
                    forward_packet_to_others(
                        player, player, mode="entity_update"
                    )
                    return

    if player.use_held_item(target=target, context=context):
        player.attack_animation_ticks = max(player.attack_animation_ticks, 6)
        forward_packet_to_others(player, player, mode="entity_update")


def _reject_player_move(player: Player) -> None:

    player.teleport_to(player.x, player.y)


def _allow_action_this_tick(player: Player, action: str) -> bool:
    current_tick = int(getattr(player.world.server, "server_ticks", 0))
    action_ticks = getattr(player, "_last_action_ticks", None)
    if action_ticks is None:
        action_ticks = {}
        player._last_action_ticks = action_ticks
    if action_ticks.get(action) == current_tick:
        return False
    action_ticks[action] = current_tick
    return True


SERVER_PACKET_DISPATCHER = PacketDispatcher[Player](SERVERBOUND)


def decode_packet(packet: dict, player: Player) -> None:
    """Validate and dispatch one client-to-server packet."""
    try:
        decoded = decode_payload(packet, SERVERBOUND)
        if getattr(player, "_disconnecting", False) and decoded.name != "DisconnectAck":
            return
        SERVER_PACKET_DISPATCHER.dispatch_packet(decoded, player)
    except PacketDecodeError as exc:
        logging.warning("Rejected serverbound packet: %s", exc)


@SERVER_PACKET_DISPATCHER.handler("DisconnectAck")
def _handle_disconnect_ack(packet: dict, player: Player) -> None:
    player.world.server.acknowledge_disconnect(player)


@SERVER_PACKET_DISPATCHER.handler("PlayerMove")
def _handle_player_move(packet: dict, player: Player) -> None:
    if player.is_awaiting_teleport_confirmation:
        return
    if player.health <= 0:
        return
    if player.sleeping:
        return
    try:
        new_x = float(packet.get("x"))
        new_y = float(packet.get("y"))
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

    current_tick = int(getattr(player.world.server, "server_ticks", 0))
    last_tick = int(getattr(player, "_last_move_tick", -1))
    if last_tick == current_tick:
        return
    elapsed_ticks = 1 if last_tick < 0 else max(1, current_tick - last_tick)
    mode = getattr(getattr(player, "gamemode", None), "name_id", "survival")
    if mode == "creative" and player.flying:
        movement_scale = max(1.0, player.get_attribute_value("flying_speed") / 0.4)
    else:
        movement_scale = max(
            1.0, player.get_attribute_value("movement_speed") / 0.1
        )

    max_horizontal = (
        (4.0 if mode == "creative" else 2.0) * movement_scale * elapsed_ticks
    )
    max_vertical = (6.0 if mode == "creative" else 3.0) * elapsed_ticks
    dx = new_x - player.x
    dy = new_y - player.y
    if abs(dx) > max_horizontal or abs(dy) > max_vertical:
        _reject_player_move(player)
        return

    if player._check_collision_at(new_x, new_y) and not player._check_collision_at(
        player.x, player.y
    ):
        _reject_player_move(player)
        return

    previous_y = player.y
    was_on_ground = bool(player.on_ground)
    player.x = new_x
    player.y = new_y
    player.motion.x = dx
    player.motion.y = dy
    player.sneaking = packet.get("sneaking") is True
    try:
        facing = int(packet.get("facing", player.facing))
    except (TypeError, ValueError):
        facing = player.facing
    if facing in (0, 1):
        player.facing = facing
    try:
        look_angle = float(packet.get("look_angle", player.look_angle))
    except (TypeError, ValueError, OverflowError):
        look_angle = player.look_angle
    if math.isfinite(look_angle):
        player.look_angle = max(-90.0, min(90.0, look_angle))
    movement_opposes_look = abs(dx) > 1.0e-3 and (dx > 0.0) != (
        player.facing == 1
    )
    player.sprinting = (
        not player.blocking
        and not movement_opposes_look
        and packet.get("sprinting") is True
        and (mode != "survival" or player.food_level > 6)
    )
    player.flying = mode == "creative" and packet.get("flying") is True
    player.in_fluid = bool(player._get_fluid_interaction()[0])
    player.on_ground = bool(player._check_support_at())
    player._last_move_tick = current_tick
    player.call_inside_block_hooks()
    player.record_server_movement(previous_y, was_on_ground, abs(dx))
    player.on_moving()
    forward_packet_to_others(player, player, mode="entity_update")


@SERVER_PACKET_DISPATCHER.handler("TeleportConfirm")
def _handle_teleport_confirm(packet: dict, player: Player) -> None:
    player.confirm_teleport(packet.get("teleport_id"))


@SERVER_PACKET_DISPATCHER.handler("ChunkReady")
def _handle_chunk_ready(packet: dict, player: Player) -> None:
    try:
        rx = int(packet.get("rx"))
    except (TypeError, ValueError):
        return
    if rx in player.loading_regions and rx in player.world.regions:
        player.client_loaded_regions.add(rx)


@SERVER_PACKET_DISPATCHER.handler("PlayerAction")
def _handle_player_action(packet: dict, player: Player) -> None:
    if player.sleeping:
        return
    action = packet.get("action")
    if action == "abort_breaking":
        player.clear_breaking()
        return
    if action in {"continue_item_use", "continue_eating"}:
        if player.using_bow:
            player.request_bow_use()
        elif player.blocking:
            player.request_blocking()
        elif player.eating:
            player.request_eating()
        return
    if action in {"stop_item_use", "stop_eating"}:
        if player.using_bow:
            player.release_bow()
        player.clear_eating(sync=True)
        player.clear_blocking(sync=True)
        return
    if action != "continue_breaking":
        return
    position = _read_block_position(packet)
    if position is not None:
        player.request_breaking(*position)


@SERVER_PACKET_DISPATCHER.handler("BreakBlock")
def _handle_break_block(packet: dict, player: Player) -> None:
    if player.sleeping:
        return
    position = _read_block_position(packet)
    if position is not None:
        player.finish_breaking(*position)


@SERVER_PACKET_DISPATCHER.handler("RightClick")
def _handle_right_click(packet: dict, player: Player) -> None:
    _process_right_click(packet, player)


@SERVER_PACKET_DISPATCHER.handler("PickupItem")
def _handle_pickup_item(packet: dict, player: Player) -> None:
    if player.sleeping:
        return
    from src.server.entities.item import Item

    entity = player.world.entities.get(str(packet.get("uuid", "")))
    if isinstance(entity, Item):
        entity.pick_up(player)


@SERVER_PACKET_DISPATCHER.handler("AttackEntity")
def _handle_attack_entity(packet: dict, player: Player) -> None:
    if player.sleeping:
        return
    target = _find_attack_target(player, packet.get("uuid", ""))
    current_tick = int(getattr(player.world.server, "server_ticks", 0))
    if (
        target is not None
        and current_tick != int(getattr(player, "_last_attack_tick", -1))
        and _can_player_reach_entity(player, target)
    ):
        player._last_attack_tick = current_tick
        player.clear_eating(sync=True)
        player.clear_blocking(sync=True)
        player.clear_bow_use(sync=True)
        player.attack_animation_ticks = player.attack_animation_duration
        player.attack(target)
        forward_packet_to_others(player, player, mode="entity_update")


@SERVER_PACKET_DISPATCHER.handler("InteractEntity")
def _handle_interact_entity(packet: dict, player: Player) -> None:
    if player.sleeping:
        return
    target = _find_attack_target(player, packet.get("uuid", ""))
    if target is not None and _can_player_reach_entity(player, target):
        slot = max(0, min(len(player.inventory) - 1, int(player.selected_slot)))
        held = player.inventory[slot]
        handled = bool(target.interact(player, held))
        if handled:
            player.apply_item_event(
                held,
                "on_successful_entity_interaction",
                target,
            )
            player.sync_inventory()
            player.attack_animation_ticks = max(player.attack_animation_ticks, 6)
            forward_packet_to_others(player, player, mode="entity_update")
        elif player.use_held_item():
            player.attack_animation_ticks = max(player.attack_animation_ticks, 6)
            forward_packet_to_others(player, player, mode="entity_update")


@SERVER_PACKET_DISPATCHER.handler("SelfDamage")
def _handle_self_damage(packet: dict, player: Player) -> None:
    return


@SERVER_PACKET_DISPATCHER.handler("ChatMessage")
def _handle_chat_message(packet: dict, player: Player) -> None:
    # 客户端发送的聊天消息
    text = packet.get("text", "")
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
                if isinstance(result, str) and result.startswith("§c"):
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


@SERVER_PACKET_DISPATCHER.handler("ClientShutdown")
def _handle_client_shutdown(packet: dict, player: Player) -> None:
    for container in tuple(player.open_inventory_containers.values()):
        owner = getattr(
            container,
            "owner_block",
            getattr(container, "furnace", None),
        )
        if owner is not None:
            owner.close_for(player)
    player.world.server.save_all(player, force=True)
    player.world.server.send_client_socket(
        player, make_packet("SaveComplete")
    )


@SERVER_PACKET_DISPATCHER.handler("InventoryClick")
def _handle_inventory_click(packet: dict, player: Player) -> None:
    try:
        player.inventory_click(int(packet.get("slot")), int(packet.get("button")))
    except (TypeError, ValueError):
        player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("ContainerClick")
def _handle_container_click(packet: dict, player: Player) -> None:
    try:
        player.container_click(
            str(packet.get("container", "")),
            packet.get("slot"),
            int(packet.get("button")),
        )
    except (TypeError, ValueError, IndexError):
        player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("CloseFurnace")
def _handle_close_furnace(packet: dict, player: Player) -> None:
    container_id = str(packet.get("container", ""))
    container = player.open_inventory_containers.get(container_id)
    furnace = getattr(container, "furnace", None)
    if furnace is not None:
        furnace.close_for(player)


@SERVER_PACKET_DISPATCHER.handler("CloseChest")
def _handle_close_chest(packet: dict, player: Player) -> None:
    container_id = str(packet.get("container", ""))
    container = player.open_inventory_containers.get(container_id)
    chest = getattr(container, "chest", None)
    if chest is not None:
        chest.close_for(player)


@SERVER_PACKET_DISPATCHER.handler("ContainerQuickMove")
def _handle_container_quick_move(packet: dict, player: Player) -> None:
    try:
        player.container_quick_move(
            str(packet.get("container", "")),
            packet.get("slot"),
            screen=str(packet.get("screen", "inventory")),
            crafting_size=int(packet.get("crafting_size", 4)),
            all_matching=bool(packet.get("all_matching", False)),
        )
    except (TypeError, ValueError, IndexError):
        player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("ContainerSwap")
def _handle_container_swap(packet: dict, player: Player) -> None:
    try:
        player.container_swap(
            str(packet.get("container", "")),
            packet.get("slot"),
            str(packet.get("target_container", "")),
            packet.get("target_slot"),
        )
    except (TypeError, ValueError, IndexError):
        player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("ContainerDrop")
def _handle_container_drop(packet: dict, player: Player) -> None:
    try:
        player.drop_container(
            str(packet.get("container", "inventory")),
            packet.get("slot"),
            cursor=bool(packet.get("cursor", False)),
            amount=packet.get("amount"),
        )
    except (TypeError, ValueError, IndexError):
        player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("CreativeSetSlot")
def _handle_creative_set_slot(packet: dict, player: Player) -> None:
    if getattr(player.gamemode, "name_id", "survival") != "creative":
        player.sync_inventory()
        return
    try:
        item_payload = packet.get("item", packet)
        item = payload_to_stack(item_payload)
        item = EmptyItemStack() if item.is_empty() else item
        if packet.get("target", "inventory") == "cursor":
            player.cursor_stack = item
        else:
            slot = int(packet.get("slot"))
            if not 0 <= slot < len(player.inventory):
                raise ValueError
            player.inventory[slot] = item
    except (TypeError, ValueError):
        pass
    player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("CreativeClearInventory")
def _handle_creative_clear_inventory(packet: dict, player: Player) -> None:
    if getattr(player.gamemode, "name_id", "survival") != "creative":
        player.sync_inventory()
        return
    for slot in range(len(player.inventory)):
        player.inventory[slot] = EmptyItemStack()
    for slot in player.equipment:
        player.equipment[slot] = EmptyItemStack()
    player._equipment_attribute_signature = None
    player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("InventoryDrag")
def _handle_inventory_drag(packet: dict, player: Player) -> None:
    try:
        button = int(packet.get("button"))
    except (TypeError, ValueError):
        button = 0
    player.inventory_drag(packet.get("slots", []), button)


@SERVER_PACKET_DISPATCHER.handler("ContainerDrag")
def _handle_container_drag(packet: dict, player: Player) -> None:
    try:
        button = int(packet.get("button"))
    except (TypeError, ValueError):
        button = 0
    player.container_drag(
        str(packet.get("container", "")),
        packet.get("slots", []),
        button,
    )


@SERVER_PACKET_DISPATCHER.handler("CraftingDrag")
def _handle_crafting_drag(packet: dict, player: Player) -> None:
    try:
        button = int(packet.get("button"))
    except (TypeError, ValueError):
        button = 0
    player.crafting_drag(packet.get("slots", []), button)


@SERVER_PACKET_DISPATCHER.handler("InventoryDrop")
def _handle_inventory_drop(packet: dict, player: Player) -> None:
    cursor = bool(packet.get("cursor", True))
    slot = packet.get("slot")
    try:
        if not cursor:
            slot = int(slot)
            if not 0 <= slot < len(player.inventory):
                raise ValueError
        amount = packet.get("amount")
        player.drop_inventory(cursor=cursor, slot=slot, amount=amount)
    except (TypeError, ValueError, IndexError):
        player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("InventoryResyncRequest")
def _handle_inventory_resync_request(packet: dict, player: Player) -> None:
    player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("CraftingClick")
def _handle_crafting_click(packet: dict, player: Player) -> None:
    try:
        player.crafting_click(int(packet.get("slot")), int(packet.get("button")))
    except (TypeError, ValueError):
        player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("CraftingTake")
def _handle_crafting_take(packet: dict, player: Player) -> None:
    try:
        width, height = int(packet.get("width", 2)), int(packet.get("height", 2))
    except (TypeError, ValueError):
        width, height = 2, 2
    player.crafting_take(width, height)


@SERVER_PACKET_DISPATCHER.handler("CraftingQuickTake")
def _handle_crafting_quick_take(packet: dict, player: Player) -> None:
    try:
        width, height = int(packet.get("width", 2)), int(packet.get("height", 2))
    except (TypeError, ValueError):
        width, height = 2, 2
    player.crafting_quick_take(width, height)


@SERVER_PACKET_DISPATCHER.handler("CraftingClose")
def _handle_crafting_close(packet: dict, player: Player) -> None:
    player.crafting_close()


@SERVER_PACKET_DISPATCHER.handler("SaveHotbar")
def _handle_save_hotbar(packet: dict, player: Player) -> None:
    player.save_hotbar(packet.get("preset"))


@SERVER_PACKET_DISPATCHER.handler("LoadHotbar")
def _handle_load_hotbar(packet: dict, player: Player) -> None:
    player.load_hotbar(packet.get("preset"))


@SERVER_PACKET_DISPATCHER.handler("SelectHotbarSlot")
def _handle_select_hotbar_slot(packet: dict, player: Player) -> None:
    old_slot = player.selected_slot
    try:
        player.selected_slot = max(0, min(8, int(packet.get("slot"))))
    except (TypeError, ValueError):
        pass
    if player.selected_slot != old_slot:
        player.clear_breaking()
        player.clear_eating()
        player.clear_blocking()
        player.clear_bow_use()
    player.sync_inventory()


@SERVER_PACKET_DISPATCHER.handler("RequestRespawn")
def _handle_request_respawn(packet: dict, player: Player) -> None:
    if player.health > 0:
        return
    player.clear_status_effects()
    player.health = player.max_health
    player.absorption_amount = 0.0
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
    player.score = 0
    player.clear_breaking()
    player.clear_eating()
    player.clear_blocking()

    saved_spawn = player.spawn_point
    if isinstance(saved_spawn, dict):
        server = player.world.server
        world = server.worlds.get(str(saved_spawn.get("world", "")))
        try:
            bed_x = int(saved_spawn["x"])
            bed_y = int(saved_spawn["y"])
            bed_z = int(saved_spawn["z"])
        except (KeyError, TypeError, ValueError, OverflowError):
            world = None
        if world is not None and 0 <= bed_y < world.attribute.MAX_BUILD_HEIGHT:
            if not world.is_chunk_loaded(bed_x // 16):
                world.generate_chunk(bed_x // 16)
            bed = world.get_block(bed_x, bed_y, bed_z)
            counterpart_location = getattr(
                bed, "get_counterpart_location", lambda: None
            )()
            if (
                counterpart_location is not None
                and not world.is_chunk_loaded(int(counterpart_location.x) // 16)
            ):
                world.generate_chunk(int(counterpart_location.x) // 16)
            respawn_position = getattr(bed, "get_respawn_position", lambda _p: None)(
                player
            )
            if respawn_position is not None:
                respawn_x, respawn_y, respawn_z = respawn_position
                player.z = int(respawn_z)
                player.teleport_to(respawn_x, respawn_y, world)
                return
        server.send_chat_to_player(player, "Your home bed was missing or obstructed.")

    spawn_x = int(getattr(player.world, "spawn_point", 0))
    block = player.world.find_top_block(spawn_x, 0)
    if block is not None:
        player.z = 0
        player.teleport_to(float(spawn_x), block.location.y + 1)


def _read_structure_point(value) -> tuple[int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        numbers = tuple(float(part) for part in value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(part) and part.is_integer() for part in numbers):
        return None
    return tuple(int(part) for part in numbers)


@SERVER_PACKET_DISPATCHER.handler("StructureEdit")
def _handle_structure_edit(packet: dict, player: Player) -> None:
    world = player.world
    if not world.structure_build_mode:
        return
    held = player.inventory[player.selected_slot]
    if not held.is_empty() or getattr(player.gamemode, "name_id", "") != "creative":
        return
    action = str(packet.get("action", ""))
    start = _read_structure_point(packet.get("start"))
    end = _read_structure_point(packet.get("end"))
    if start is None or end is None:
        return
    if action == "toggle":
        end = start
        position = start
        if getattr(world.get_block(*position), "block_id", "air") != "air":
            return
        kind = (
            "air"
            if position in world.structure_void_positions
            else "structure_void"
        )
    elif action == "fill":
        kind = str(packet.get("kind", ""))
    else:
        return
    if kind not in {"air", "structure_void"}:
        return
    if start[2] != end[2]:
        return
    for point in (start, end):
        x, y, z = point
        if (
            not 0 <= y < world.attribute.MAX_BUILD_HEIGHT
            or z not in (0, 1)
            or x // 16 not in player.client_loaded_regions
        ):
            return
    try:
        apply_structure_mask(world, kind, start, end)
    except ValueError as exc:
        logging.warning("Rejected structure edit from %s: %s", player.name, exc)


# ClientHello is consumed before a Player exists in SocketServer.receive_client_hello.
SERVER_PACKET_DISPATCHER.validate_handlers(exclude=("ClientHello",))


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
            biome_update = {"rx": chunk_rx, "biome_array": chunk.get_full_biome_dict()}
            player.world.server.send_client_socket(player, biome_update, "BiomeUpdate")


def forward_packet_to_others(packet, player: Player, mode=0):
    if mode == 0:
        for other_player in player.world.server.players:
            if other_player != player:
                other_player.world.server.send_client_socket(
                    other_player, packet, "Forward"
                )
    elif mode == "entity_update":
        for other_player in player.world.server.players:
            if other_player != player and other_player.is_loading_position(
                int(player.x), int(player.y), 0
            ):
                other_player.world.server.send_client_socket(
                    other_player, packet, "EntityUpdate"
                )
