import logging
import traceback

from typing import TYPE_CHECKING, Callable, List, Dict

if TYPE_CHECKING:
    from resources.server.server_main import Server

class CommandExecutor:
    def __init__(self,server: 'Server'):
        self.server = server
        self.commands_map: Dict[str, Callable[[List[str]], str]] = {
        "regions": self.list_region,
    }

    def list_region(self, args):
        world_name = args[0]
        regions = str(self.server.worlds[world_name].regions)
        return f"{world_name} regions: {regions}"


    def execute_command(self, args: list) -> str:
        cmd = args.pop(0)
        if cmd in self.commands_map:
            try:
                return_info = self.commands_map[cmd](args)
                return return_info
            except Exception as e:
                return f"Error executing command: {cmd}\n{traceback.format_exc()}"
        else:
            return f"Unknown command: {cmd}"