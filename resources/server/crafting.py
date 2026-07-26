# Commented and arranged by ChatGPT

import json
import logging
from functools import lru_cache
from pathlib import Path

from resources.server.item_class import EmptyItemStack, ItemStack
from resources.server.materials import get_material_by_id
from resources.server.smelting import ingredient_matches
from resources.server.tags import ItemTag


RECIPES_ROOT = Path("data/minecraft/recipes")


def _item_id(stack) -> str | None:
    if stack is None or stack.is_empty():
        return None
    return stack.material.name_id


def _matches_ingredient(stack: ItemStack | None, ingredient: dict) -> bool:
    if isinstance(ingredient, list):
        return any(_matches_ingredient(stack, option) for option in ingredient)
    if not isinstance(ingredient, dict):
        return False
    if stack is None or stack.is_empty():
        return False
    item_id = _item_id(stack)
    expected = ingredient.get("item")
    if expected:
        return item_id == str(expected).removeprefix("minecraft:") or (
            str(expected).removeprefix("minecraft:") == "oak_planks"
            and item_id == "oak_plank"
        )
    tag = str(ingredient.get("tag", "")).removeprefix("minecraft:")
    if tag == "planks":
        return item_id.endswith("_plank") or item_id.endswith("_planks")
    if tag == "logs":
        return item_id.endswith("_log")
    if tag.endswith("_logs"):
        return item_id == tag[:-1]
    if tag == "stone_tool_materials":
        return ItemTag.COBBLESTONE in getattr(stack.material, "Tags", ())
    if tag == "stone_crafting_materials":
        return ItemTag.COBBLESTONE in getattr(stack.material, "Tags", ())
    return ingredient_matches(stack, ingredient)


def _trim(grid: list[list[ItemStack | None]]) -> list[list[ItemStack | None]]:
    rows = [row[:] for row in grid]
    while rows and not any(rows[0]):
        rows.pop(0)
    while rows and not any(rows[-1]):
        rows.pop()
    if not rows:
        return []
    while rows and not any(row[0] for row in rows):
        rows = [row[1:] for row in rows]
    while rows and not any(row[-1] for row in rows):
        rows = [row[:-1] for row in rows]
    return rows


@lru_cache(maxsize=1)
def load_recipes() -> tuple[dict, ...]:
    recipes = []
    for path in RECIPES_ROOT.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("type") in {
            "minecraft:crafting_shaped",
            "minecraft:crafting_shapeless",
        }:
            recipes.append(data)
    logging.info(f"Loaded {len(recipes)} recipes")
    return tuple(recipes)


def find_recipe(
    stacks: list[ItemStack], width: int, height: int
) -> tuple[ItemStack, list[int]] | None:
    grid = [
        [
            None if stacks[row * width + col].is_empty() else stacks[row * width + col]
            for col in range(width)
        ]
        for row in range(height)
    ]
    compact = _trim(grid)
    if not compact:
        return None
    for recipe in load_recipes():
        if recipe["type"] == "minecraft:crafting_shaped":
            pattern = recipe.get("pattern", [])
            if (
                len(pattern) != len(compact)
                or not pattern
                or len(pattern[0]) != len(compact[0])
            ):
                continue
            key = recipe.get("key", {})
            valid = True
            for row, line in enumerate(pattern):
                for col, char in enumerate(line):
                    stack = compact[row][col]
                    if char == " ":
                        valid = valid and stack is None
                    else:
                        valid = valid and _matches_ingredient(stack, key.get(char, {}))
                    if not valid:
                        break
                if not valid:
                    break
            if not valid:
                continue
        else:
            present = [stack for row in compact for stack in row if stack is not None]
            ingredients = recipe.get("ingredients", [])
            if len(present) != len(ingredients):
                continue
            remaining = present[:]
            for ingredient in ingredients:
                index = next(
                    (
                        i
                        for i, stack in enumerate(remaining)
                        if _matches_ingredient(stack, ingredient)
                    ),
                    -1,
                )
                if index < 0:
                    break
                remaining.pop(index)
            if remaining:
                continue
            if len(remaining) != 0:
                continue
        result = recipe.get("result", {})
        material = get_material_by_id(result.get("item", "air"))
        if material.name_id == "air":
            continue
        return ItemStack(material, int(result.get("count", 1))), [
            i for i, stack in enumerate(stacks) if not stack.is_empty()
        ]
    return None
