import logging
import math
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

import numpy as np
import pygame

from resources.client.camera import Camera

if TYPE_CHECKING:
    from resources.client.client_main import Client


def get_light_level(light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]], x: int, y: int):
    light = light_map[x][y]
    return light / 15


# ===================== 渲染器主体 =====================
class Render:
    def __init__(self, client: 'Client'):
        self.BLACK = None
        pygame.init()
        pygame.mixer.init()
        self.client = client
        self.client_world = client.client_world
        self.SCREEN_WIDTH = 800
        self.SCREEN_HEIGHT = 600
        self.screen = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.RESIZABLE)
        pygame.display.set_caption("PyCraft 2D - 0.0.1 SNAPSHOT")
        self.icon = pygame.image.load("icon.png").convert_alpha()
        pygame.display.set_icon(self.icon)
        self.block_size = 64
        self.running = False
        self.camera = Camera()
        self.font = pygame.font.Font("assets\\minecraft\\font\\Minecraft_AE.ttf", 36)

        # 光照与阴影相关
        self.gradient_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_CACHE_SIZE = 128  # 渐变纹理缓存上限
        self.ao_multiple = 0.05

    # -------------------- 辅助方法 --------------------
    def _is_solid(self, x: int, y: int, z: int) -> bool:
        """
        判断某个世界坐标是否有固体方块。
        超出世界范围视为固体（边界遮蔽）。
        """
        block = self.client_world.get_block(x, y, z)
        return block is not None and block.solid

    def calculate_ao(self, x: int, y: int, z: int) -> tuple[float, float, float, float]:
        """
        计算方块四个角的环境光遮蔽因子（0.0 ~ 1.0，1为无遮蔽）。
        返回顺序：左上、右上、左下、右下。

        仅背景层（z=1）受遮蔽影响，前景层（z=0）无遮蔽。
        """
        # 前景层直接全亮
        if z == 0:
            return 1.0, 1.0, 1.0, 1.0

        # 背景层（z=1）计算与前景层的相互遮挡
        def solid(xx, yy, zz) -> int:
            return 1 if self._is_solid(xx, yy, zz) else 0

        # 左上角
        s = (solid(x - 1, y, 1) +
             solid(x, y + 1, 1) +
             solid(x - 1, y + 1, 1) +
             solid(x - 1, y, 0) +
             solid(x, y + 1, 0) +
             solid(x - 1, y + 1, 0))
        ao_tl = max(0.2, 1.0 - s * self.ao_multiple)

        # 右上角
        s = (solid(x + 1, y, 1) +
             solid(x, y + 1, 1) +
             solid(x + 1, y + 1, 1) +
             solid(x + 1, y, 0) +
             solid(x, y + 1, 0) +
             solid(x + 1, y + 1, 0))
        ao_tr = max(0.2, 1.0 - s * self.ao_multiple)

        # 左下角
        s = (solid(x - 1, y, 1) +
             solid(x, y - 1, 1) +
             solid(x - 1, y - 1, 1) +
             solid(x - 1, y, 0) +
             solid(x, y - 1, 0) +
             solid(x - 1, y - 1, 0))
        ao_bl = max(0.2, 1.0 - s * self.ao_multiple)

        # 右下角
        s = (solid(x + 1, y, 1) +
             solid(x, y - 1, 1) +
             solid(x + 1, y - 1, 1) +
             solid(x + 1, y, 0) +
             solid(x, y - 1, 0) +
             solid(x + 1, y - 1, 0))
        ao_br = max(0.2, 1.0 - s * self.ao_multiple)

        return ao_tl, ao_tr, ao_bl, ao_br

    def get_gradient_surface(self, tl: float, tr: float, bl: float, br: float) -> pygame.Surface:
        """
        生成一个与 block_size 等大的亮度渐变 Surface。
        内部用一个 2x2 纹理记录四个角的亮度，再用 smoothscale 平滑放大。
        结果会被缓存，避免重复生成相同参数的渐变。
        """
        # 将亮度值离散化到一定精度，提高缓存命中率
        key = (round(tl, 3), round(tr, 3), round(bl, 3), round(br, 3))
        if key in self.gradient_cache:
            self.gradient_cache.move_to_end(key)
            return self.gradient_cache[key]

        small = pygame.Surface((2, 2), pygame.SRCALPHA)
        small.fill((int(255 * tl), int(255 * tl), int(255 * tl)), (0, 0, 1, 1))  # 左上
        small.fill((int(255 * tr), int(255 * tr), int(255 * tr)), (1, 0, 1, 1))  # 右上
        small.fill((int(255 * bl), int(255 * bl), int(255 * bl)), (0, 1, 1, 1))  # 左下
        small.fill((int(255 * br), int(255 * br), int(255 * br)), (1, 1, 1, 1))  # 右下

        grad = pygame.transform.smoothscale(small, (self.block_size, self.block_size))

        # 缓存管理
        self.gradient_cache[key] = grad
        if len(self.gradient_cache) > self.MAX_CACHE_SIZE:
            self.gradient_cache.popitem(last=False)

        return grad

    # -------------------- 原有的绘制方法（已修改） --------------------
    def start(self):
        self.running = True
        self.BLACK = (104, 209, 246)
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    self.client.shutdown()
                elif event.type == pygame.VIDEORESIZE:
                    self.SCREEN_WIDTH, self.SCREEN_HEIGHT = event.size
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)

            # 如果正在关闭，跳过渲染
            if not self.running or self.client.is_shutting_down:
                break

            try:
                self.screen.fill(self.BLACK)

                self.camera.update()
                self.draw_block()  # 这里已经加入了光照和 AO
                self.draw_hovered_block_outline()
                self.draw_player()

                pygame.display.flip()
            except pygame.error as e:
                # pygame 已经退出，正常退出循环
                logging.debug(f"Pygame error during shutdown: {e}")
                break

    def draw_block(self):
        """绘制所有可见方块，并应用光照 + 环境光遮蔽"""
        camera_x = self.camera.x
        camera_y = self.camera.y

        x_blocks = math.ceil(self.SCREEN_WIDTH / self.block_size)
        y_blocks = math.ceil(self.SCREEN_HEIGHT / self.block_size)

        x_start = int(camera_x - x_blocks // 2 - 1)
        x_end = int(camera_x + x_blocks // 2 + 2)
        y_start = int(camera_y - y_blocks // 2)
        y_end = int(camera_y + y_blocks // 2 + 2)

        for x in range(x_start, x_end):
            for y in range(y_start, y_end):
                # 保持原有的层绘制顺序（z=0 先，z=1 后）
                for z in range(0, 2):
                    if z == 1 and self.client_world.get_block(x, y, 0).solid:
                        continue  # 被前景固体完全遮挡

                    block = self.client_world.get_block(x, y, z)
                    if block.block_id == 'air':
                        continue

                    # 原始纹理（已经缩放好的）
                    tex = block.get_texture(self.block_size, self.client)
                    if tex is None:
                        continue

                    # 1. 预留光照接口
                    light = get_light_level(self.client_world.light_map, x, y)

                    # 2. 计算环境光遮蔽因子
                    ao_tl, ao_tr, ao_bl, ao_br = self.calculate_ao(x, y, z)

                    # 3. 四角最终亮度 = 光照 × AO
                    tl = light * ao_tl
                    tr = light * ao_tr
                    bl = light * ao_bl
                    br = light * ao_br

                    # 4. 生成亮度渐变图
                    gradient = self.get_gradient_surface(tl, tr, bl, br)

                    # 5. 叠加到方块纹理上（复制一份，避免污染缓存）
                    lit_tex = tex.copy()
                    lit_tex.blit(gradient, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

                    # 6. 绘制到屏幕
                    screen_x = (x - camera_x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
                    screen_y = self.SCREEN_HEIGHT - ((y - camera_y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2)
                    self.screen.blit(lit_tex, (screen_x, screen_y))

    # ---------- 后面这些方法保持不变 ----------
    def draw_player(self):
        pygame.draw.rect(self.screen, (50, 50, 50),
                         ((self.SCREEN_WIDTH - 64) / 2, (self.SCREEN_HEIGHT - 64) / 2, 64, 64))

    def get_hovered_block_position(self):
        mouse_x, mouse_y = pygame.mouse.get_pos()
        camera_x = self.camera.x
        camera_y = self.camera.y
        world_x = (mouse_x - self.SCREEN_WIDTH // 2) / self.block_size + camera_x + 0.5
        world_y = -(mouse_y - self.SCREEN_HEIGHT // 2) / self.block_size + camera_y + 0.5
        block_x = math.floor(world_x)
        block_y = math.floor(world_y)
        distance = math.sqrt(
            (mouse_x - self.SCREEN_WIDTH / 2) ** 2 + (mouse_y - self.SCREEN_HEIGHT / 2) ** 2) / self.block_size
        if distance > self.client.client_player.interact_range:
            return None, None
        self.client.client_player.choosing_block = (block_x, block_y)
        return block_x, block_y

    def draw_hovered_block_outline(self):
        block_x, block_y = self.get_hovered_block_position()
        if block_x is None or block_y is None:
            return
        camera_x = self.camera.x
        camera_y = self.camera.y
        screen_x = (block_x - camera_x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
        screen_y = self.SCREEN_HEIGHT - ((block_y - camera_y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2)
        outline_rect = pygame.Rect(screen_x, screen_y, self.block_size, self.block_size)
        pygame.draw.rect(self.screen, (0, 0, 0), outline_rect, 1)