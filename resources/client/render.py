import math

import pygame

from resources.client.camera import Camera
from resources.client.client_world import ClientWorld


class Render:
    def __init__(self, client_world: ClientWorld):
        self.BLACK = None
        pygame.init()
        self.client_world = client_world;
        self.SCREEN_WIDTH = 800
        self.SCREEN_HEIGHT = 600
        self.screen = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("PyCraft 2D - 0.0.1 SNAPSHOT")
        self.icon = pygame.image.load("icon.png").convert_alpha()
        pygame.display.set_icon(self.icon)
        self.block_size = 64
        self.running = False
        self.camera = Camera()

    def start(self):
        self.running = True
        self.BLACK = (104, 209, 246)
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.VIDEORESIZE:
                    self.SCREEN_WIDTH, self.SCREEN_HEIGHT = event.size
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)

            self.screen.fill(self.BLACK)

            self.camera.update()
            self.draw_block()
            self.draw_player()

            # 更新显示（将绘制内容呈现到窗口）
            pygame.display.flip()

        # 退出 Pygame
        pygame.quit()

    def draw_block(self):
        x_blocks = math.ceil(self.SCREEN_WIDTH / self.block_size)
        y_blocks = math.ceil(self.SCREEN_HEIGHT / self.block_size)

        x_start = int(self.camera.x - x_blocks // 2 - 1)
        x_end = int(self.camera.x + x_blocks // 2 + 1)
        y_start = int(self.camera.y - y_blocks // 2)
        y_end = int(self.camera.y + y_blocks // 2 + 1)

        for x in range(x_start, x_end):
            for y in range(y_start, y_end):
                block = self.client_world.get_block(x, y, 0)
                if block.block_id != 'air':
                    screen_x = (x - self.camera.x) * self.block_size + self.SCREEN_WIDTH // 2
                    screen_y = (y - self.camera.y) * self.block_size + self.SCREEN_HEIGHT // 2
                    self.screen.blit(block.get_texture(self.block_size), (screen_x, screen_y))

    def draw_player(self):
        pygame.draw.rect(self.screen, (50, 50, 50), ((self.SCREEN_WIDTH - 50) / 2, (self.SCREEN_HEIGHT - 50) / 2, 50, 50))




