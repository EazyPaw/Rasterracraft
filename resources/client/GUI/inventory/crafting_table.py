from resources.client.GUI.inventory.backpack import Backpack


class CraftingTable(Backpack):
    """Workbench UI: the normal inventory plus the data-driven 3×3 grid."""
    _texture_path = "gui.container.crafting_table"
    crafting_columns = 3
    crafting_rows = 3
    crafting_offset = (29, 17)
    crafting_output_offset = (124, 35)
