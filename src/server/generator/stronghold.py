"""Unlimited underground strongholds built with the shared structure templates.

Like fortress/village generation, plans and loot depend only on the world seed,
and each chunk places only its slice. No loaded terrain is queried by locate.
"""
import json
import random
from functools import cached_property
from pathlib import Path

from src.server.generator.fortress import NetherFortressGenerator, FortressPlan
from src.server.generator.minecraft_like import MinecraftLike2D
from src.server.generator.classic_flat import ClassicFlat


POOL_PATH = Path(__file__).resolve().parents[3] / "worldgen/stronghold.json"
STRONGHOLD_LOOT = (
    ("ender_pearl", 1, 1, 10), ("diamond", 1, 3, 3),
    ("iron_ingot", 1, 5, 10), ("gold_ingot", 1, 3, 5),
    ("bread", 1, 3, 15), ("apple", 1, 3, 15), ("book", 1, 3, 20),
    ("redstone", 4, 9, 5),
)


class StrongholdGenerator(NetherFortressGenerator):
    SPACING = spacing = 1536
    MARGIN = 128

    def __init__(self, generator, height=256, *, enabled=True):
        enabled = enabled and isinstance(generator, (MinecraftLike2D, ClassicFlat))
        if isinstance(generator, ClassicFlat):
            enabled = enabled and "stronghold" in generator.settings.structures
        super().__init__(generator, height, enabled=enabled)
        self.max_height = height - 1

    @cached_property
    def pool(self):
        data = json.loads(POOL_PATH.read_text(encoding="utf-8"))
        if data.get("format_version") != 1 or data.get("start") not in data.get("pieces", {}):
            raise ValueError("Invalid stronghold pool")
        for role in ("regular", "library", "prison", "portal", "end"):
            if not data.get("pools", {}).get(role) or any(
                    name not in data["pieces"] for name in data["pools"][role]):
                raise ValueError(f"Invalid stronghold pool: {role}")
        return data

    def _build_plan(self, region):
        if not self.enabled:
            return None
        rng = random.Random(f"{self.generator.seed}:stronghold:{region}")
        center = region * self.SPACING + self.SPACING // 2 + rng.randint(-256, 256)
        # Keep even the tallest room buried and away from bedrock. Flat presets
        # that have insufficient underground space intentionally have no starts.
        roof = min(self.generator.get_surface_height(x)
                   for x in range(center - 240, center + 241, 16))
        floor = min(rng.randint(20, 36), roof - 18, self.max_height - 20)
        if floor < 6:
            return None
        start = self._piece(self.pool["start"], 0, 0)
        start = self._piece(start.template, center - start.width // 2,
                            floor - self.connectors(start)[0].y)
        pieces, links = [start], []
        for socket in self.connectors(start):
            roles = ["regular"] * rng.randint(2, 4)
            roles.extend(("library" if socket.direction < 0 else "prison",
                          "end" if socket.direction < 0 else "portal"))
            for role in roles:
                attached = self._attach(socket, self.pool["pools"][role], pieces, rng, region)
                if attached is None:
                    return None
                piece, inlet = attached
                pieces.append(piece)
                links.append((socket, inlet))
                exits = [c for c in self.connectors(piece) if c != inlet]
                if not exits:
                    break
                socket = exits[0]
        portal = next(p for p in pieces if p.template == "portal_room")
        px, py, _ = self.templates[portal.template]["portal_origin"]
        if portal.mirror_x:
            px = portal.width - 5 - px
        return FortressPlan(portal.x + px + 2, portal.y + py, tuple(pieces), tuple(links))

    def locate(self, origin_x, max_radius=524288):
        if not self.enabled or max_radius < 0:
            return None
        # Candidate centers are within +/-256 of each region's midpoint; room
        # chains fit within 240 blocks. This bound permits an exact early exit.
        region = int(origin_x // self.SPACING)
        nearest, distance = None, max_radius + 1
        for radius in range(int(max_radius // self.SPACING) + 3):
            for candidate in ((region,) if radius == 0 else (region - radius, region + radius)):
                plan = self.plan_for_region(candidate)
                if plan is not None and abs(plan.center_x - origin_x) < distance:
                    nearest, distance = plan.location, abs(plan.center_x - origin_x)
            if radius * self.SPACING - 512 > min(distance, max_radius):
                break
        return nearest if distance <= max_radius else None

    def _fill_loot(self, block, x, y, z):
        if any(not stack.is_empty() for stack in block.inventory):
            return
        from src.server.item_class import ItemStack
        from src.server.materials import get_material_by_id
        rng = random.Random(f"{self.generator.seed}:stronghold_loot:{x}:{y}:{z}")
        for _ in range(rng.randint(2, 5)):
            item, low, high, _ = rng.choices(STRONGHOLD_LOOT, [e[3] for e in STRONGHOLD_LOOT])[0]
            block.inventory[rng.randrange(len(block.inventory))] = ItemStack(
                get_material_by_id(item), rng.randint(low, high))

    def _has_eye(self, x, y, z):
        return random.Random(f"{self.generator.seed}:stronghold_eye:{x}:{y}:{z}").random() > .9

    def apply_chunk(self, world, rx, blocks):
        super().apply_chunk(world, rx, blocks)
        from src.server.blocks import END_PORTAL
        from src.server.end_portal import frame_positions
        for plan in self.plans_for_chunk(rx):
            left, y = plan.center_x - 2, plan.floor_y
            for x, py, z, _ in frame_positions(left, y):
                if rx * 16 <= x < rx * 16 + 16:
                    blocks[x % 16, py, z].eye = self._has_eye(x, py, z)
            if all(self._has_eye(x, py, z) for x, py, z, _ in frame_positions(left, y)):
                from src.server.location import Location
                for x in range(left + 1, left + 4):
                    if rx * 16 <= x < rx * 16 + 16:
                        portal = END_PORTAL()
                        portal.location = Location(world, x, y, 0)
                        blocks[x % 16, y, 0] = portal
