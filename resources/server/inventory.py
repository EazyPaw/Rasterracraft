from resources.server.item_class import ItemStack, EmptyItemStack
from resources.server.materials import get_material_by_id


def serialize_inventory(inventory) -> list[dict]:
    """Convert an inventory into the packet/save representation.

    Materials are persisted by their stable ``name_id`` rather than by Python
    class, so this remains compatible across processes and future sessions.
    """
    return [
        {
            "id": getattr(stack.material, "name_id", "air"),
            "amount": max(0, int(getattr(stack, "amount", 0))),
            "nbt": getattr(stack, "nbt", {}) if isinstance(getattr(stack, "nbt", {}), dict) else {},
        }
        for stack in inventory
    ]


def normalize_inventory_payload(payload, size: int = 36) -> list[dict]:
    """Validate a wire/save inventory and return exactly ``size`` slots."""
    entries = payload if isinstance(payload, list) else []
    normalized: list[dict] = []
    for entry in entries[:size]:
        entry = entry if isinstance(entry, dict) else {}
        material = get_material_by_id(entry.get("id", "air"))
        try:
            amount = int(entry.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0
        amount = max(0, min(amount, material.max_stack_size))
        if getattr(material, "name_id", "air") == "air" or amount == 0:
            normalized.append({"id": "air", "amount": 0, "nbt": {}})
        else:
            normalized.append({
                "id": material.name_id,
                "amount": amount,
                "nbt": entry.get("nbt", {}) if isinstance(entry.get("nbt", {}), dict) else {},
            })
    normalized.extend({"id": "air", "amount": 0, "nbt": {}} for _ in range(size - len(normalized)))
    return normalized


def restore_inventory(inventory, payload) -> None:
    """Replace the contents of an ``Inventory`` from saved packet data."""
    for slot, entry in enumerate(normalize_inventory_payload(payload, len(inventory))):
        inventory[slot] = ItemStack(
            get_material_by_id(entry["id"]), entry["amount"], entry["nbt"],
        )


def stack_to_payload(stack: ItemStack) -> dict:
    return serialize_inventory([stack])[0]


def payload_to_stack(payload) -> ItemStack:
    entry = normalize_inventory_payload([payload], 1)[0]
    return ItemStack(get_material_by_id(entry["id"]), entry["amount"], entry["nbt"])


class Inventory:
    def __init__(self, max_slots: int = 9):
        self._items: list[ItemStack] = []
        self.selected_slot = 0
        self.max_slots = max_slots
        for i in range(self.max_slots):
            self._items.append(EmptyItemStack())

    def __getitem__(self, item):
        if not(0 <= item < self.max_slots):
            raise IndexError("Inventory index out of range")
        return self._items[item]

    def __setitem__(self, index, value):
        if not(0 <= index < self.max_slots):
            raise IndexError("Inventory index out of range")
        self._items[index] = value

    def __len__(self):
        return len(self._items)

    def is_full(self) -> bool:
        """
        返回物品栏是否已经被占满
        :return:
        """
        return all(not stack.is_empty() for stack in self._items)

    def get_first_empty_slot(self) -> int:
        """
        返回物品栏中第一个空槽的索引
        :return: 如果物品栏已满则返回 -1
        """
        for i in range(self.max_slots):
            if self._items[i].is_empty():
                return i
        return -1

    def add_item(self, item: ItemStack, put_in_empty_slot: bool = False) -> bool:
        """
        向物品栏中添加物品，返回是否添加成功
        :param put_in_empty_slot: 是否强制放在一个新的物品栏内，默认为 False
        :param item: 添加的 ItemStack
        :return:
        """
        if item.amount <= 0 or item.is_empty():
            return True
        if put_in_empty_slot:
            slot = next((i for i in range(self.max_slots) if self[i].is_empty()), -1)
            if slot == -1:
                return False
            moved = min(item.amount, item.max_stack_size)
            self[slot] = ItemStack(item.material, moved, item.nbt)
            item.amount -= moved
            return item.amount <= 0
        else:
            for i in range(self.max_slots):
                target = self[i]
                if target.is_empty():
                    continue
                space = target.max_stack_size - target.amount
                if target.material == item.material and target.nbt == item.nbt and space > 0:
                    moved = min(space, item.amount)
                    target.amount += moved
                    item.amount -= moved
                    if item.amount <= 0:
                        return True
            for i in range(self.max_slots):
                if self[i].is_empty():
                    moved = min(item.amount, item.max_stack_size)
                    self[i] = ItemStack(item.material, moved, item.nbt)
                    item.amount -= moved
                    if item.amount <= 0:
                        return True
            return False

    def set_item(self, solt, item: ItemStack):
        self[solt] = item


