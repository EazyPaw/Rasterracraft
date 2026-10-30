"""Minecraft 1.8.9 pearl physics and server-authoritative teleportation."""

import random

from src.server.damange_type import FALL
from src.server.entities.thrown_item import ThrownItem, ThrownItemSkeleton
from src.server.entity_registry import register_entity
from src.server.particles import PORTAL


@register_entity(persistent=False)
class EnderPearl(ThrownItem):
    entity_id = "ender_pearl"
    translation_key = "item.enderPearl.name"
    impact_knockback = 0.0

    def __init__(self, x, y, world, z=0, *, owner=None):
        super().__init__(x, y, world, z, owner=owner)
        self.width = self.height = 0.25

    def can_hit_entity(self, target):
        # EntityEnderPearl ignores its original thrower even after leaving them.
        return target is not self.get_owner() and super().can_hit_entity(target)

    def on_hit(self, result):
        if result.kind == "entity":
            self.on_hit_entity(result)
        self.world.spawn_particle(PORTAL(
            self.x, self.y, self.z, count=32, data={"kind": "impact"},
        ))
        owner = self.get_owner()
        if self._can_teleport_owner(owner):
            if (getattr(owner, "entity_id", "") == "player"
                    and not getattr(self.world, "disable_mob_generation", False)
                    and random.random() < 0.05):
                from src.server.entities.endermite import Endermite

                mite = Endermite(owner.x, owner.y, self.world, self.z)
                mite.player_spawned = True
                self.world.spawn_entity(mite)
            # teleport_to also uses the player's existing teleport confirmation
            # handshake, so old movement packets cannot undo the teleport.
            x, y = self.x, self.y
            if result.kind == "block":
                # The game stores AABB lower-left positions. Match the impacted
                # face using the player's larger box to avoid embedding in walls.
                if result.normal_x < 0:
                    x += self.width - owner.width
                if result.normal_y < 0:
                    y += self.height - owner.height
            owner.teleport_to(x, y)
            self.world.server.broadcast_sound(
                'mob.endermen.portal', self.x if x is None else x, self.y if y is None else y,
                self.z, world=self.world,
            )
            owner.fall_distance = 0.0
            if getattr(owner, "entity_id", "") == "player":
                owner.apply_damage(5.0, FALL)
        self.discard()

    def _can_teleport_owner(self, owner):
        if (owner is None or owner.world is not self.world
                or owner.health <= 0 or getattr(owner, "removed", False)
                or getattr(owner, "sleeping", False)):
            return False
        if getattr(owner, "entity_id", "") == "player":
            return owner in self.world.server.players
        return True

    def update(self):
        owner = self.get_owner()
        if owner is not None and owner.health <= 0:
            self.discard()
            return
        super().update()


class EnderPearlSkeleton(ThrownItemSkeleton):
    visual_size = 0.5
