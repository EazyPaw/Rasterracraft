"""Data-driven furnace recipes and vanilla-style fuel values."""

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from resources.server.item_class import ItemStack
from resources.server.materials import get_material_by_id


RECIPES_ROOT = Path("data/minecraft/recipes")
ITEM_TAGS_ROOT = Path("data/minecraft/tags/items")


@dataclass(frozen=True)
class SmeltingRecipe:
    ingredient: object
    result_id: str
    cooking_time: int
    experience: float

    def create_result(self) -> ItemStack | None:
        material = get_material_by_id(self.result_id)
        if getattr(material, "name_id", "air") == "air":
            return None
        return ItemStack(material, 1)


def _material_id(stack: ItemStack | None) -> str | None:
    if stack is None or stack.is_empty():
        return None
    return getattr(stack.material, "name_id", None)


def ingredient_matches(stack: ItemStack | None, ingredient) -> bool:
    """Match the item/list/tag forms used by Minecraft recipe JSON."""
    if isinstance(ingredient, list):
        return any(ingredient_matches(stack, option) for option in ingredient)
    if not isinstance(ingredient, dict) or stack is None or stack.is_empty():
        return False

    item_id = _material_id(stack)
    expected = ingredient.get("item")
    if expected:
        return item_id == str(expected).removeprefix("minecraft:")

    tag = str(ingredient.get("tag", "")).removeprefix("minecraft:")
    if not tag:
        return False
    material_tags = {
        getattr(value, "value", str(value))
        for value in getattr(stack.material, "Tags", ())
    }
    if tag in material_tags:
        return True
    if item_id in load_item_tag(tag):
        return True
    if tag == "logs":
        return bool(item_id and item_id.endswith("_log"))
    if tag.endswith("_logs"):
        return item_id == tag[:-1]
    return False


@lru_cache(maxsize=None)
def load_item_tag(tag: str) -> frozenset[str]:
    """Resolve a Minecraft item tag, including nested ``#tag`` entries."""
    tag = str(tag).removeprefix("#").removeprefix("minecraft:")

    def resolve(current: str, resolving: set[str]) -> set[str]:
        current = current.removeprefix("#").removeprefix("minecraft:")
        if current in resolving:
            return set()
        path = ITEM_TAGS_ROOT / f"{current}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        resolving.add(current)
        values: set[str] = set()
        for entry in data.get("values", []):
            if isinstance(entry, dict):
                entry = entry.get("id", "")
            entry = str(entry)
            if entry.startswith("#"):
                values.update(resolve(entry, resolving))
            elif entry:
                values.add(entry.removeprefix("minecraft:"))
        resolving.discard(current)
        return values

    return frozenset(resolve(tag, set()))


@lru_cache(maxsize=1)
def load_smelting_recipes() -> tuple[SmeltingRecipe, ...]:
    recipes: list[SmeltingRecipe] = []
    for path in RECIPES_ROOT.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("type") != "minecraft:smelting":
            continue
        result = data.get("result", "minecraft:air")
        if isinstance(result, dict):
            result = result.get("id", result.get("item", "minecraft:air"))
        recipes.append(SmeltingRecipe(
            ingredient=data.get("ingredient", {}),
            result_id=str(result).removeprefix("minecraft:"),
            cooking_time=max(1, int(data.get("cookingtime", 200))),
            experience=max(0.0, float(data.get("experience", 0.0))),
        ))
    logging.info("Loaded %d furnace recipes", len(recipes))
    return tuple(recipes)


def find_smelting_recipe(stack: ItemStack | None) -> SmeltingRecipe | None:
    if stack is None or stack.is_empty():
        return None
    for recipe in load_smelting_recipes():
        if ingredient_matches(stack, recipe.ingredient):
            return recipe
    return None


def get_fuel_burn_time(stack: ItemStack | None) -> int:
    """Return one item's Java-furnace burn duration in game ticks."""
    item_id = _material_id(stack)
    if not item_id:
        return 0
    explicit = {
        "lava_bucket": 20_000,
        "coal_block": 16_000,
        "dried_kelp_block": 4_000,
        "blaze_rod": 2_400,
        "coal": 1_600,
        "charcoal": 1_600,
        "bamboo": 50,
        "stick": 100,
        "bowl": 100,
        "wool": 100,
    }
    if item_id in explicit:
        return explicit[item_id]
    if item_id.endswith("_wool"):
        return 100
    if item_id.endswith("_slab") and any(
        wood in item_id
        for wood in ("oak", "birch", "spruce", "jungle", "acacia", "dark_oak")
    ):
        return 150
    if item_id.endswith(("_log", "_plank", "_planks")):
        return 300
    if item_id in {
        "crafting_table", "chest", "trapped_chest", "bookshelf",
        "jukebox", "note_block", "ladder",
    }:
        return 300
    if item_id.startswith("wooden_") or item_id in {
        "bow", "fishing_rod", "sign", "oak_sign",
    }:
        return 200
    return 0


def is_fuel(stack: ItemStack | None) -> bool:
    return get_fuel_burn_time(stack) > 0
