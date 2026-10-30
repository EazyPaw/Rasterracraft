"""Template-based Nether fortresses, using the same placement path as villages.

Plans read original templates only. Each chunk applies its own slice before
block initialization; neither chunk order nor player edits affect a plan.
"""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path

from src.server.block_class import ConnectableBarrier
from src.server.blocks import get_block_by_id
from src.server.item_class import ItemStack
from src.server.location import Location
from src.server.materials import get_material_by_id
from src.server.structure import iter_structure_blocks, load_structure_data


POOL_PATH = Path(__file__).resolve().parents[3] / "worldgen/nether_fortress.json"
FORTRESS_LOOT = (
    ("diamond", 1, 3, 5), ("iron_ingot", 1, 5, 5), ("gold_ingot", 1, 3, 15),
    ("golden_sword", 1, 1, 5), ("golden_chestplate", 1, 1, 5),
    ("nether_wart", 3, 7, 5), ("obsidian", 2, 4, 2),
    ("flint_and_steel", 1, 1, 5), ("saddle", 1, 1, 10),
    ("golden_horse_armor", 1, 1, 8), ("iron_horse_armor", 1, 1, 5),
    ("diamond_horse_armor", 1, 1, 3),
)


@dataclass(frozen=True)
class FortressConnector:
    x: int
    y: int
    direction: int
    kind: str
    clearance: int


@dataclass(frozen=True)
class FortressPiece:
    template: str
    x: int
    y: int
    width: int
    height: int
    mirror_x: bool = False

    @property
    def bounds(self):
        return self.x, self.y, self.x + self.width - 1, self.y + self.height - 1


@dataclass(frozen=True)
class FortressPlan:
    center_x: int
    floor_y: int
    pieces: tuple[FortressPiece, ...]
    # Pairs of adjacent entrance cells, useful for validating/editing layouts.
    links: tuple[tuple[FortressConnector, FortressConnector], ...]

    @property
    def location(self):
        return self.center_x, self.floor_y

    @property
    def x_min(self):
        return min(p.x for p in self.pieces)

    @property
    def x_max(self):
        return max(p.x + p.width - 1 for p in self.pieces)


