import ast
import logging
import traceback
from typing import TYPE_CHECKING, Callable, List, Dict

from resources.server.blocks import get_block_by_id
from resources.server.entity import Entity
from resources.server.location import Location
from resources.server.player import Player

if TYPE_CHECKING:
    from resources.server.server_main import Server

class CommandExecutor:
    def __init__(self,server: 'Server'):
        self.server = server
        self.allow_python_execute = True # 是否允许执行 Python 命令。攻击者可以通过该命令执行任意恶意指令，这十分危险！通常仅应该在开发时被打开！
        self.commands_map: Dict[str, Callable[[List[str], Player | str], str]] = {
        "regions": self.list_region,
        "players": self.list_players,
        "tp": self.teleport,
        "exec": self.python_execute,
        "setblock": self.set_block_c,
        "say": self.say_command,
        "fill": self.fill_command,
        "time": self.time
    }

    def python_execute(self, args, executor: Player | str):
        """
        执行 Python 命令
        """
        if not self.allow_python_execute: return "python execute is not enabled on this server!"
        code = " ".join(args)
        exec(code)

        return f"Done"

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

    def list_region(self, args, executor: Player | str):
        world_name = args[0]
        regions = str(self.server.worlds[world_name].regions)
        return f"{world_name} regions: {regions}"

    def list_players(self, args, executor: Player | str):
        return str((self.server.players[0].x,self.server.players[0].y))

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
                return (self._parse_coord(s1, ref_x),
                        self._parse_coord(s2, ref_y))
            except ValueError:
                return None

        targets = None
        target_location = None

        if len(args) == 1:
            # /tp <destination>
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
                    raise ValueError("Console cannot teleport itself, must specify targets")
                targets = [executor]
                target_location = coords

        elif len(args) == 3:
            # /tp <targets> <x> <y>
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

        world = executor.world if isinstance(executor, Player) else self.server.worlds[self.server.main_world_id]
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
        if '[' in block_str and block_str.rstrip().endswith(']'):
            bracket_start = block_str.index('[')
            block_id = block_str[:bracket_start]
            nbt_str = block_str[bracket_start + 1:block_str.rindex(']')]
            for pair in nbt_str.split(','):
                pair = pair.strip()
                if '=' not in pair:
                    continue
                key, value = pair.split('=', 1)
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
        if value.startswith('~'):
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
            raise ValueError("Usage: /fill <x1> <y1> <z1> <x2> <y2> <z2> <block> [mode]")

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
        mode = args[7].lower() if len(args) > 7 else 'replace'
        if mode not in ('replace', 'destroy', 'keep', 'hollow', 'outline'):
            raise ValueError(f"Invalid mode '{mode}'. Valid modes: replace, destroy, keep, hollow, outline")

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
                    if mode == 'keep':
                        existing = world.get_block(x, y, z)
                        if not existing.replaceable:
                            continue
                    elif mode in ('hollow', 'outline'):
                        # 仅填充三维区域的表面（六个面）
                        is_surface = (
                            x == x_min or x == x_max or
                            y == y_min or y == y_max or
                            z == z_min or z == z_max
                        )
                        if not is_surface:
                            continue

                    if mode == 'destroy':
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
            chunk = world.regions.get(rx)
            if chunk is None:
                continue
            chunk.recalculate_all_light(world=world)
            for player in world.server.players:
                if rx in player.loading_regions:
                    world.server.send_client_socket(player, chunk, "Chunk")

        return f"Filled {filled} block(s) with {block_id}"


    def execute_command(self, executor: Player | str, args: list) -> str:
        cmd = args.pop(0)
        if cmd in self.commands_map:
            try:
                return_info = self.commands_map[cmd](args, executor)
                return return_info
            except Exception as e:
                if self.server.commands_error_traceback:
                    logging.error(f"§cError executing command: {cmd}\n{traceback.format_exc()}")
                else:
                    logging.error(f"§cUnknown or invalid command: {cmd}\n{e}")
                return f"§cUnknown or invalid command: {cmd}\n{e}"
        else:
            return f"§cUnknown or invalid command: {cmd}"


    def target_selector(self, input_str: str, executor: Player | str) -> List[Entity] | None:
        """
        目标选择器

        支持的选择器：
        - @s - 执行者自己
        - @a - 所有玩家
        - @p - 最近的玩家
        - @r - 随机玩家

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
                nearest = min(self.server.players,
                            key=lambda p: (p.x - executor.x)**2 + (p.y - executor.y)**2)
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

        else:
            # 尝试按名称查找玩家
            for player in self.server.players:
                if str(player) == input_str or player.uuid.hex[:8] == input_str:
                    return [player]

            # 不是有效的选择器或名称
            return None
