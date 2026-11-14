"""Private, server-owned enchanting/anvil sessions integrated with Inventory."""
import random
import uuid

from src.server.enchanting import JavaRandom, anvil_result, table_offers
from src.server.inventory import Inventory, serialize_inventory
from src.server.item_class import EmptyItemStack, ItemStack
from src.server.materials import get_material_by_id


def is_creative(player):
    return getattr(player.gamemode, "name_id", "survival") == "creative"


def spend_levels(player, levels):
    # 1.8 removes levels while preserving the fraction of the current XP bar.
    fraction = player.experience / player.experience_to_next_level()
    player.experience_level = max(0, player.experience_level - levels)
    player.experience = int(fraction * player.experience_to_next_level())
    player.sync_experience()


def count_bookshelves(block):
    """Two sides, two heights, both depth layers: eight reachable shelves.

    Each side/depth column needs a two-block-high air gap, as in vanilla.
    """
    loc = block.location
    count = 0
    for side in (-1, 1):
        for z in (0, 1):
            if any(loc.world.get_block(int(loc.x) + side, int(loc.y) + dy, z).block_id != "air"
                   for dy in (0, 1)):
                continue
            for dy in (0, 1):
                if loc.world.get_block(int(loc.x) + side * 2, int(loc.y) + dy, z).block_id == "bookshelf":
                    count += 1
    return min(8, count)


