"""Dimension-owned End encounter state, independent of entity chunk saves."""
import logging
import math
from uuid import uuid4

from src.server.damange_type import EXPLOSION
from src.server.bossbar import BossBar


class EndFight:
    ARENA_CHUNKS = tuple(range(-7, 7))

    def __init__(self, world):
        self.world = world
        self.dragon_uuid = None
        self.dragon_chunk = None
        self.dragon_killed = False
        self.previously_killed = False
        self.crystals_initialized = False
        self.exit_portal_generated = False
        self._prepare_future = None
        self._preparing = False
        self._pending_entries = {}
        self.boss_bar = BossBar(str(uuid4()), "entity.EnderDragon.name", 0, 200, active=False)

    def queue_entry(self, entity):
        """Latch server-verified contact while the arena loads off-thread."""
        if str(entity.uuid) in self._pending_entries:
            return
        self._pending_entries[str(entity.uuid)] = (entity, entity.world)
        entity._pending_end_entry = self
        entity.motion.x = entity.motion.y = 0
        entity.fall_distance = 0
        if entity.entity_id == "player":
            # Correct client prediction at the portal; subsequent inputs are
            # suspended until travel completes, so lava below cannot catch it.
            entity.teleport_to(entity.x, entity.y)

    def _finish_entries(self, ready):
        server = self.world.server
        for uuid, (entity, origin) in tuple(self._pending_entries.items()):
            valid = (not entity.removed and entity.health > 0 and entity.world is origin
                     and getattr(entity, "riding_entity", None) is None)
            if entity.entity_id == "player":
                valid = valid and entity in server.players
            else:
                valid = valid and origin.entities.get(uuid) is entity
            if valid and not ready and self._prepare_future is not None:
                continue
            del self._pending_entries[uuid]
            entity._pending_end_entry = None
            if valid and ready:
                travel_end(server, entity)

    def restore(self, data):
        self.dragon_uuid = data.get("dragon_uuid")
        self.dragon_chunk = data.get("dragon_chunk")
        self.dragon_killed = bool(data.get("dragon_killed", False))
        self.previously_killed = bool(data.get("previously_killed", False))
        self.crystals_initialized = bool(data.get("crystals_initialized", False))
        self.exit_portal_generated = bool(data.get("exit_portal_generated", False))

    def to_dict(self):
        self.required_chunks()
        return {"dragon_uuid": self.dragon_uuid, "dragon_killed": self.dragon_killed,
                "dragon_chunk": self.dragon_chunk,
                "previously_killed": self.previously_killed,
                "crystals_initialized": self.crystals_initialized,
                "exit_portal_generated": self.exit_portal_generated}

    def required_chunks(self):
        # Inertia and a player chase can carry the boss beyond the island.
        # Remember its actual chunk so a reload restores it before respawning.
        dragon = self.world.entities.get(self.dragon_uuid)
        if dragon is not None and not dragon.removed:
            self.dragon_chunk = math.floor(dragon.x) // 16
        extra = (int(self.dragon_chunk),) if self.dragon_chunk is not None and not self.dragon_killed else ()
        return (*self.ARENA_CHUNKS, *extra)

    def prepare(self):
        """Load the finite arena off the tick thread, then spawn on the tick."""
        if self._prepare_future is not None:
            if not self._prepare_future.done():
                return False
            try:
                self._prepare_future.result()
            except Exception:
                logging.exception("Could not prepare the End arena")
                self._prepare_future = None
                self._preparing = False
                return False
            self._prepare_future = None
            self._preparing = False
        if not all(self.world.is_chunk_loaded(rx) for rx in self.required_chunks()):
            if self._prepare_future is None:
                pool = getattr(self.world.server, "chunk_gen_pool", None)
                if pool is None:
                    self._load_arena()
                else:
                    self._preparing = True
                    self._prepare_future = pool.submit(self._load_arena)
            if self._prepare_future is not None:
                return False
        self._ensure_encounter()
        return True

    def _load_arena(self):
        for rx in self.required_chunks():
            if not self.world.is_chunk_loaded(rx):
                self.world.generate_chunk(rx)

    def _ensure_encounter(self):
        from src.server.entities.end import EnderCrystal, EnderDragon
        if not self.crystals_initialized:
            for piece in self.world.structure_generator.layout["pieces"]:
                if "crystal" not in piece:
                    continue
                x, y = piece["crystal"]
                if not any(e.entity_id == "ender_crystal" and abs(e.x + 1 - x) < .5 and abs(e.y - y) < .5
                           for e in tuple(self.world.entities.values())):
                    self.world.spawn_entity(EnderCrystal(x - 1, y, self.world))
            self.crystals_initialized = True
        if self.dragon_killed:
            if not self.exit_portal_generated or any(self.world.get_block(x, y, z).block_id != "end_portal"
                for x, y, z in self.world.structure_generator.layout["exit_cells"]):
                self._activate_exit()
            return
        dragons = [e for e in tuple(self.world.entities.values())
                   if e.entity_id == "ender_dragon" and not e.removed and (e.health > 0 or e.dying)]
        dragon = next((e for e in dragons if str(e.uuid) == self.dragon_uuid), None)
        if dragon is None:
            dragon = dragons[0] if dragons else EnderDragon(-8, 88, self.world)
            if not dragons:
                self.world.spawn_entity(dragon)
            self.dragon_uuid = str(dragon.uuid)
        for duplicate in dragons:
            if duplicate is not dragon:
                self.world.remove_entity(duplicate)

    def crystal_destroyed(self, crystal):
        # Notify before the explosion removes its source from the entity map.
        for dragon in tuple(self.world.entities.values()):
            if (dragon.entity_id == "ender_dragon" and dragon.health > 0
                    and dragon.healing_crystal_uuid == str(crystal.uuid)):
                dragon.healing_crystal_uuid = None
                dragon.apply_part_damage("head", 10, EXPLOSION)

    def dragon_died(self, dragon):
        if self.dragon_uuid is not None and str(dragon.uuid) != self.dragon_uuid:
            return
        first_kill = not self.previously_killed
        self.dragon_killed = self.previously_killed = True
        self._activate_exit()
        if first_kill:
            from src.server.blocks import DRAGON_EGG
            x, y, z = self.world.structure_generator.layout["egg_position"]
            self.world.set_block(DRAGON_EGG(), x, y, z, block_update=False)

    def _activate_exit(self):
        from src.server.blocks import END_PORTAL
        for x, y, z in self.world.structure_generator.layout["exit_cells"]:
            if not self.world.is_chunk_loaded(x // 16):
                self.world.generate_chunk(x // 16)
            self.world.set_block(END_PORTAL({"exit_portal": True}), x, y, z, block_update=False)
        self.exit_portal_generated = True

    def tick(self):
        # A latched entry completes without requiring another portal collision.
        if self._prepare_future is not None or self._pending_entries:
            ready = self.prepare()
            self._finish_entries(ready)
        players = [p for p in tuple(self.world.server.players) if p.world is self.world]
        if not players or not self.prepare():
            return
        tick = self.world.server.server_ticks
        if tick % 5 == 0:
            dragon = self.world.entities.get(self.dragon_uuid)
            self.boss_bar.update_from_entity(dragon if not self.dragon_killed else None)
            packet = self.boss_bar.to_packet(self.world.id_name)
            for player in players:
                self.world.server.send_client_socket(player, packet, "Forward")


def travel_end(server, entity, portal_location=None):
    """Use the existing authoritative world-reset / teleport acknowledgement."""
    origin = entity.world
    if (entity.removed or entity.health <= 0
            or getattr(entity, "riding_entity", None) is not None):
        return False
    if origin.id_name == "end":
        fight = getattr(origin, "end_fight", None)
        if fight is None or not fight.dragon_killed:
            return False
        destination = server.worlds.get("overworld")
        if destination is None:
            return False
        x = int(getattr(destination, "spawn_point", 0))
        if not destination.is_chunk_loaded(x // 16):
            destination.generate_chunk(x // 16)
        block = destination.find_top_block(x, 0)
        y = block.location.y + 1 if block is not None else 100
    else:
        destination = server.worlds.get("end")
        if destination is None:
            return False
        if not destination.end_fight.prepare():
            if destination.end_fight._prepare_future is not None:
                destination.end_fight.queue_entry(entity)
            return False
        x, y = destination.structure_generator.layout["arrival"]
        # Vanilla recreates the obsidian entry platform and clears headroom on
        # every arrival. Only the platform template footprint is rewritten.
        from src.server.structure import iter_structure_blocks
        from src.server.blocks import get_block_by_id
        piece = next(p for p in destination.structure_generator.layout["pieces"] if p["template"] == "end/platform")
        data = destination.structure_generator.templates[piece["template"]]
        for px, py, pz, entry in iter_structure_blocks(data, tuple(piece["origin"])):
            destination.set_block(get_block_by_id(entry["id"]), px, py, pz, block_update=False)
    if entity.entity_id != "player":
        origin.remove_entity(entity)
        entity.removed = False
        entity.x, entity.y, entity.z = float(x), float(y), 0
        entity.motion.x = entity.motion.y = 0
        destination.spawn_entity(entity)
    else:
        entity.z = 0
        entity.teleport_to(float(x), float(y), destination)
    entity.fall_distance = 0
    return True
