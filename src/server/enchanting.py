"""Minecraft 1.8.9 EnchantmentHelper / ContainerRepair rules.

The sole table-power adaptation is eight bookshelves instead of fifteen.
All results and costs are computed on the server, never accepted from clients.
"""
from dataclasses import dataclass
import math

from src.server.enchantments import get_enchantment
from src.server.inventory import Inventory
from src.server.item_class import EmptyItemStack


class JavaRandom:
    """java.util.Random, so seeds and weighted rolls use the original algorithm."""
    def __init__(self, seed):
        self.seed = (int(seed) ^ 0x5DEECE66D) & ((1 << 48) - 1)

    def bits(self, count):
        self.seed = (self.seed * 0x5DEECE66D + 11) & ((1 << 48) - 1)
        return self.seed >> (48 - count)

    def randrange(self, bound):
        if bound <= 0:
            raise ValueError("positive bound required")
        if bound & (bound - 1) == 0:
            return (bound * self.bits(31)) >> 31
        while True:
            bits = self.bits(31)
            value = bits % bound
            if bits - value + bound - 1 < (1 << 31):
                return value

    def random(self):
        return self.bits(24) / float(1 << 24)


# id: weight, minimum base, minimum per level, maximum window.
# None windows call Enchantment.getMinEnchantability(level) + 50 in MCP 919.
RULES = {
    "protection": (10, 1, 11, 20), "fire_protection": (5, 10, 8, 12),
    "feather_falling": (5, 5, 6, 10), "blast_protection": (2, 5, 8, 12),
    "projectile_protection": (5, 3, 6, 15), "respiration": (2, 10, 10, 30),
    "aqua_affinity": (2, 1, 0, 40), "thorns": (1, 10, 20, None),
    "depth_strider": (2, 10, 10, 15), "sharpness": (10, 1, 11, 20),
    "smite": (5, 5, 8, 20), "bane_of_arthropods": (5, 5, 8, 20),
    "knockback": (5, 5, 20, None), "fire_aspect": (2, 10, 20, None),
    "looting": (2, 15, 9, None), "efficiency": (10, 1, 10, None),
    "silk_touch": (1, 15, 0, None), "unbreaking": (5, 5, 8, None),
    "fortune": (2, 15, 9, None), "power": (10, 1, 10, 15),
    "punch": (2, 12, 20, 25), "flame": (2, 20, 0, 30),
    "infinity": (1, 20, 0, 30), "luck_of_the_sea": (2, 15, 9, None),
    "lure": (2, 15, 9, None),
}


def compatible(first, second):
    a, b = first.split(":")[-1], second.split(":")[-1]
    if a == b:
        return False
    for group in ({"sharpness", "smite", "bane_of_arthropods"},
                  {"protection", "fire_protection", "blast_protection", "projectile_protection"},
                  {"silk_touch", "fortune"}):
        if a in group and b in group:
            return False
    return True


def enchantability(stack):
    material = stack.material
    if material.name_id == "book":
        return 1
    if not stack.is_damageable() or stack.amount != 1:
        return 0
    from src.server.materials import Armor, Tool
    if isinstance(material, Armor):
        return {"leather": 15, "chainmail": 12, "iron": 9, "golden": 25,
                "diamond": 10}.get(material.name_id.split("_")[0], 0)
    if isinstance(material, Tool) and material.tool_type != "hoe":
        return {"wood": 15, "stone": 5, "iron": 14, "gold": 22, "diamond": 10}.get(material.tier, 0)
    return 1 if material.name_id in {"bow", "fishing_rod"} else 0


def table_supports(enchantment, stack):
    name = enchantment.id.split(":")[-1]
    if stack.material.name_id == "book":
        return True
    if name in {"sharpness", "smite", "bane_of_arthropods"}:
        return getattr(stack.material, "tool_type", None) == "sword"
    if name == "thorns":
        return getattr(stack.material, "equipment_slot", None) == "chest"
    return enchantment.supports(stack)


