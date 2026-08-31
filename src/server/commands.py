# Commented and arranged by ChatGPT
import ast
import logging
import traceback
import time
import re
from typing import TYPE_CHECKING, Callable, List, Dict

from src.client.game_mode import get_gamemode_by_id
from src.server.blocks import get_block_by_id
from src.server.entity import Entity
from src.server.enchantments import get_enchantment
from src.server.location import Location
from src.server.materials import get_material_by_id
from src.server.player import Player
from src.server.text import Text, TextColor
from src.server.biome import BIOME_PROFILES
from src.server.status_effects import (
    INFINITE_DURATION,
    STATUS_EFFECTS,
    StatusEffectInstance,
    get_status_effect,
)

if TYPE_CHECKING:
    from src.server.server_main import Server


class CommandExecutor:
    def __init__(self, server: "Server"):
        self.server = server
        self.allow_python_execute = True  # 是否允许执行 Python 命令。攻击者可以通过该命令执行任意恶意指令，这十分危险！通常仅应该在开发时被打开！
        self.commands_map: Dict[
            str, Callable[[List[str], Player | str], str | Text]
        ] = {
            "regions": self.list_region,
            "players": self.list_players,
            "tp": self.teleport,
            "exec": self.python_execute,
            "setblock": self.set_block_c,
            "say": self.say_command,
            "fill": self.fill_command,
            "time": self.time,
            "weather": self.weather,
            "gamemode": self.switch_gamemode,
            "give": self.give_command,
            "enchant": self.enchant_command,
            "effect": self.effect_command,
            "kick": self.kick_command,
            "locate": self.locate_command,
            "summon": self.summon_command,
            "tps": self.tps_command,
            "mspt": self.mspt_command,
            "stop": self.stop_server,
        }

    @staticmethod
    def _performance_color(
        value: float, good: float, warning: float, higher_is_better=True
    ):
        if higher_is_better:
            if value >= good:
                return TextColor.GREEN
            if value >= warning:
                return TextColor.YELLOW
        else:
            if value <= good:
                return TextColor.GREEN
            if value <= warning:
                return TextColor.YELLOW
        return TextColor.RED

    def tps_command(self, args, executor: Player | str):
        if args:
            raise ValueError("Usage: /tps")
        values = self.server.get_performance_snapshot().tps_averages
        message = Text("TPS from last 1m, 5m, 15m: ", TextColor.GOLD)
        for index, value in enumerate(values):
            if index:
                message += Text(", ", TextColor.GOLD)
            message += Text(
                f"{value:.1f}",
                self._performance_color(value, good=18.0, warning=15.0),
            )
        return message

    def mspt_command(self, args, executor: Player | str):
        if args:
            raise ValueError("Usage: /mspt")
        stats_by_window = self.server.get_performance_snapshot().mspt_stats
        message = Text("Server tick times ", TextColor.GOLD)
        message += Text("(avg/min/max) ", TextColor.GRAY)
        message += Text("from last 5s, 10s, 1m:\n", TextColor.GOLD)
        for window_index, stats in enumerate(stats_by_window):
            if window_index:
                message += Text(", ", TextColor.GOLD)
            for stat_index, value in enumerate(stats):
                if stat_index:
                    message += Text("/", TextColor.GRAY)
                message += Text(
                    f"{value:.1f}",
                    self._performance_color(
                        value, good=40.0, warning=50.0, higher_is_better=False
                    ),
                )
        return message

    def python_execute(self, args, executor: Player | str):
        """
        执行 Python 命令
        """
        if not self.allow_python_execute or (
            isinstance(executor, Player) and not executor.is_operator
        ):
            return "python execute is not enabled for this player!"
        code = " ".join(args)
        start_time = time.time()
        exec(code)
        end_time = time.time()
        execution_time = end_time - start_time
        return f"Done in {execution_time * 1000} ms."

    def stop_server(self, args, executor: Player | str):
        self.server.close_server()
        return "Stopping server.."

    def switch_gamemode(self, args, executor: Player | str):
        if not isinstance(executor, Player) or len(args) != 1:
            raise ValueError("Usage: /gamemode <creative|survival>")

        gamemode = get_gamemode_by_id(args[0].lower())

        executor.gamemode = gamemode
        self.server.send_client_socket(executor, executor, "GamemodeUpdate")
        return f"Gamemode is set to {gamemode.name_id}"

    def give_command(self, args, executor: Player | str):
        """
        /give <target> <item> [<count>]

        模仿 Minecraft 的 give 指令，给予目标玩家指定物品。
        - <target>: 目标选择器 (@s, @a, @p, @r) 或玩家名称
        - <item>: 物品 ID（如 "dirt", "apple", "stone_pickaxe"）
        - [<count>]: 可选数量，默认 1，最大为一组堆叠上限
        """
        if len(args) < 2:
            raise ValueError("Usage: /give <target> <item> [<count>]")
        if isinstance(executor, Player) and not executor.is_operator:
            raise ValueError("You do not have permission to use /give")

        # ---- 1. 解析目标 ----
        targets = self.target_selector(args[0], executor)
        if targets is None:
            raise ValueError(f"No targets matched: {args[0]}")
        if len(targets) == 0:
            raise ValueError(f"No targets matched: {args[0]}")

        # ---- 2. 解析物品 ----
        item_id = args[1].removeprefix("minecraft:")
        material = get_material_by_id(item_id)
        if material.name_id == "air" and item_id != "air":
            raise ValueError(f"Unknown item: {args[1]}")

        # ---- 3. 解析数量 ----
        count = 1
        if len(args) >= 3:
            try:
                count = int(args[2])
            except ValueError:
                raise ValueError(f"Invalid count: {args[2]}")

        if count < 1:
            raise ValueError("Count must be at least 1")
        if count > material.max_stack_size:
            count = material.max_stack_size

        # ---- 4. 分发物品 ----
        given_items = 0
        given_players = 0
        for target in targets:
            if not isinstance(target, Player):
                continue
            added = target.give_item(material, count)
            given_items += added
            if added:
                given_players += 1

        item_name = getattr(material, "name", item_id)
        return f"Gave {given_items}x {item_name} to {given_players} player(s)"

    @staticmethod
    def _parse_effect_boolean(value: str) -> bool:
        value = str(value).strip().lower()
        if value == "true":
            return True
        if value == "false":
            return False
        raise ValueError("hideParticles must be true or false")

    def effect_command(self, args, executor: Player | str):
        """Execute Java-style ``/effect give`` and ``/effect clear``."""
        if isinstance(executor, Player) and not executor.is_operator:
            raise ValueError("You do not have permission to use /effect")
        if not args or args[0] not in {"give", "clear"}:
            raise ValueError(
                "Usage: /effect give <targets> <effect> [seconds|infinite] "
                "[amplifier] [hideParticles] | /effect clear [targets] [effect]"
            )

        action = args[0]
        if action == "clear":
            if len(args) > 3:
                raise ValueError("Usage: /effect clear [targets] [effect]")
            target_token = args[1] if len(args) >= 2 else "@s"
            targets = self.target_selector(target_token, executor)
            if not targets:
                raise ValueError(f"No targets matched: {target_token}")
            effect = None
            if len(args) == 3:
                effect = get_status_effect(args[2])
                if effect is None:
                    raise ValueError(f"Unknown effect: {args[2]}")
            changed = 0
            for target in targets:
                if effect is None:
                    changed += target.clear_status_effects()
                elif target.remove_status_effect(effect.id):
                    changed += 1
            if changed == 0:
                raise ValueError("No effects were cleared")
            return f"Cleared {changed} effect(s) from {len(targets)} target(s)"

        if not 3 <= len(args) <= 6:
            raise ValueError(
                "Usage: /effect give <targets> <effect> [seconds|infinite] "
                "[amplifier] [hideParticles]"
            )
        target_token = args[1]
        targets = self.target_selector(target_token, executor)
        if not targets:
            raise ValueError(f"No targets matched: {target_token}")
        effect = get_status_effect(args[2])
        if effect is None:
            available = ", ".join(STATUS_EFFECTS)
            raise ValueError(f"Unknown effect: {args[2]}. Available: {available}")

        seconds_token = args[3].lower() if len(args) >= 4 else "30"
        if seconds_token == "infinite":
            duration = INFINITE_DURATION
        else:
            try:
                seconds = int(seconds_token)
            except ValueError as exc:
                raise ValueError(f"Invalid duration: {seconds_token}") from exc
            if not 1 <= seconds <= 1_000_000:
                raise ValueError("Duration must be between 1 and 1000000 seconds")
            duration = seconds * 20

        try:
            amplifier = int(args[4]) if len(args) >= 5 else 0
        except ValueError as exc:
            raise ValueError(f"Invalid amplifier: {args[4]}") from exc
        if not 0 <= amplifier <= 255:
            raise ValueError("Amplifier must be between 0 and 255")
        hide_particles = (
            self._parse_effect_boolean(args[5]) if len(args) >= 6 else False
        )
        instance = StatusEffectInstance(
            effect.id,
            duration,
            amplifier,
            ambient=False,
            show_particles=not hide_particles,
            show_icon=not hide_particles,
        )
        changed = sum(target.add_status_effect(instance) for target in targets)
        if changed == 0:
            raise ValueError("Could not apply the requested effect")
        duration_text = (
            "infinite" if duration == INFINITE_DURATION else f"{duration // 20}s"
        )
        return (
            f"Applied {effect.id} {amplifier + 1} to {changed} target(s) "
            f"for {duration_text}"
        )

    def enchant_command(self, args, executor: Player | str):
        """Apply an enchantment to each target player's selected item."""
        if len(args) not in (2, 3):
            raise ValueError("Usage: /enchant <targets> <enchantment> [<level>]")
        if isinstance(executor, Player) and not executor.is_operator:
            raise ValueError("You do not have permission to use /enchant")

        targets = self.target_selector(args[0], executor)
        if not targets:
            raise ValueError(f"No targets matched: {args[0]}")
        if any(not isinstance(target, Player) for target in targets):
            raise ValueError("Only players can be enchanted")

        enchantment = get_enchantment(args[1])
        if enchantment is None:
            raise ValueError(f"Unknown enchantment: {args[1]}")
        try:
            level = enchantment.validate_level(args[2] if len(args) == 3 else 1)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Level must be between 1 and {enchantment.max_level}"
            ) from exc

        held_items = []
        for target in targets:
            held = target.get_equipped_item("mainhand")
            if held.is_empty():
                raise ValueError(f"{target} is not holding an item")
            if not enchantment.supports(held):
                raise ValueError(
                    f"{enchantment.id} cannot be applied to {held.material.name_id}"
                )
            held_items.append((target, held))

        for target, held in held_items:
            held.set_enchantment(enchantment.id, level)
            target._equipment_attribute_signature = None
            target.sync_inventory()
        return (
            f"Enchanted {len(held_items)} item(s) with "
            f"{enchantment.id} {level}"
        )

    def kick_command(self, args, executor: Player | str):
        if not args:
            raise ValueError("Usage: /kick <target> [reason]")
        if isinstance(executor, Player) and not executor.is_operator:
            raise ValueError("You do not have permission to use /kick")
        targets = self.target_selector(args[0], executor)
        if targets is None or not targets:
            raise ValueError(f"No targets matched: {args[0]}")
        reason = " ".join(args[1:]).strip() or None
        kicked = 0
        for target in targets:
            if isinstance(target, Player) and self.server.kick_player(target, reason):
                kicked += 1
        return f"Kicked {kicked} player(s)"

    def locate_command(self, args, executor: Player | str):
        if len(args) < 2 or args[0].lower() != "biome":
            raise ValueError("Usage: /locate biome <biome>")
        biome_id = args[1].lower().removeprefix("minecraft:")
        if biome_id not in BIOME_PROFILES:
            raise ValueError(f"Unknown biome: {args[1]}")
        if isinstance(executor, Player):
            world = executor.world
            origin_x = int(round(executor.x))
        else:
            world = self.server.worlds[self.server.main_world_id]
            origin_x = 0
        generator = world.generator

        max_radius = 524288

        for radius in range(max_radius + 1):
            candidates = (
                (origin_x,) if radius == 0 else (origin_x - radius, origin_x + radius)
            )
            for x in candidates:
                if generator.get_original_biome(x, 0) != biome_id:
                    continue
                if hasattr(generator, "get_surface_height"):
                    y = generator.get_surface_height(x)
                else:
                    y = 70
                return f"The nearest {biome_id} is at ({x}, {y})"
        raise ValueError(
            f"Could not locate biome {biome_id} within {max_radius} blocks"
        )

    @staticmethod
    def _parse_summon_nbt(raw: str) -> dict:
        raw = raw.strip()
        if not raw:
            return {}
        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            normalized = re.sub(
                r"([,{]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)",
                r"\1'\2'\3",
                raw,
            )
            normalized = re.sub(
                r"(?<=\d)[bBsSlLfFd](?=\s*[,}])",
                "",
                normalized,
            )
            normalized = re.sub(r"\btrue\b", "True", normalized, flags=re.IGNORECASE)
            normalized = re.sub(r"\bfalse\b", "False", normalized, flags=re.IGNORECASE)
            try:
                value = ast.literal_eval(normalized)
            except (SyntaxError, ValueError) as exc:
                raise ValueError(f"Invalid entity NBT: {raw}") from exc
        if not isinstance(value, dict):
            raise ValueError("Entity NBT must be a compound")
        return value

    def summon_command(self, args, executor: Player | str):
        if not args:
            raise ValueError("Usage: /summon <entity> [<x> <y> <z>] [<nbt>]")
        if isinstance(executor, Player) and not executor.is_operator:
            raise ValueError("You do not have permission to use /summon")

        entity_id = args[0].lower()
        from src.server.entity_registry import get_entity_type

        if get_entity_type(entity_id, summonable_only=True) is None:
            raise ValueError(f"Unknown entity: {args[0]}")

        if isinstance(executor, Player):
            world = executor.world
        else:
            world = self.server.worlds[self.server.main_world_id]
        ref_x, ref_y, ref_z = self._get_reference_position(executor)

        if len(args) == 1:
            x, y, z = ref_x, ref_y, int(ref_z)
            nbt = {}
        else:
            if len(args) < 4:
                raise ValueError("Summon position requires x, y and z")
            try:
                x = self._parse_coord(args[1], ref_x)
                y = self._parse_coord(args[2], ref_y)
                raw_z = self._parse_coord(args[3], ref_z)
            except ValueError as exc:
                raise ValueError(f"Invalid coordinate: {exc}") from exc
            if not raw_z.is_integer() or int(raw_z) not in (0, 1):
                raise ValueError("z must be foreground 0 or background 1")
            z = int(raw_z)
            nbt = self._parse_summon_nbt(" ".join(args[4:])) if len(args) > 4 else {}

        if not 0 <= y < world.attribute.MAX_BUILD_HEIGHT:
            raise ValueError(
                f"y must be between 0 and {world.attribute.MAX_BUILD_HEIGHT - 1}"
            )

        from src.server.entity_registry import create_entity

        entity = create_entity(entity_id, x, y, world, z)
        entity.apply_summon_nbt(nbt)
        world.spawn_entity(entity)
        return f"Summoned {entity_id} at ({entity.x:g}, {entity.y:g}, {entity.z})"

    def time(self, args, executor: Player | str):
        if args[0] == "add" and isinstance(executor, Player):
            executor.world.world_time += int(args[1])
            return f"Time has set to {executor.world.world_time}"
        elif args[0] == "set" and isinstance(executor, Player):
            executor.world.world_time = int(args[1])
            return f"Time has set to {executor.world.world_time}"
        elif args[0] == "query" and isinstance(executor, Player):
            return f"Now time is {executor.world.world_time}"
        else:
            raise ValueError(f"Invalid args: {args}")

    def weather(self, args, executor: Player | str):
        if not args or args[0].lower() == "query":
            world = (
                executor.world
                if isinstance(executor, Player)
                else self.server.worlds[self.server.main_world_id]
            )
            return f"Weather is {world.weather.value} ({world.weather_tick} ticks remaining)"
        state = args[0].lower()
        if state not in ("clear", "rain"):
            raise ValueError("Usage: /weather <clear|rain> [seconds]")
        duration_ticks = None
        if len(args) > 1:
            try:
                duration_ticks = max(1, int(float(args[1]) * self.server.rate))
            except (ValueError, OverflowError) as exc:
                raise ValueError(
                    "Weather duration must be a number of seconds"
                ) from exc
        world = (
            executor.world
            if isinstance(executor, Player)
            else self.server.worlds[self.server.main_world_id]
        )
        from src.server.world_class import Weather

        world.set_weather(Weather(state), duration_ticks)
        return f"Weather set to {state}"

    def list_region(self, args, executor: Player | str):
        world_name = args[0]
        regions = str(self.server.worlds[world_name].regions)
        return f"{world_name} regions: {regions}"

    def list_players(self, args, executor: Player | str):
        return str((self.server.players[0].x, self.server.players[0].y))

    def teleport(self, args, executor: Player | str):
        """
        tp 指令，模仿 Minecraft 的 tp 语法：
        - /tp <x> <y>                传送执行者到坐标（支持 ~）
        - /tp <destination>          传送执行者到目标实体
        - /tp <targets> <destination> 传送目标到目标实体
        - /tp <targets> <x> <y>      传送目标到坐标（支持 ~）
        """
        # 清理空参数
        args = [a for a in args if a]
        if not args:
            raise ValueError("Usage: /tp [targets] <destination|x y>")

        ref_x, ref_y, _ = self._get_reference_position(executor)

        def try_parse_coords(s1, s2):
            """尝试将两个字符串解析为浮点坐标（支持 ~ 相对坐标）"""
            try:
                return (self._parse_coord(s1, ref_x), self._parse_coord(s2, ref_y))
            except ValueError:
                return None

        targets = None
        target_location = None

        if len(args) == 1:
            if isinstance(executor, str):
                raise ValueError("Console must specify target entities when using /tp")
            dest_entities = self.target_selector(args[0], executor)
            if dest_entities is None:
                raise ValueError(f"Invalid destination: {args[0]}")
            if len(dest_entities) != 1:
                raise ValueError("Destination must be a single entity")
            targets = [executor]
            target_location = (dest_entities[0].x, dest_entities[0].y)

        elif len(args) == 2:
            # 可能为 /tp <x> <y> 或 /tp <targets> <destination>
            # 优先尝试将 args[0] 作为目标选择器
            targets_entities = self.target_selector(args[0], executor)
            if targets_entities is not None and len(targets_entities) > 0:
                # 第一个参数是有效的实体选择器，视为 <targets>
                targets = targets_entities
                dest_entities = self.target_selector(args[1], executor)
                if dest_entities is None or len(dest_entities) == 0:
                    raise ValueError(f"Invalid destination: {args[1]}")
                if len(dest_entities) != 1:
                    raise ValueError("Destination must be a single entity")
                target_location = (dest_entities[0].x, dest_entities[0].y)
            else:
                # 不是实体选择器，尝试作为坐标传送执行者
                coords = try_parse_coords(args[0], args[1])
                if coords is None:
                    raise ValueError(f"Invalid arguments: {' '.join(args)}")
                if isinstance(executor, str):
                    raise ValueError(
                        "Console cannot teleport itself, must specify targets"
                    )
                targets = [executor]
                target_location = coords

        elif len(args) == 3:
            targets = self.target_selector(args[0], executor)
            if targets is None or len(targets) == 0:
                raise ValueError(f"No targets matched: {args[0]}")
            coords = try_parse_coords(args[1], args[2])
            if coords is None:
                raise ValueError("Invalid coordinates")
            target_location = coords

        else:
            raise ValueError("Too many arguments")

        # 执行传送
        for entity in targets:
            entity.teleport_to(target_location[0], target_location[1])

        return f"Teleported {len(targets)} entities to {target_location}"

    def set_block_c(self, args, executor: Player | str):
        """
        /setblock <x> <y> <z> <block>
        坐标支持相对坐标 (~, ~offset)。
        """
        if len(args) < 4:
            raise ValueError("Usage: /setblock <x> <y> <z> <block>")

        ref_x, ref_y, ref_z = self._get_reference_position(executor)

        try:
            x = int(self._parse_coord(args[0], ref_x))
            y = int(self._parse_coord(args[1], ref_y))
            z = int(self._parse_coord(args[2], ref_z))
        except ValueError as e:
            raise ValueError(f"Invalid coordinate: {e}")

        block_id, nbt = self._parse_block_spec(args[3])
        block = get_block_by_id(block_id)
        if nbt:
            block.write_nbt(nbt)

        world = (
            executor.world
            if isinstance(executor, Player)
            else self.server.worlds[self.server.main_world_id]
        )
        block.place_at(Location(world, x, y, z))
        return f"Block placed at {block.location}"

    def say_command(self, args, executor: Player | str):
        """广播消息给所有玩家（/say <message>）"""
        message = " ".join(args)
        if not message:
            raise ValueError("Usage: /say <message>")
        if len(message) > 128:
            message = message[:128]
        formatted = f"[Server] {message}"
        self.server.broadcast_chat(formatted, (255, 255, 85))
        return f"Broadcasted: {message}"

    @staticmethod
    def _parse_block_spec(block_str: str) -> tuple[str, dict]:
        """
        解析方块规格字符串，支持 NBT 方括号语法。
        例如: 'stone' → ('stone', {})
              'snow[layer=3]' → ('snow', {'layer': 3})
              'oak_log[axis=y]' → ('oak_log', {'axis': 'y'})
        """
        nbt = {}
        if "[" in block_str and block_str.rstrip().endswith("]"):
            bracket_start = block_str.index("[")
            block_id = block_str[:bracket_start]
            nbt_str = block_str[bracket_start + 1 : block_str.rindex("]")]
            for pair in nbt_str.split(","):
                pair = pair.strip()
                if "=" not in pair:
                    continue
                key, value = pair.split("=", 1)
                key = key.strip()
                value = value.strip()
                try:
                    value = ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    pass  # 保持字符串
                nbt[key] = value
        else:
            block_id = block_str
        return block_id, nbt

    @staticmethod
    def _parse_coord(value: str, reference: float) -> float:
        """
        解析可能为相对坐标的字符串。
        - '~'      → reference
        - '~5'     → reference + 5
        - '~-3.5'  → reference - 3.5
        - '100'    → 100.0
        """
        value = value.strip()
        if value.startswith("~"):
            if len(value) == 1:
                return float(reference)
            else:
                return float(reference) + float(value[1:])
        else:
            return float(value)

    @staticmethod
    def _get_reference_position(executor: Player | str) -> tuple[float, float, float]:
        """
        获取执行者的参考位置，用于相对坐标计算。
        玩家返回 (x, y, 0)；控制台返回 (0, 0, 0)。
        """
        if isinstance(executor, Player):
            return executor.x, executor.y, 0.0
        else:
            return 0.0, 0.0, 0.0

    def fill_command(self, args, executor: Player | str):
        """
        /fill <x1> <y1> <z1> <x2> <y2> <z2> <block> [mode]

        用指定方块填充三维区域。坐标支持相对坐标 (~, ~offset)。
        模式: replace (默认) | destroy | keep | hollow | outline
        """
        if len(args) < 7:
            raise ValueError(
                "Usage: /fill <x1> <y1> <z1> <x2> <y2> <z2> <block> [mode]"
            )

        # ---- 1. 解析坐标（支持 ~ 相对坐标） ----
        ref_x, ref_y, ref_z = self._get_reference_position(executor)

        try:
            x1 = int(self._parse_coord(args[0], ref_x))
            y1 = int(self._parse_coord(args[1], ref_y))
            z1 = int(self._parse_coord(args[2], ref_z))
            x2 = int(self._parse_coord(args[3], ref_x))
            y2 = int(self._parse_coord(args[4], ref_y))
            z2 = int(self._parse_coord(args[5], ref_z))
        except ValueError as e:
            raise ValueError(f"Invalid coordinate: {e}")

        # ---- 2. 标准化范围 ----
        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)
        z_min, z_max = min(z1, z2), max(z1, z2)

        # 限制 z 到有效范围 (0~1)
        z_min = max(0, z_min)
        z_max = min(1, z_max)

        # ---- 3. 解析方块 ----
        block_id, nbt = self._parse_block_spec(args[6])

        # ---- 4. 解析模式 ----
        mode = args[7].lower() if len(args) > 7 else "replace"
        if mode not in ("replace", "destroy", "keep", "hollow", "outline"):
            raise ValueError(
                f"Invalid mode '{mode}'. Valid modes: replace, destroy, keep, hollow, outline"
            )

        # ---- 5. 获取世界 ----
        if isinstance(executor, Player):
            world = executor.world
        else:
            world = self.server.worlds[self.server.main_world_id]

        max_h = world.attribute.MAX_BUILD_HEIGHT

        # ---- 6. 边界限制与数量检查 ----
        y_min = max(0, y_min)
        y_max = min(max_h - 1, y_max)

        area_width = x_max - x_min + 1
        area_height = y_max - y_min + 1
        area_depth = z_max - z_min + 1
        total_blocks = area_width * area_height * area_depth

        MAX_FILL_BLOCKS = 32768
        if total_blocks > MAX_FILL_BLOCKS:
            raise ValueError(
                f"Too many blocks ({total_blocks}). Maximum is {MAX_FILL_BLOCKS} "
                f"({area_width}×{area_height}×{area_depth})"
            )

        # ---- 7. 确保所需区块已生成 ----
        from_x_chunk = x_min // 16
        to_x_chunk = x_max // 16
        for rx in range(from_x_chunk, to_x_chunk + 1):
            if rx not in world.regions:
                world.generate_chunk(rx)

        # ---- 8. 批量设置方块 ----
        affected_chunks: set[int] = set()
        filled = 0

        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                for z in range(z_min, z_max + 1):
                    # 模式过滤
                    if mode == "keep":
                        existing = world.get_block(x, y, z)
                        if not existing.replaceable:
                            continue
                    elif mode in ("hollow", "outline"):
                        # 仅填充三维区域的表面（六个面）
                        is_surface = (
                            x == x_min
                            or x == x_max
                            or y == y_min
                            or y == y_max
                            or z == z_min
                            or z == z_max
                        )
                        if not is_surface:
                            continue

                    if mode == "destroy":
                        old = world.get_block(x, y, z)
                        old.on_break()

                    # 创建新方块实例
                    block = get_block_by_id(block_id)
                    if nbt:
                        block.write_nbt(nbt)
                    block.location = Location(world, x, y, z)

                    # 直接写入数组（跳过 set_block 的逐块光照/发包）
                    rx = x // 16
                    chunk = world.regions[rx]
                    chunk.region_array[x % 16][y][z] = block
                    filled += 1
                    affected_chunks.add(rx)

        # ---- 9. 受影响区块重算光照并同步客户端 ----
        for rx in affected_chunks:
            world.mark_chunk_dirty(rx)
            world.invalidate_chunk_packet(rx)
            if hasattr(world, "schedule_chunk_and_boundary_fluids"):
                world.schedule_chunk_and_boundary_fluids(rx)
        changed_light_chunks = world.recalculate_light_for_chunks(affected_chunks)
        for rx in affected_chunks:
            chunk = world.regions.get(rx)
            if chunk is None:
                continue
            for player in world.server.players:
                if rx in player.loading_regions:
                    world.server.send_client_socket(player, chunk, "Chunk")
        world.send_light_updates(changed_light_chunks - affected_chunks)

        return f"Filled {filled} block(s) with {block_id}"

    def execute_command(self, executor: Player | str, args: list) -> str | Text:
        cmd = args.pop(0)
        if cmd in self.commands_map:
            try:
                return_info = self.commands_map[cmd](args, executor)
                return return_info
            except Exception as e:
                if self.server.commands_error_traceback:
                    logging.error(
                        f"§cError executing command: {cmd}\n{traceback.format_exc()}"
                    )
                else:
                    logging.error(f"§cUnknown or invalid command: {cmd}\n{e}")
                return f"§cUnknown or invalid command: {cmd}\n{e}"
        else:
            return f"§cUnknown or invalid command: {cmd}"

    def target_selector(
        self, input_str: str, executor: Player | str
    ) -> List[Entity] | None:
        """
        目标选择器

        支持的选择器：
        - @s - 执行者自己
        - @a - 所有玩家
        - @p - 最近的玩家
        - @r - 随机玩家
        - @e - 所有已加载实体（包括玩家）

        返回 None 表示输入不是选择器（可能是坐标或实体名）
        返回空列表表示没有匹配的目标
        """

        input_str = input_str.strip()

        if input_str == "@s":
            if isinstance(executor, Entity):
                return [executor]
            else:
                raise ValueError("@s can only be used by entities, not console")

        elif input_str == "@a":
            return list(self.server.players)

        elif input_str == "@p":
            # 最近的玩家
            if not self.server.players:
                return []

            if isinstance(executor, Entity):
                # 找到距离执行者最近的玩家
                nearest = min(
                    self.server.players,
                    key=lambda p: (p.x - executor.x) ** 2 + (p.y - executor.y) ** 2,
                )
                return [nearest]
            else:
                # 控制台使用时，返回第一个玩家
                return [self.server.players[0]] if self.server.players else []

        elif input_str == "@r":
            # 随机玩家
            import random

            if not self.server.players:
                return []
            return [random.choice(self.server.players)]

        elif input_str == "@e":
            entities = list(self.server.players)
            seen = {str(entity.uuid) for entity in entities}
            for world in self.server.worlds.values():
                for entity in world.entities.values():
                    if str(entity.uuid) not in seen and not entity.removed:
                        entities.append(entity)
                        seen.add(str(entity.uuid))
            return entities

        else:
            # 尝试按名称查找玩家
            for player in self.server.players:
                if str(player) == input_str or player.uuid.hex[:8] == input_str:
                    return [player]

            # 再尝试已加载实体的名称、完整 UUID 或 UUID 前八位。
            for world in self.server.worlds.values():
                for entity in world.entities.values():
                    entity_uuid = str(entity.uuid)
                    if input_str in {
                        str(entity),
                        entity_uuid,
                        entity.uuid.hex[:8],
                        str(getattr(entity, "name", "")),
                    }:
                        return [entity]

            # 不是有效的选择器或名称
            return None
