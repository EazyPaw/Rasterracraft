import pygame

from resources.client.client_world import ClientWorld
from resources.client.player import Player
from resources.server.world_class import World


def start_game(self):

    main_player = Player()

    world = ClientWorld()