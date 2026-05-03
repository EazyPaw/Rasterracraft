from typing import TYPE_CHECKING

from resources.server.block_class import Block
from resources.server.blocks import STONE
from resources.server.entity import Entity
from resources.server.location import Location

if TYPE_CHECKING:
    from resources.client.main_player import ClientPlayer

class GameMode:

    name_id = "null"

    def __init__(self, player: 'ClientPlayer'):
        self.player = player
        self.player.interact_range = 5

    def left_click_on_block(self, block: Block):
        pass

    def right_click_on_block(self, block: Block):
        pass

    def left_click_on_entity(self, entity: Entity):
        pass

    def right_click_on_entity(self, entity: Entity):
        pass


class CreativeMode(GameMode):
    name_id = "creative"

    def left_click_on_block(self, block: Block):
        x,y = self.player.choosing_block
        location = Location(self.player.client.client_world, x,y, 0)
        block = location.world.get_block(location)
        if self.player.client.hold_mouse_buttons[0] or not block.breakable:
            return
        self.player.client.client_world.break_block(location)
        self.player.client.sent_packet(block, 'BreakBlock')
        self.player.client.resources_manager.play_sound(block.break_sound)

    def right_click_on_block(self, block: Block):
        if self.player.client.hold_mouse_buttons[2]:
            return
        x, y = self.player.choosing_block
        location = Location(self.player.client.client_world, x,y, 0)
        block = location.world.get_block(location)
        new_block = STONE()
        if (not block.on_right_click() and y != 0
                and new_block.place_at(Location(self.player.client.client_world, x, y, 0))):
            self.player.client.resources_manager.play_sound(block.break_sound)
            self.player.client.sent_packet(new_block, 'PlaceBlock')

class SurvivalMode(GameMode):
    name_id = "survival"

    def left_click_on_block(self, block: Block):
        block.on_break()
        block.on_left_click()

    def right_click_on_block(self, block: Block):
        block.on_right_click()