def build_enchantments(stack, cost, rng):
    ability = enchantability(stack)
    if ability <= 0:
        return {}
    bonus = 1 + rng.randrange(ability // 4 + 1) + rng.randrange(ability // 4 + 1)
    power = max(1, math.floor((cost + bonus) * (1 + (rng.random() + rng.random() - 1) * .15) + .5))
    candidates = {}
    # Numeric enchantment order, also used by the original registry.
    for name, (weight, base, step, window) in RULES.items():
        enchantment = get_enchantment(name)
        if enchantment is None or not table_supports(enchantment, stack):
            continue
        for level in range(1, enchantment.max_level + 1):
            low = base + step * (level - 1)
            high = low + window if window is not None else 1 + level * 10 + 50
            if low <= power <= high:
                candidates[enchantment.id] = (level, weight)
    result = {}
    def choose():
        roll = rng.randrange(sum(weight for _, weight in candidates.values()))
        for key, (level, weight) in candidates.items():
            roll -= weight
            if roll < 0:
                result[key] = level
                return
    if candidates:
        choose()
        while rng.randrange(50) <= power:
            candidates = {key: value for key, value in candidates.items()
                          if all(compatible(key, chosen) for chosen in result)}
            if candidates:
                choose()
            power >>= 1
    if stack.material.name_id == "book" and len(result) > 1:
        del result[list(result)[rng.randrange(len(result))]]
    return result


def table_offers(stack, shelves, seed):
    if stack.is_empty() or stack.has_enchantments() or enchantability(stack) == 0:
        return [(0, {}) for _ in range(3)]
    power = min(15, max(0, int(shelves)) * 15 // 8)
    rng = JavaRandom(seed)
    costs = []
    for index in range(3):
        base = rng.randrange(8) + 1 + (power >> 1) + rng.randrange(power + 1)
        cost = (max(base // 3, 1), base * 2 // 3 + 1, max(base, power * 2))[index]
        costs.append(cost if cost >= index + 1 else 0)
    return [(cost, build_enchantments(stack, cost, JavaRandom(seed + index)))
            for index, cost in enumerate(costs)]


def repair_ingredient(stack, ingredient):
    name = stack.material.name_id
    other = ingredient.material.name_id
    if name.startswith(("wooden_",)):
        return other.endswith(("_plank", "_planks"))
    prefix = name.split("_")[0]
    return other == {"stone": "cobblestone", "iron": "iron_ingot", "chainmail": "iron_ingot",
                     "golden": "gold_ingot", "diamond": "diamond", "leather": "leather"}.get(prefix)


@dataclass
class AnvilResult:
    stack: object
    cost: int = 0
    materials: int = 0


def anvil_result(left, right, name=None, creative=False):
    """Port of ContainerRepair.updateRepairOutput (including 1.8 rename penalty)."""
    if left.is_empty():
        return AnvilResult(EmptyItemStack())
    output = Inventory.copy_stack(left)
    levels = left.get_enchantments()
    prior = max(0, int(left.nbt.get("RepairCost", 0)))
    right_prior = max(0, int(right.nbt.get("RepairCost", 0))) if not right.is_empty() else 0
    work = used = rename = 0
    if not right.is_empty():
        book = right.material.name_id == "enchanted_book" and right.has_enchantments()
        if left.is_damageable() and repair_ingredient(left, right):
            while used < right.amount and output.get_damage() > 0:
                repair = min(output.get_damage(), left.get_max_damage() // 4)
                if repair <= 0:
                    break
                output.set_damage(output.get_damage() - repair)
                used += 1
                work += 1
            if not used:
                return AnvilResult(EmptyItemStack())
        else:
            if not book and (left.material != right.material or not left.is_damageable()):
                return AnvilResult(EmptyItemStack())
            if left.is_damageable() and not book:
                damage = max(0, left.get_damage() - right.get_remaining_durability() - left.get_max_damage() * 12 // 100)
                if damage < output.get_damage():
                    output.set_damage(damage)
                    work += 2
            for key, level in right.get_enchantments().items():
                enchantment = get_enchantment(key)
                if enchantment is None:
                    continue
                old = levels.get(key, 0)
                level = min(enchantment.max_level, level + 1 if old == level else max(old, level))
                allowed = creative or left.material.name_id == "enchanted_book" or enchantment.supports(left)
                for existing in levels:
                    if existing != key and not compatible(key, existing):
                        allowed = False
                        work += 1
                if allowed:
                    levels[key] = level
                    weight = RULES.get(key.split(":")[-1], (2,))[0]
                    multiplier = {1: 8, 2: 4, 5: 2, 10: 1}.get(weight, 0)
                    work += max(1, multiplier // 2) * level if book else multiplier * level
    current_name = left.nbt.get("display", {}).get("Name", "")
    if name is not None and name != current_name and (name.strip() or current_name):
        rename = 1
        work += 1
        display = output.nbt.setdefault("display", {})
        if name.strip():
            display["Name"] = name
        else:
            display.pop("Name", None)
    cost = prior + right_prior + work
    if rename == work and rename > 0 and cost >= 40:
        cost = 39
    if work <= 0 or (cost >= 40 and not creative):
        return AnvilResult(EmptyItemStack(), cost)
    output.nbt["RepairCost"] = max(prior, right_prior) * 2 + 1
    output.nbt["minecraft:enchantments"] = {"levels": levels}
    output.nbt.pop("enchantments", None)
    output.nbt.pop("Enchantments", None)
    return AnvilResult(output, cost, used)
