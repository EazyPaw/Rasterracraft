import math

import pygame

from resources.server.blocks import *


class Render:
    def __init__(self):
        self.BLACK = None
        pygame.init()
        self.SCREEN_WIDTH = 800
        self.SCREEN_HEIGHT = 600
        self.screen = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("PyCraft 2D - 0.0.1 SNAPSHOT")
        self.icon = pygame.image.load("icon.png").convert_alpha()
        pygame.display.set_icon(self.icon)
        self.block_size = 64
        self.running = False

    def start(self):
        self.running = True
        self.BLACK = (0, 0, 0)
        while self.running:
            # 处理事件队列
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False

            self.screen.fill(self.BLACK)

            # 可以在窗口上绘制其他内容，例如一个白色矩形
            # pygame.draw.rect(screen, WHITE, (100, 100, 200, 150))
            self.screen.blit(STONE().get_texture(self.block_size), (0, 10))

            # 更新显示（将绘制内容呈现到窗口）
            pygame.display.flip()

        # 退出 Pygame
        pygame.quit()



