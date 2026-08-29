# Commented and arranged by ChatGPT
import uuid
from typing import TYPE_CHECKING

import pygame

from src.client.entity_skeleton import PlayerSkeleton
from src.client.game_mode import CreativeMode, SurvivalMode
from src.server.damange_type import GENERIC, DamageType
from src.server.entity import Entity
from src.server.experience import experience_to_next_level
from src.server.inventory import Inventory
from src.server.item_class import EmptyItemStack

if TYPE_CHECKING:
    from src.client.client_main import Client


class ClientPlayer(Entity):
    HURT_FLASH_TICKS = 10

    def __init__(self, client: "Client", game_mode: str = "survival"):
        super().__init__(0, 15, client.client_world)
        self.uuid = uuid.UUID("{00000000-0000-0000-0000-000000000000}")
        self.entity_id = "player"
        self.client = client
        self.move_speed = 0.1
        self.damping = 0.91
        self.width = 0.6
        self.height = 1.8
        self.jump_height = 0.42
        self.set_attribute_base_value("waypoint_receive_range", 60_000_000.0)
        self.set_attribute_base_value("waypoint_transmit_range", 60_000_000.0)
        self.max_health = 20
        self.health = self.max_health
        self.food_level = 20
        self.saturation = 5.0
        self.hurt_time = 0
        self.dead = False
        self.experience = 0
        self.experience_level = 0
        self.experience_total = 0
        self.score = 0
        self.choosing_block = None
        self.choosing_entity = None
        self.flyable = False
        self.inventory = Inventory(36)
        self.equipment = {
            slot: EmptyItemStack()
            for slot in ("offhand", "head", "chest", "legs", "feet")
        }
        self.skeleton = PlayerSkeleton(self)
        self.skeleton.x = self.client.render.SCREEN_WIDTH / 2
        self.skeleton.y = self.client.render.SCREEN_HEIGHT / 2
        self.selected_slot = 0
        self.game_mode = (
            CreativeMode(self) if game_mode == "creative" else SurvivalMode(self)
        )
        self.fore_place = False

    def set_creative_slot(
        self,
        slot: int | None,
        item_id: str = "air",
        amount: int = 64,
        nbt=None,
        *,
        target: str = "inventory",
    ) -> None:
        packet = {
            "__class__": "CreativeSetSlot",
            "target": str(target),
            "item": {"id": str(item_id), "amount": int(amount), "nbt": nbt or {}},
        }
        if slot is not None:
            packet["slot"] = int(slot)
        self.client.sent_packet(packet)

    def set_creative_cursor(
        self, item_id: str = "air", amount: int = 64, nbt=None
    ) -> None:
        """Ask the server to create a stack on the creative inventory cursor."""
        self.set_creative_slot(
            None,
            item_id,
            amount,
            nbt,
            target="cursor",
        )

    def clear_creative_inventory(self) -> None:
        """Clear all player inventory and equipment slots while in creative mode."""
        self.client.sent_packet({"__class__": "CreativeClearInventory"})

    def move_update(self):
        if self.dead:
            return
        if not self.client.can_simulate_player(self):
            self.motion.x = 0
            self.motion.y = 0
            return
        if self.client.game_manager.gameplay_input_blocked():
            # 这些状态原先绕过事件队列直接轮询键盘，导致 GUI 已经吃掉
            # KEYDOWN 后玩家仍会下蹲/上浮。统一服从游戏输入门闩。
            self.sneaking = False
            self.swimming_up = False
        else:
            keys = pygame.key.get_pressed()
            self.sneaking = (
                keys[pygame.K_LSHIFT] or keys[pygame.K_s]
            ) and not self.flying
            self.swimming_up = keys[pygame.K_SPACE] and not self.flying

        super().move_update()
        self._update_survival_state()

        self.client.sent_packet(self, "PlayerMove")

    def _update_survival_state(self):

        self.tick_damage_state()
        if not isinstance(self.game_mode, SurvivalMode):
            return
        if self.food_level <= 6:
            self.sprinting = False
        self._request_nearby_item_pickups()
        self.game_mode.tick()

    def can_take_damage(self, damage_type: type[DamageType] = GENERIC) -> bool:
        return (
            not self.dead
            and not isinstance(self.game_mode, CreativeMode)
            and super().can_take_damage(damage_type)
        )

    def on_damage_applied(
        self,
        actual_damage: float,
        raw_damage: float,
        damage_type: type[DamageType],
        source,
    ) -> None:
        if self.health <= 0:
            self.dead = True
            args = [getattr(self, "name", "Player")]
            if source is not None:
                args.append(getattr(source, "name", str(source)))
            self.client.show_death_screen(
                {
                    "key": f"death.attack.{getattr(damage_type, 'message_id', 'generic')}",
                    "args": args,
                }
            )

    def add_experience(self, amount: int):
        amount = max(0, int(amount))
        self.experience += amount
        self.experience_total += amount
        self.score += amount
        while self.experience >= self.experience_to_next_level():
            self.experience -= self.experience_to_next_level()
            self.experience_level += 1

    def experience_to_next_level(self) -> int:
        return experience_to_next_level(self.experience_level)

    def _request_nearby_item_pickups(self):
        if self.client.client_ticks % 5:
            return
        for entity in self.client.client_world.iter_entities():
            if entity.entity_id != "item":
                continue
            if (
                abs(entity.x - (self.x + self.width / 2)) <= 1.2
                and self.y - 0.5 <= entity.y <= self.y + self.height + 0.7
            ):
                self.client.sent_packet(
                    {"__class__": "PickupItem", "uuid": entity.uuid}
                )