class WorkstationInventory(Inventory):
    def __init__(self, owner, player):
        kind = getattr(owner, "workstation_kind", owner.block_id)
        super().__init__(3 if kind == "anvil" else 2)
        self.owner_block = owner
        self.player = player
        self.container_id = "workstation:" + uuid.uuid4().hex
        self.kind = kind
        self.name = None
        self.cost = 0
        self.material_cost = 0
        self.shelves = 0
        self.offers = [(0, {}) for _ in range(3)]
        self.closed = False
        self._input_signature = None

    def can_place(self, slot, stack):
        if stack.is_empty():
            return slot != 2
        if self.kind == "anvil":
            return slot in (0, 1)
        return slot == 0 or (slot == 1 and stack.material.name_id == "lapis_lazuli")

    def slot_limit(self, slot, stack):
        return 1 if self.kind == "enchanting_table" and slot == 0 else stack.max_stack_size

    def can_take(self, slot, player):
        if self.kind != "anvil" or slot != 2:
            return True
        self.refresh()
        return not self[2].is_empty() and self.cost > 0 and (is_creative(player) or player.experience_level >= self.cost)

    def refresh(self):
        if self.kind == "anvil":
            signature = (self[0].material.name_id, repr(self[0].nbt))
            if signature != self._input_signature:
                self.name = None
                self._input_signature = signature
            result = anvil_result(self[0], self[1], self.name, is_creative(self.player))
            self[2], self.cost, self.material_cost = result.stack, result.cost, result.materials
        else:
            self.shelves = count_bookshelves(self.owner_block)
            self.offers = table_offers(self[0], self.shelves, self.player.enchantment_seed)

    def packet(self, packet_class="WorkstationUpdate"):
        self.refresh()
        hints = []
        for index, (cost, levels) in enumerate(self.offers):
            clue = list(levels.items())
            hint = clue[JavaRandom(self.player.enchantment_seed + index).randrange(len(clue))] if clue else None
            hints.append({"level": cost, "lapis": index + 1,
                          "hint": list(hint) if hint else None})
        return {"__class__": packet_class, "container": self.container_id, "kind": self.kind,
                "slots": serialize_inventory(self), "cost": self.cost,
                "name": self.name if self.name is not None else self[0].nbt.get("display", {}).get("Name", ""),
                "bookshelves": self.shelves, "offers": hints,
                "glyph_seed": self.player.enchantment_seed & ~15}

    def send(self, packet_class="WorkstationUpdate"):
        if not self.closed:
            self.player.world.server.send_client_socket(self.player, self.packet(packet_class), "Forward")

    def on_changed(self):
        self.send()

    def tick(self):
        if self.kind == "enchanting_table" and self.shelves != count_bookshelves(self.owner_block):
            self.send()

    def enchant(self, option):
        if self.kind != "enchanting_table" or option not in (0, 1, 2):
            return
        self.refresh()
        cost, levels = self.offers[option]
        price = option + 1
        creative = is_creative(self.player)
        if not cost or not levels or (not creative and (self.player.experience_level < max(cost, price)
                or self[1].material.name_id != "lapis_lazuli" or self[1].amount < price)):
            self.send()
            return
        if self[0].material.name_id == "book":
            self[0] = ItemStack(get_material_by_id("enchanted_book"), 1, self[0].nbt.copy())
        for key, level in levels.items():
            self[0].set_enchantment(key, level)
        if not creative:
            self[1].amount -= price
            if self[1].amount <= 0:
                self[1] = EmptyItemStack()
        spend_levels(self.player, price)
        loc = self.owner_block.location
        loc.world.server.broadcast_sound("block.enchantment_table.use", loc.x + .5, loc.y + .5,
                                         loc.z, world=loc.world)
        self.player.enchantment_seed = random.randrange(-(1 << 31), 1 << 31)
        self.send()
        self.player.sync_inventory()

    def rename(self, name):
        if self.kind != "anvil" or not isinstance(name, str) or len(name) > 30:
            return
        self.refresh()
        self.name = "".join(char for char in name if char >= " " and char != "\u00a7")
        self.send()

    def on_take(self, slot, amount, player=None):
        if self.kind != "anvil" or slot != 2:
            return
        if not is_creative(self.player):
            spend_levels(self.player, self.cost)
        self[0] = EmptyItemStack()
        if self.material_cost:
            self[1].amount -= self.material_cost
            if self[1].amount <= 0:
                self[1] = EmptyItemStack()
        else:
            self[1] = EmptyItemStack()
        self[2] = EmptyItemStack()
        owner = self.owner_block
        sound = "random.anvil_use"
        if not is_creative(self.player) and random.random() < .12:
            owner.damage += 1
            if owner.damage > 2:
                sound = "random.anvil_break"
                from src.server.blocks import AIR
                owner.close_all_viewers()
                owner.location.world.set_block(AIR(), owner.location)
            else:
                owner.notify_state_changed()
        loc = owner.location
        loc.world.server.broadcast_sound(sound, loc.x, loc.y, loc.z, world=loc.world)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.player.unregister_inventory_container(self.container_id)
        self.owner_block._viewers.discard(self.player)
        # Only inputs are real items; anvil output is a preview until taken.
        for index in range(2):
            stack = self[index]
            if not stack.is_empty():
                self.player.inventory.insert_stack(stack)
                if not stack.is_empty():
                    self.player.drop_item_stack(stack, pickup_delay=0)
            self[index] = EmptyItemStack()
        self.player.sync_inventory()
        self.player.world.server.send_client_socket(self.player,
            {"__class__": "WorkstationClosed", "container": self.container_id}, "Forward")


class WorkstationBlockMixin:
    closed_packet_class = "WorkstationClosed"

    def __init__(self, nbt=None):
        self._viewers = set()
        self.damage = getattr(self, "initial_damage", 0)
        super().__init__(nbt)

    def on_right_click(self, player):
        for container in tuple(player.open_inventory_containers.values()):
            owner = getattr(container, "owner_block", getattr(container, "furnace", None))
            if owner is not None:
                owner.close_for(player)
        session = WorkstationInventory(self, player)
        self._viewers.add(player)
        player.register_inventory_container(session.container_id, session)
        session.send("WorkstationOpen")
        return True

    def close_for(self, player):
        for container in tuple(player.open_inventory_containers.values()):
            if getattr(container, "owner_block", None) is self:
                container.close()

    def close_all_viewers(self):
        for player in tuple(self._viewers):
            self.close_for(player)

    def on_break(self):
        self.close_all_viewers()

    def on_unload(self):
        self.close_all_viewers()
