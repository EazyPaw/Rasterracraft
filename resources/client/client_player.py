import uuid
from typing import TYPE_CHECKING

import pygame

from resources.client.entity_skeleton import PlayerSkeleton
from resources.client.game_mode import CreativeMode, SurvivalMode
from resources.server.damange_type import FALL, GENERIC, STARVE, DamageType
from resources.server.entity import Entity
from resources.server.inventory import Inventory

if TYPE_CHECKING:
    from resources.client.client_main import Client


class ClientPlayer(Entity):
    HURT_FLASH_TICKS = 10

    def __init__(self, client: 'Client', game_mode: str = "survival"):
        super().__init__(0, 15, client.client_world)
        self.uuid = uuid.UUID('{00000000-0000-0000-0000-000000000000}')
        self.entity_id = "player"
        self.client = client
        # The base Entity implements vanilla's per-tick acceleration and drag.
        # Keep the player speed attribute at the Java default (0.1); the
        # effective ground acceleration is 0.098 blocks/tick.
        self.move_speed = 0.1
        self.damping = 0.91
        self.width = 0.6
        self.height = 1.8
        self.jump_height = 0.42
        self.max_health = 20
        self.health = self.max_health
        self.food_level = 20
        self.saturation = 5.0
        self.exhaustion = 0.0
        self.hurt_time = 0
        self.regen_timer = 0
        self.starvation_timer = 0
        self.fall_distance = 0.0
        self.dead = False
        self.experience = 0
        self.experience_level = 0
        self.choosing_block = None
        self.choosing_entity = None
        self.flyable = False
        self.inventory = Inventory(36)
        self.skeleton = PlayerSkeleton(self)
        self.skeleton.x = self.client.render.SCREEN_WIDTH / 2
        self.skeleton.y = self.client.render.SCREEN_HEIGHT / 2
        self.selected_slot = 0
        self.game_mode = CreativeMode(self) if game_mode == "creative" else SurvivalMode(self)
        self.fore_place = False

    def set_creative_slot(self, slot: int, item_id: str = "air", amount: int = 64, nbt=None) -> None:
        """Request a creative-only server-side replacement for one slot."""
        self.client.sent_packet({
            "__class__": "CreativeSetSlot",
            "slot": int(slot),
            "item": {"id": str(item_id), "amount": int(amount), "nbt": nbt or {}},
        })

    def move_update(self):
        if self.dead:
            return
        if not self.client.can_simulate_player(self):
            self.motion.x = 0
            self.motion.y = 0
            self.fall_distance = 0.0
            return
        if self.client.game_manager.gameplay_input_blocked():
            # 这些状态原先绕过事件队列直接轮询键盘，导致 GUI 已经吃掉
            # KEYDOWN 后玩家仍会下蹲/上浮。统一服从游戏输入门闩。
            self.sneaking = False
            self.swimming_up = False
        else:
            keys = pygame.key.get_pressed()
            self.sneaking = (keys[pygame.K_LSHIFT] or keys[pygame.K_s]) and not self.flying
            self.swimming_up = keys[pygame.K_SPACE] and not self.flying

        previous_y = self.y
        was_on_ground = self.on_ground
        super().move_update()
        self._update_survival_state(previous_y, was_on_ground)

        self.client.sent_packet(self, 'PlayerMove')

    def _update_survival_state(self, previous_y: float, was_on_ground: bool):
        self.tick_damage_state()
        if not isinstance(self.game_mode, SurvivalMode):
            return
        fallen = previous_y - self.y
        if not self.in_fluid and not self.flying and fallen > 0:
            self.fall_distance += fallen
        if self.on_ground and not was_on_ground:
            if self.fall_distance > 3.0:
                amount = int(self.fall_distance - 3.0 + 0.999)
                self._send_self_damage(amount, "fall")
                self.apply_damage(amount, FALL, source=None)
            self.fall_distance = 0.0
        elif self.in_fluid or self.flying:
            self.fall_distance = 0.0

        moving = abs(self.motion.x) > 0.02
        if moving:
            self.exhaustion += 0.006 if self.sprinting else 0.001
        self._consume_exhaustion()
        self._natural_regeneration()
        self._request_nearby_item_pickups()
        self.game_mode.tick()

    def _consume_exhaustion(self):
        while self.exhaustion >= 4.0:
            self.exhaustion -= 4.0
            if self.saturation > 0:
                self.saturation = max(0.0, self.saturation - 1.0)
            elif self.food_level > 0:
                self.food_level -= 1

    def _natural_regeneration(self):
        if self.food_level >= 18 and self.health < self.max_health:
            self.regen_timer += 1
            if self.regen_timer >= 80:
                self.health = min(self.max_health, self.health + 1)
                self.exhaustion += 6.0
                self.regen_timer = 0
        else:
            self.regen_timer = 0
        if self.food_level == 0:
            self.starvation_timer += 1
            if self.starvation_timer >= 80:
                self._send_self_damage(1, "starvation")
                self.apply_damage(1, STARVE, source=None)
                self.starvation_timer = 0
        else:
            self.starvation_timer = 0

    def _send_self_damage(self, amount: float, cause: str) -> None:
        self.client.sent_packet({
            "__class__": "SelfDamage",
            "amount": float(amount),
            "cause": cause,
        })

    def can_take_damage(self, damage_type: type[DamageType] = GENERIC) -> bool:
        return not self.dead and not isinstance(self.game_mode, CreativeMode) and super().can_take_damage(damage_type)

    def on_damage_applied(self, actual_damage: float, raw_damage: float,
                          damage_type: type[DamageType], source) -> None:
        if self.health <= 0:
            self.dead = True
            args = [getattr(self, "name", "Player")]
            if source is not None:
                args.append(getattr(source, "name", str(source)))
            self.client.show_death_screen({
                "key": f"death.attack.{getattr(damage_type, 'message_id', 'generic')}",
                "args": args,
            })

    def add_experience(self, amount: int):
        self.experience += max(0, int(amount))
        while self.experience >= self.experience_to_next_level():
            self.experience -= self.experience_to_next_level()
            self.experience_level += 1

    def experience_to_next_level(self) -> int:
        level = self.experience_level
        if level < 16:
            return 7 + level * 2
        if level < 31:
            return 37 + (level - 15) * 5
        return 112 + (level - 30) * 9

    def _request_nearby_item_pickups(self):
        if self.client.client_ticks % 5:
            return
        for entity in self.client.client_world.iter_entities():
            if entity.entity_id != "item":
                continue
            if abs(entity.x - (self.x + self.width / 2)) <= 1.2 and self.y - 0.5 <= entity.y <= self.y + self.height + 0.7:
                self.client.sent_packet({'__class__': 'PickupItem', 'uuid': entity.uuid})
