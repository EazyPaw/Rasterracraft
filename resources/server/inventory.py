from resources.server.item_class import ItemStack, EmptyItemStack


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
        return len(self._items) >= self.max_slots

    def get_first_empty_slot(self) -> int:
        """
        返回物品栏中第一个空槽的索引
        :return: 如果物品栏已满则返回 -1
        """
        for i in range(self.max_slots):
            if self._items[i] is None:
                return i
        return -1

    def add_item(self, item: ItemStack, put_in_empty_slot: bool = False) -> bool:
        """
        向物品栏中添加物品，返回是否添加成功
        :param put_in_empty_slot: 是否强制放在一个新的物品栏内，默认为 False
        :param item: 添加的 ItemStack
        :return:
        """
        if self.is_full():
            return False
        if put_in_empty_slot:
            slot = self.get_first_empty_slot()
            if slot == -1:
                return False
            self[slot] = item
            return True
        else:
            for i in range(self.max_slots):
                if self[i].stack_item(item):
                    return True
            return False

    def set_item(self, solt, item: ItemStack):
        self[solt] = item


