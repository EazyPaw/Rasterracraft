import uuid
from typing import TYPE_CHECKING

import pygame

from resources.client.entity_skeleton import PlayerSkeleton
from resources.client.game_mode import CreativeMode, SurvivalMode
from resources.server.entity import Entity
from resources.server.inventory import Inventory
from resources.server.item_class import ItemStack
from resources.server.materials import *

if TYPE_CHECKING:
    from resources.client.client_main import Client


class ClientPlayer(Entity):
    HURT_FLASH_TICKS = 10

    def __init__(self, client: 'Client', game_mode: str = "survival"):
        super().__init__(0, 15, client.client_world)
        self.uuid = uuid.UUID('{00000000-0000-0000-0000-000000000000}')
        self.entity_id = "player"
        self.client = client
        self.move_speed = 0.3
        self.damping = 0.95
        self.width = 0.3
        self.height = 1.8
        self.jump_height = 0.8
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
        self.flyable = False
        self.inventory = Inventory(36)
        self.skeleton = PlayerSkeleton(client, self)
        self.skeleton.x = self.client.render.SCREEN_WIDTH / 2
        self.skeleton.y = self.client.render.SCREEN_HEIGHT / 2
        if game_mode == "creative":
            for i in range(4):
                self.inventory.set_item(i, ItemStack(GLOWSTONE(), 64))
            for i in range(8, 16):
                self.inventory.set_item(i, ItemStack(SAND(), 64))
            for i in range(4, 8):
                self.inventory.set_item(i, ItemStack(WATER(), 64))
        else:
            # The project has no animals/crops yet.  A small starter ration
            # keeps the fully implemented hunger loop playable from day one.
            self.inventory.set_item(0, ItemStack(APPLE(), 3))
            self.inventory.set_item(1, ItemStack(BREAD(), 2))
        self.selected_slot = 0
        self.game_mode = CreativeMode(self) if game_mode == "creative" else SurvivalMode(self)

    def move_update(self):
        if self.dead:
            return
        keys = pygame.key.get_pressed()
        self.sneaking = (keys[pygame.K_LSHIFT] or keys[pygame.K_s]) and not self.flying
        self.swimming_up = keys[pygame.K_SPACE] and not self.flying

        previous_y = self.y
        was_on_ground = self.on_ground
        super().move_update()
        self._update_survival_state(previous_y, was_on_ground)

        self.client.sent_packet(self, 'PlayerMove')

    def _update_survival_state(self, previous_y: float, was_on_ground: bool):
        if not isinstance(self.game_mode, SurvivalMode):
            return
        fallen = previous_y - self.y
        if not self.in_fluid and not self.flying and fallen > 0:
            self.fall_distance += fallen
        if self.on_ground and not was_on_ground:
            if self.fall_distance > 3.0:
                self.damage(int(self.fall_distance - 3.0 + 0.999), "fall")
            self.fall_distance = 0.0
        elif self.in_fluid or self.flying:
            self.fall_distance = 0.0

        moving = abs(self.motion.x) > 0.02
        if moving:
            self.exhaustion += 0.006 if self.sprinting else 0.001
        if self.hurt_time > 0:
            self.hurt_time -= 1
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
                self.damage(1, "starvation")
                self.starvation_timer = 0
        else:
            self.starvation_timer = 0

    def damage(self, amount: float, cause: str = "generic"):
        if self.dead or amount <= 0:
            return
        self.health = max(0.0, self.health - amount)
        self.hurt_time = self.HURT_FLASH_TICKS
        sound = "game.player.hurt.fall.big" if cause == "fall" and amount >= 5 else "game.player.hurt"
        self.client.resources_manager.play_sound(sound)
        if self.health <= 0:
            self.dead = True
            self.client.add_chat_message("You died!", (255, 85, 85))
            self.client.sent_packet({'__class__': 'RequestRespawn'})

    def add_item_stack(self, stack: ItemStack) -> bool:
        """Insert a picked-up item while respecting normal stack merging."""
        for slot in range(len(self.inventory)):
            current = self.inventory[slot]
            if not current.is_empty() and current.material == stack.material and current.nbt == stack.nbt:
                space = current.max_stack_size - current.amount
                moved = min(space, stack.amount)
                current.amount += moved
                stack.amount -= moved
                if stack.amount == 0:
                    return True
        for slot in range(len(self.inventory)):
            if self.inventory[slot].is_empty():
                self.inventory[slot] = stack
                return True
        return False

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
