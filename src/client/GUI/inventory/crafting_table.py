# Commented and arranged by ChatGPT
from src.client.GUI.inventory.backpack import Backpack


class CraftingTable(Backpack):
    _texture_path = "gui.container.crafting_table"
    crafting_columns = 3
    crafting_rows = 3
    crafting_offset = (29, 17)
    crafting_output_offset = (124, 35)
    quick_move_screen = "crafting_table"
