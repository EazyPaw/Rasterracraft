import logging
import traceback
import sys

from typing import TYPE_CHECKING, Callable, List, Dict

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
        "exec": self.python_execute
    }

    def python_execute(self, args, executor: Player | str):
        """
        执行 Python 命令
        """
        if not self.allow_python_execute: return "python execute is not enabled on this server!"
        code = " ".join(args)
        exec(code)

        return f"Done"

    def list_region(self, args, executor: Player | str):
        world_name = args[0]
        regions = str(self.server.worlds[world_name].regions)
        return f"{world_name} regions: {regions}"

    def list_players(self, args, executor: Player | str):
        return str((self.server.players[0].x,self.server.players[0].y))

    def teleport(self, args, executor: Player | str):
        """
        tp 指令，模仿 Minecraft 的 tp 语法：
        - /tp <x> <y>                传送执行者到坐标
        - /tp <destination>          传送执行者到目标实体
        - /tp <targets> <destination> 传送目标到目标实体
        - /tp <targets> <x> <y>      传送目标到坐标
        """
        # 清理空参数
        args = [a for a in args if a]
        if not args:
            raise ValueError("Usage: /tp [targets] <destination|x y>")

        def try_parse_coords(s1, s2):
            """尝试将两个字符串解析为浮点坐标"""
            try:
                return float(s1), float(s2)
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
