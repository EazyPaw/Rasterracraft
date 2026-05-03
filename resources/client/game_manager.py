import time
import pygame

from typing import TYPE_CHECKING

from resources.server.blocks import AIR, STONE

if TYPE_CHECKING:
    from resources.client.client_main import Client


class GameManager:
    """游戏管理器，负责处理游戏主循环、输入处理和玩家状态同步"""

    def __init__(self, client: 'Client'):
        self.client = client
        self.running = True

    def tick(self):
        """执行一次游戏逻辑更新"""
        self.handle_key_pressed()
        self.sync_player_camera()
        self.client.client_player.handle_gravity()
        self.client.client_player.move_update()

    def handle_key_pressed(self):
        """处理键盘输入"""
        keys = pygame.key.get_pressed()
        mouse_button = pygame.mouse.get_pressed()
        for key, action in self.client.key_map.items():
            if type(key) == str: continue
            if keys[key]:
                action()
        if mouse_button[0]:
            x, y = self.client.client_player.choosing_block
            self.client.key_map["mouse_left"](self.client.client_world.get_block(x, y, 0))
            self.client.hold_mouse_buttons[0] = True
        else:
            self.client.hold_mouse_buttons[0] = False
        if mouse_button[2]:
            x, y = self.client.client_player.choosing_block
            self.client.key_map["mouse_right"](self.client.client_world.get_block(x, y, 0))
            self.client.hold_mouse_buttons[2] = True
        else:
            self.client.hold_mouse_buttons[2] = False


    def sync_player_camera(self):
        """同步玩家位置到相机"""
        self.client.render.camera.move_to(
            self.client.client_player.x,
            self.client.client_player.y
        )

    def start_game_loop(self):
        """启动游戏主循环"""
        next_time = time.perf_counter()

        while self.running:
            interval = 1.0 / self.client.rate

            self.tick()

            next_time += interval
            sleep_time = next_time - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        """停止游戏循环"""
        self.running = False


