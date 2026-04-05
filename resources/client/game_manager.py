import time
import pygame

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from resources.client.client_main import Client


def tick(client: 'Client'):
    handle_keyboard(client)
    sync_player_camera(client)
    client.client_player.handle_gravity()
    client.client_player.motion_update()

def handle_keyboard(client: 'Client'):
    keys = pygame.key.get_pressed()

    for key, action in client.key_map.items():
        if keys[key]:
            action()

def sync_player_camera(client: 'Client'):
    client.render.camera.move_to(
        client.client_player.x,
        -client.client_player.y
    )

def start_inner_game(client: 'Client'):

    next_time = time.perf_counter()

    while True:

        interval = 1.0 / client.rate

        tick(client)

        next_time += interval
        sleep_time = next_time - time.perf_counter()
        if sleep_time > 0:
            time.sleep(sleep_time)

