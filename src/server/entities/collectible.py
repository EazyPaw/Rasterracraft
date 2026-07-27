# Commented and arranged by ChatGPT

from __future__ import annotations

from src.server.entity import Entity


class CollectibleEntity(Entity):
    blocks_block_placement = False
    lifetime = 6000

    def __init__(self, x: float, y: float, world):
        super().__init__(float(x), float(y), world)
        self.age = 0
        self.pickup_delay = 10

    def get_persistent_data(self) -> dict:
        return {
            "age": max(0, int(self.age)),
            "pickup_delay": max(0, int(self.pickup_delay)),
        }

    def read_persistent_data(self, data: dict) -> None:
        self.age = max(0, int(data.get("age", self.age)))
        self.pickup_delay = max(0, int(data.get("pickup_delay", self.pickup_delay)))

    def advance_collectible_lifetime(self) -> bool:
        self.age += 1
        if self.age >= self.lifetime:
            self.world.remove_entity(self)
            return False
        return True

    def tick_pickup_delay(self) -> bool:
        if self.pickup_delay <= 0:
            return False
        self.pickup_delay -= 1
        return True

    def is_valid_pickup_player(self, player) -> bool:
        return (
            getattr(player, "world", None) is self.world
            and getattr(player, "health", 0) > 0
            and getattr(getattr(player, "gamemode", None), "name_id", "survival")
            != "spectator"
        )

    def is_pickup_candidate(self, player) -> bool:
        return (
            self.is_valid_pickup_player(player)
            and abs((player.x + player.width / 2) - self.x) <= 1.2
            and player.y - 0.5 <= self.y <= player.y + player.height + 0.7
        )

    def get_pickup_player(self):
        for player in tuple(getattr(self.world.server, "players", ())):
            if self.is_pickup_candidate(player):
                return player
        return None
