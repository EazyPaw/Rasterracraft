# Commented and arranged by ChatGPT
from copy import deepcopy

from resources.server.item_class import ItemStack, EmptyItemStack
from resources.server.materials import get_material_by_id


def serialize_inventory(inventory) -> list[dict]:
    return [
        {
            "id": getattr(stack.material, "name_id", "air"),
            "amount": max(0, int(getattr(stack, "amount", 0))),
            "nbt": getattr(stack, "nbt", {})
            if isinstance(getattr(stack, "nbt", {}), dict)
            else {},
        }
        for stack in inventory
    ]


def normalize_inventory_payload(payload, size: int = 36) -> list[dict]:
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
            normalized.append(
                {
                    "id": material.name_id,
                    "amount": amount,
                    "nbt": entry.get("nbt", {})
                    if isinstance(entry.get("nbt", {}), dict)
                    else {},
                }
            )
    normalized.extend(
        {"id": "air", "amount": 0, "nbt": {}} for _ in range(size - len(normalized))
    )
    return normalized


def restore_inventory(inventory, payload) -> None:
    for slot, entry in enumerate(normalize_inventory_payload(payload, len(inventory))):
        inventory[slot] = ItemStack(
            get_material_by_id(entry["id"]),
            entry["amount"],
            entry["nbt"],
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
        if not (0 <= item < self.max_slots):
            raise IndexError("Inventory index out of range")
        return self._items[item]

    def __setitem__(self, index, value):
        if not (0 <= index < self.max_slots):
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

    def _normalize_slots(self, slots=None) -> list[int]:
        if slots is None:
            return list(range(self.max_slots))
        result = []
        for slot in slots:
            try:
                slot = int(slot)
            except (TypeError, ValueError):
                continue
            if 0 <= slot < self.max_slots and slot not in result:
                result.append(slot)
        return result

    def can_place(self, slot: int, stack: ItemStack) -> bool:
        return True

    @staticmethod
    def copy_stack(stack: ItemStack, amount: int | None = None) -> ItemStack:
        if amount is None:
            amount = stack.amount
        return ItemStack(stack.material, int(amount), deepcopy(stack.nbt))

    def capacity_for(self, stack: ItemStack, slots=None) -> int:
        if stack is None or stack.is_empty() or stack.amount <= 0:
            return 0
        capacity = 0
        for slot in self._normalize_slots(slots):
            target = self[slot]
            if target.is_empty():
                capacity += stack.max_stack_size
            elif target.is_stackable_with(stack, require_full_fit=False):
                capacity += max(0, target.max_stack_size - target.amount)
        return capacity

    def insert_stack(self, stack: ItemStack, slots=None) -> int:
        if stack is None or stack.is_empty() or stack.amount <= 0:
            return 0
        ordered_slots = self._normalize_slots(slots)
        before = stack.amount

        for slot in ordered_slots:
            target = self[slot]
            if not self.can_place(slot, stack):
                continue
            if target.is_empty() or not target.is_stackable_with(
                stack, require_full_fit=False
            ):
                continue
            moved = min(
                stack.amount,
                max(0, target.max_stack_size - target.amount),
            )
            if moved <= 0:
                continue
            target.amount += moved
            stack.amount -= moved
            if stack.amount <= 0:
                return before

        for slot in ordered_slots:
            if not self.can_place(slot, stack):
                continue
            if not self[slot].is_empty():
                continue
            moved = min(stack.amount, stack.max_stack_size)
            self[slot] = self.copy_stack(stack, moved)
            stack.amount -= moved
            if stack.amount <= 0:
                break
        return before - max(0, stack.amount)

    def transfer_stack_to(
        self, source_slot: int, destination: "Inventory", destination_slots=None
    ) -> int:
        source_slot = int(source_slot)
        if not 0 <= source_slot < self.max_slots:
            return 0
        source = self[source_slot]
        if source.is_empty() or source.amount <= 0:
            return 0
        slots = destination._normalize_slots(destination_slots)
        if destination is self:
            slots = [slot for slot in slots if slot != source_slot]
        moved = destination.insert_stack(source, slots)
        if source.amount <= 0:
            self[source_slot] = EmptyItemStack()
        return moved

    def swap_slots(
        self, source_slot: int, destination: "Inventory", destination_slot: int
    ) -> bool:
        source_slot = int(source_slot)
        destination_slot = int(destination_slot)
        if not 0 <= source_slot < self.max_slots:
            return False
        if not 0 <= destination_slot < len(destination):
            return False
        if self is destination and source_slot == destination_slot:
            return False
        self[source_slot], destination[destination_slot] = (
            destination[destination_slot],
            self[source_slot],
        )
        return True

    def consolidate_matching(
        self, reference: ItemStack, source_slots=None, destination_slots=None
    ) -> int:
        if reference is None or reference.is_empty():
            return 0
        sources = self._normalize_slots(source_slots)
        matching = [
            slot
            for slot in sources
            if not self[slot].is_empty()
            and self[slot].is_stackable_with(reference, require_full_fit=False)
        ]
        if not matching:
            return 0
        original = [(slot, self.copy_stack(self[slot])) for slot in matching]
        total = sum(stack.amount for _, stack in original)
        moving = self.copy_stack(reference, total)
        for slot in matching:
            self[slot] = EmptyItemStack()

        inserted = self.insert_stack(moving, destination_slots)
        if moving.amount > 0:
            restore_slots = [slot for slot, _ in original if self[slot].is_empty()]
            self.insert_stack(moving, restore_slots)
        return inserted

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
        self.insert_stack(item)
        return item.amount <= 0

    def set_item(self, solt, item: ItemStack):
        self[solt] = item