class NetherFortressGenerator:
    SPACING = spacing = 512
    MARGIN = 16

    def __init__(self, generator, height=256, *, enabled=True):
        self.generator = generator
        self.max_height = min(122, height - 1)
        self.enabled = bool(enabled)
        self.plan_for_region = lru_cache(maxsize=256)(self._build_plan)

    @cached_property
    def pool(self):
        with POOL_PATH.open(encoding="utf-8") as stream:
            pool = json.load(stream)
        if pool.get("format_version") != 1:
            raise ValueError("Unsupported Nether fortress pool format")
        pieces = pool.get("pieces", {})
        if not pieces or pool.get("start") not in pieces:
            raise ValueError("Nether fortress pool needs a registered start piece")
        for name, settings in pieces.items():
            if (not isinstance(settings.get("template"), str)
                    or type(settings.get("weight", 1)) is not int or settings.get("weight", 1) <= 0
                    or not isinstance(settings.get("connectors"), list)):
                raise ValueError(f"Invalid Nether fortress pool entry: {name}")
        for role in ("regular", "wart", "blaze", "end"):
            names = pool.get("pools", {}).get(role)
            if not isinstance(names, list) or not names or any(name not in pieces for name in names):
                raise ValueError(f"Nether fortress pool {role} must contain registered piece names")
        return pool

    @cached_property
    def templates(self):
        templates = {}
        for name, settings in self.pool["pieces"].items():
            data = load_structure_data(settings["template"])[1]
            width, height, depth = data["size"]
            if depth != 2 or data.get("entities"):
                raise ValueError(f"Fortress template {name} needs two layers and block-based spawners")
            cells = {(x, y, z): entry for x, y, z, entry in iter_structure_blocks(data, (0, 0, 0))}
            directions = set()
            for connector in settings["connectors"]:
                position = connector.get("pos")
                if (not isinstance(position, list) or len(position) != 3
                        or any(type(value) is not int for value in position)):
                    raise ValueError(f"Invalid fortress connector position in {name}")
                x, y, z = connector["pos"]
                direction = connector["direction"]
                clearance = connector["clearance"]
                if (type(direction) is not int or direction not in (-1, 1) or direction in directions or z != 0
                        or x != (0 if direction == -1 else width - 1)
                        or type(y) is not int or y < 1
                        or type(clearance) is not int or clearance < 3 or y + clearance > height
                        or not isinstance(connector.get("type"), str) or not connector["type"]):
                    raise ValueError(f"Invalid fortress connector in {name}")
                directions.add(direction)
                floor_entry = cells.get((x, y - 1, 0), {"id": "air"})
                floor_block = get_block_by_id(floor_entry["id"])
                if floor_entry.get("nbt"):
                    floor_block.write_nbt(floor_entry["nbt"])
                if not ConnectableBarrier._is_full_connection_block(floor_block):
                    logging.warning(
                        "Fortress connector in %s at %s has no full floor; preserving authored geometry",
                        name, position,
                    )
                if any(cells.get((x, y + dy, 0), {}).get("id") != "air" for dy in range(clearance)):
                    logging.warning(
                        "Fortress connector in %s at %s has non-air or void cells; preserving authored geometry",
                        name, position,
                    )
            if not directions:
                raise ValueError(f"Fortress template {name} has no connectors")
            for position in settings.get("loot_chests", []):
                if cells.get(tuple(position), {}).get("id") != "chest":
                    logging.warning(
                        "Ignoring stale fortress loot marker in %s at %s: no chest in template",
                        name, position,
                    )
            templates[name] = data
        return templates

    def connectors(self, piece):
        result = []
        for entry in self.pool["pieces"][piece.template]["connectors"]:
            x, y, _z = entry["pos"]
            direction = entry["direction"]
            if piece.mirror_x:
                x, direction = piece.width - 1 - x, -direction
            result.append(FortressConnector(piece.x + x, piece.y + y, direction,
                                            entry["type"], entry["clearance"]))
        return tuple(result)

    def _piece(self, name, x, y, mirror=False):
        width, height, _ = self.templates[name]["size"]
        return FortressPiece(name, x, y, width, height, mirror)

    def _attach(self, exit_socket, names, pieces, rng, region):
        # Weighted ordering without replacement permits alternatives when a
        # chosen template does not fit the height or its connector type differs.
        names = list(names)
        ordered = []
        while names:
            name = rng.choices(names, [self.pool["pieces"][n].get("weight", 1) for n in names])[0]
            names.remove(name)
            ordered.append(name)
        for name in ordered:
            mirrors = [False, True] if self.pool["pieces"][name].get("allow_mirror", True) else [False]
            rng.shuffle(mirrors)
            for mirror in mirrors:
                local_piece = self._piece(name, 0, 0, mirror)
                for inlet in self.connectors(local_piece):
                    if (inlet.direction != -exit_socket.direction or inlet.kind != exit_socket.kind
                            or inlet.clearance != exit_socket.clearance):
                        continue
                    piece = self._piece(name, exit_socket.x + exit_socket.direction - inlet.x,
                                        exit_socket.y - inlet.y, mirror)
                    x1, y1, x2, y2 = piece.bounds
                    if (x1 < region * self.SPACING + self.MARGIN
                            or x2 >= (region + 1) * self.SPACING - self.MARGIN
                            or y1 < 5 or y2 >= self.max_height):
                        continue
                    if any(not (x2 < p.bounds[0] or x1 > p.bounds[2]
                                or y2 < p.bounds[1] or y1 > p.bounds[3]) for p in pieces):
                        continue
                    return piece, next(c for c in self.connectors(piece)
                                       if c.direction == inlet.direction)
        return None

    def _build_plan(self, region):
        if not self.enabled:
            return None
        rng = random.Random(f"{self.generator.seed}:fortress_templates:{region}")
        center = region * self.SPACING + 256 + rng.randint(-24, 24)
        floor = rng.randint(52, 68)
        start = self._piece(self.pool["start"], 0, 0)
        sockets = self.connectors(start)
        if len(sockets) != 2 or {c.direction for c in sockets} != {-1, 1}:
            raise ValueError("Fortress start needs one connector on either side")
        start = self._piece(start.template, center - start.width // 2, floor - sockets[0].y)
        if start.y < 5 or start.y + start.height >= self.max_height:
            return None
        pieces, links = [start], []
        for side, socket in enumerate(self.connectors(start)):
            # One blaze deck per wing, plus a wart room in one wing. Normal
            # pieces and mirroring vary, while special-room counts stay bounded.
            roles = ["regular"] * rng.randint(2, 4)
            if side == 1:
                roles.append("wart")
            roles.extend(("blaze", "end"))
            for role in roles:
                attached = self._attach(socket, self.pool["pools"][role], pieces, rng, region)
                if attached is None:
                    return None
                piece, inlet = attached
                pieces.append(piece)
                links.append((socket, inlet))
                exits = [c for c in self.connectors(piece) if c != inlet]
                if role == "end":
                    if exits:
                        raise ValueError("Fortress end templates must have one connector")
                    break
                if len(exits) != 1 or exits[0].direction != socket.direction:
                    raise ValueError("Fortress through-pieces need two opposite connectors")
                socket = exits[0]
        return FortressPlan(center, floor, tuple(pieces), tuple(links))

    def plans_for_chunk(self, rx):
        if not self.enabled:
            return
        plan = self.plan_for_region(rx * 16 // self.SPACING)
        if plan is not None and plan.x_min <= rx * 16 + 15 and plan.x_max >= rx * 16:
            yield plan

    def fortress_at(self, x, y):
        plan = self.plan_for_region(int(x // self.SPACING))
        return plan is not None and any(p.x <= x < p.x + p.width and p.y <= y < p.y + p.height
                                       for p in plan.pieces)

    def locate(self, origin_x, max_radius=524288):
        if not self.enabled or max_radius < 0:
            return None
        first = int((origin_x - max_radius) // self.SPACING)
        last = int((origin_x + max_radius) // self.SPACING)
        nearest, distance = None, max_radius + 1
        regions = range(first, last + 1)
        def minimum_distance(region):
            return max(region * self.SPACING + 232 - origin_x,
                       origin_x - (region * self.SPACING + 280), 0)
        for region in sorted(regions, key=lambda r: (minimum_distance(r), r)):
            if minimum_distance(region) > min(distance, max_radius):
                break
            plan = self.plan_for_region(region)
            if plan is not None and abs(plan.center_x - origin_x) < distance:
                nearest, distance = plan.location, abs(plan.center_x - origin_x)
        return nearest if distance <= max_radius else None

    def _fill_loot(self, block, x, y, z):
        if any(not stack.is_empty() for stack in block.inventory):
            return  # Preserve hand-authored contents.
        rng = random.Random(f"{self.generator.seed}:fortress_loot:{x}:{y}:{z}")
        for _ in range(rng.randint(2, 5)):
            item, low, high, _weight = rng.choices(FORTRESS_LOOT, [e[3] for e in FORTRESS_LOOT])[0]
            block.inventory[rng.randrange(len(block.inventory))] = ItemStack(
                get_material_by_id(item), rng.randint(low, high))

    def apply_chunk(self, world, rx, blocks):
        first, last = rx * 16, rx * 16 + 15
        for plan in self.plans_for_chunk(rx):
            for piece in plan.pieces:
                loot = set()
                for x, y, z in self.pool["pieces"][piece.template].get("loot_chests", []):
                    if piece.mirror_x:
                        x = piece.width - 1 - x
                    loot.add((piece.x + x, piece.y + y, z))
                for x, y, z, entry in iter_structure_blocks(
                    self.templates[piece.template], (piece.x, piece.y, 0),
                    x_bounds=(first, last), mirror_x=piece.mirror_x,
                ):
                    if not 0 <= y < blocks.shape[1]:
                        continue
                    block = get_block_by_id(entry["id"])
                    if entry.get("nbt"):
                        block.write_nbt(entry["nbt"])
                    if (x, y, z) in loot and block.block_id == "chest":
                        self._fill_loot(block, x, y, z)
                    block.location = Location(world, x, y, z)
                    blocks[x - first, y, z] = block
