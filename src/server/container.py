from src.server.entities.item import Item
from src.server.inventory import Inventory
from src.server.block_class import Block

class Container(Block):
    def __init__(self, nbt=None):
        super().__init__(nbt)
        self.slots = 27
        self.container = Inventory(self.slots)

    def on_break(self):
        super().on_break()
        if self.get_server() is not None:
            location = self.location
            world = location.world
            for item in self.container:
                world.spawn_entity(Item(location.x, location.y, world, item, location.z))
