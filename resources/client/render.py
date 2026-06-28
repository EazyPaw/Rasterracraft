import logging
import math
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Optional

import numpy as np
import pygame

from resources.client.GUI.gui import GUI
from resources.client.camera import Camera
from resources.server.blocks import AIR

if TYPE_CHECKING:
    from resources.client.client_main import Client
    from resources.server.block_class import Block


# ===================== 保留原有模块级接口 =====================
def get_light_level(light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]], x: int, y: int):
    """
    获取某个世界坐标的亮度。
    """
    rx = x // 16
    chunk_light_map = light_map.get(rx)

    if chunk_light_map is None:
        return 0

    local_x = x % 16
    if y < 0:
        return 0

    if y >= chunk_light_map.shape[1]:
        return 15

    try:
        light = chunk_light_map[local_x, y]
        return light / 15.0
    except IndexError:
        return 0


def get_light_levels_at(light_map: dict[int, np.ndarray[Any, np.dtype[np.uint8]]], x: int, y: int):
    """
    返回方块四个角落的光照值（左上、右上、左下、右下）。
    采用"边-角-边-中心"四点平均算法。
    """
    center = get_light_level(light_map, x, y)
    tl = (get_light_level(light_map, x - 1, y) +
          get_light_level(light_map, x - 1, y + 1) +
          get_light_level(light_map, x, y + 1) +
          center) / 4.0
    tr = (get_light_level(light_map, x, y + 1) +
          get_light_level(light_map, x + 1, y + 1) +
          get_light_level(light_map, x + 1, y) +
          center) / 4.0
    bl = (get_light_level(light_map, x - 1, y) +
          get_light_level(light_map, x - 1, y - 1) +
          get_light_level(light_map, x, y - 1) +
          center) / 4.0
    br = (get_light_level(light_map, x, y - 1) +
          get_light_level(light_map, x + 1, y - 1) +
          get_light_level(light_map, x + 1, y) +
          center) / 4.0
    return tl, tr, bl, br

def color_tint(image, new_color):
    """使用混合模式对图像进行染色"""
    # 创建一个图像的副本，避免修改原始图像
    tinted_image = image.copy()
    # 第一步：用 BLEND_RGBA_MULT 将RGB通道归零，保留原始Alpha通道
    tinted_image.fill((0, 0, 0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    # 第二步：用 BLEND_RGBA_ADD 将新的RGB颜色加上
    # 注意：要忽略alpha通道，所以用 (new_color[0], new_color[1], new_color[2], 0)
    tinted_image.fill((*new_color, 0), special_flags=pygame.BLEND_RGBA_ADD)
    return tinted_image


# ===================== 渲染器 =====================
class Render:
    def __init__(self, client: 'Client'):
        self.sky_base = None
        pygame.init()
        pygame.mixer.init()
        self.debug = False
        self.client = client
        self.client_world = client.client_world
        self.SCREEN_WIDTH = 800
        self.SCREEN_HEIGHT = 600
        self.screen = pygame.display.set_mode(
            (self.SCREEN_WIDTH, self.SCREEN_HEIGHT),
            pygame.RESIZABLE
        )
        pygame.display.set_caption("PyCraft 2D - 0.0.1 SNAPSHOT")
        self.icon = pygame.image.load("icon.png").convert_alpha()
        pygame.display.set_icon(self.icon)
        self.block_size = 64
        self.trans_scale = self.block_size / 16
        self.gui_scale = 3.5
        self.running = False
        self.camera = Camera()
        self.mouse_x = 0
        self.mouse_y = 0
        self.choosing_position = (0, 0)
        self.font_path = "assets\\minecraft\\font\\Minecraft_AE.ttf"
        self.default_font = pygame.font.Font("assets\\minecraft\\font\\Minecraft_AE.ttf", 36)
        self.font_cache = {}
        self.events = []
        self.sky_layer_origin = self.get_sky_layer()
        self.sky_layer = self.get_sky_layer()
        self.sky_layer_surface = None
        self.last_sky_color = None
        self.sky_layer_color = (192, 216, 255, 0)
        self.ig_gui_layer = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)
        self.ig_gui_layer.fill((0, 0, 0, 128))

        # 光照与阴影相关缓存
        self.gradient_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_GRADIENT_CACHE = 128  # 渐变纹理缓存上限
        self.lit_tex_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_LIT_CACHE = 256  # 最终光照纹理缓存上限
        self.ao_multiple = 0.05

        self.drawing_GUIs: list[GUI] = [] # 需要绘制的 GUI

        self.blit = self.screen.blit    # 供外部使用的绘制方法，便于在必要情况下更换渲染器

    def transform_pos(self, pos: tuple[float, float]) -> tuple[float, float]:
        """
        将相对屏幕的坐标转换为绝对坐标，用于handle屏幕大小的改变
        :param pos: 相对坐标 （0~100之间）
        :return: 绝对坐标
        """
        x = pos[0] / 100 * self.SCREEN_WIDTH
        y = pos[1] / 100 * self.SCREEN_HEIGHT
        return x, y

    def trans_world_location(self, pos: tuple[float, float]) -> tuple[float, float]:
        """
        将世界坐标转换为屏幕坐标
        :param pos: 世界坐标 (world_x, world_y)
        :return: 屏幕坐标 (screen_x, screen_y)
        """
        world_x, world_y = pos
        screen_x = (world_x - self.camera.x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
        screen_y = self.SCREEN_HEIGHT - ((world_y - self.camera.y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2)
        return screen_x, screen_y

    # ---------- 主循环 ----------
    def start(self):
        self.running = True
        self.sky_base = (120, 167, 255)
        clock = pygame.time.Clock()

        while self.running:
            self.events = pygame.event.get()
            for event in self.events:
                if event.type == pygame.QUIT:
                    self.running = False
                    self.client.shutdown()
                elif event.type == pygame.VIDEORESIZE:
                    self.SCREEN_WIDTH, self.SCREEN_HEIGHT = event.size
                    self.screen = pygame.display.set_mode(event.size, pygame.RESIZABLE)
                    self.sky_layer_origin = self.get_sky_layer()
                    self.last_sky_color = None # 借 last_sky_color 刷新天空的渲染
                    self.ig_gui_layer = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)
                    self.ig_gui_layer.fill((0, 0, 0, 128))
                else:
                    # 把键盘、鼠标等游戏事件转发给 GameManager
                    self.client.game_manager.event_queue.append(event)

            if not self.running or self.client.is_shutting_down:
                break

            try:
                self.draw_sky()
                self.camera.update()
                self.draw_block()
                self.draw_hovered_block_outline()
                self.client.client_player.skeleton.update()
                self.draw_player()
                self.draw_gui()

                fps = clock.get_fps()
                #fps_text = self.default_font.render(f"FPS: {int(fps)}", True, (255, 255, 255))
                #self.screen.blit(fps_text, (10, 10))
                self.render_text(f"FPS: {int(fps)}", (10, 10), (255, 255, 255), 36, True)

                pygame.display.flip()
                clock.tick(250)

            except pygame.error as e:
                logging.debug(f"Pygame error during shutdown: {e}")
                break

    def draw_sky(self):
        """绘制天空"""
        self.screen.fill(self.sky_base)
        if self.last_sky_color != self.sky_base:
            self.sky_layer = self.sky_layer_origin.copy()
            self.sky_layer.fill(self.sky_layer_color, special_flags=pygame.BLEND_RGB_MULT)
            self.last_sky_color = self.sky_base
        self.screen.blit(self.sky_layer, (0, 0))

    def render_text(self, text: str, pos: tuple[float, float], color: tuple[int, int, int] = (255, 255, 255)
                    , font_size: int = 36, shadow: bool = False, glow: bool = False):
        text_surface = self.get_font(font_size).render(text, True, color)
        if shadow:
            shadow_text = self.get_font(font_size).render(text, True, tuple(int(x * 0.4) for x in color))
            self.screen.blit(shadow_text, (pos[0] + font_size / 8, pos[1] + font_size / 8))
        self.screen.blit(text_surface, pos)

    def get_sky_layer(self):
        """获取天空层"""
        # 创建一个与屏幕大小相同的半透明Surface
        sky_layer = pygame.Surface((self.SCREEN_WIDTH, self.SCREEN_HEIGHT), pygame.SRCALPHA)

        height = self.SCREEN_HEIGHT
        
        # 遍历每个像素行，创建渐变效果
        for y in range(height):
            # 计算透明度：上1/3完全透明(0)，下1/3纯白(255)，中间过渡
            if y < height / 3:
                # 上1/3：完全透明
                alpha = 0
            elif y > 2 * height / 3:
                # 下1/3：纯白（完全不透明的白色）
                alpha = 255
            else:
                # 中间1/3：线性过渡
                progress = (y - height / 3) / (height / 3)
                alpha = int(progress * 255)
            
            # 绘制一行，颜色为白色，透明度根据位置变化
            pygame.draw.line(sky_layer, (255, 255, 255, alpha), (0, y), (self.SCREEN_WIDTH - 1, y))

        sky_layer.convert_alpha()

        return sky_layer

    def draw_block(self):
        """绘制所有可见方块，应用光照+AO，使用批量预取与缓存策略"""
        # ---- 局部变量绑定，消除属性查找开销 ----
        screen = self.screen
        block_size = self.block_size
        cam_x = self.camera.x
        cam_y = self.camera.y
        cw = self.client_world
        light_map = cw.light_map
        get_block = cw.get_block
        width = self.SCREEN_WIDTH
        height = self.SCREEN_HEIGHT
        ao_mul = self.ao_multiple
        debug = self.debug
        font = self.default_font

        # ---- 可见范围 ----
        x_blocks = math.ceil(width / block_size)
        y_blocks = math.ceil(height / block_size)
        x_start = int(cam_x - x_blocks // 2 - 1)
        x_end = int(cam_x + x_blocks // 2 + 2)
        y_start = int(cam_y - y_blocks // 2 - 1)
        y_end = int(cam_y + y_blocks // 2 + 2)

        # 扩展一圈用于 AO / 光照邻域
        x_min = x_start - 1
        x_max = x_end + 1
        y_min = y_start - 1
        y_max = y_end + 1

        x_len = x_max - x_min + 1
        y_len = y_max - y_min + 1

        # ---- 预取区块信息 ----
        # block_info:   bit0 = z0固体, bit1 = z1固体
        # blocks0/1:    方块对象
        # light_levels: 归一化光照 0.0-1.0
        block_info = [[0] * y_len for _ in range(x_len)]
        blocks0: list[list[Optional['Block']]] = [[None] * y_len for _ in range(x_len)]
        blocks1: list[list[Optional['Block']]] = [[None] * y_len for _ in range(x_len)]
        light_levels = [[0.0] * y_len for _ in range(x_len)]

        for i in range(x_len):
            x = x_min + i
            chunk_light = light_map.get(x // 16)  # 一次取区块
            local_x = x % 16
            for j in range(y_len):
                y = y_min + j
                b0 = get_block(x, y, 0)
                b1 = get_block(x, y, 1)
                solid0 = 1 if (b0 and b0.solid) else 0
                solid1 = 1 if (b1 and b1.solid) else 0
                block_info[i][j] = solid0 | (solid1 << 1)
                blocks0[i][j] = b0
                blocks1[i][j] = b1

                # 光照
                if chunk_light is not None and 0 <= y < chunk_light.shape[1]:
                    light_levels[i][j] = chunk_light[local_x, y] / 15.0

        # ---- 内联辅助函数 ----
        def is_solid(x, y, z):
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return True  # 边界视为固体
            i = x - x_min
            j = y - y_min
            return (block_info[i][j] & (1 << z)) != 0

        def get_light(x, y):
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return 0.0
            return light_levels[x - x_min][y - y_min]

        # ---- 绘制循环 ----
        for x in range(x_start, x_end + 1):
            i = x - x_min
            for y in range(y_start, y_end + 1):
                j = y - y_min
                b0 = blocks0[i][j]
                b1 = blocks1[i][j]

                # ---- z = 0 层 ----
                if b0 is not None and b0.block_id != 'air':
                    self._draw_block_optimized(
                        screen, block_size, cam_x, cam_y, width, height,
                        x, y, 0, b0,
                        light_levels, block_info, is_solid, get_light,
                        x_min, y_min, ao_mul, debug, font
                    )

                # ---- z = 1 层 ----
                if b1 is not None and b1.block_id != 'air':
                    if b0 and b0.solid:
                        continue
                    self._draw_block_optimized(
                        screen, block_size, cam_x, cam_y, width, height,
                        x, y, 1, b1,
                        light_levels, block_info, is_solid, get_light,
                        x_min, y_min, ao_mul, debug, font
                    )

    def _draw_block_optimized(self, screen, bs, cam_x, cam_y, sw, sh,
                              x, y, z, block,
                              light_levels, block_info, is_solid, get_light,
                              x_min, y_min, ao_mul, debug, font):
        """绘制单个方块，所有计算内联，使用两级缓存"""
        # ---- 1. 四角光照（内联计算） ----
        center = get_light(x, y)
        tl = (get_light(x - 1, y) + get_light(x - 1, y + 1) + get_light(x, y + 1) + center) * 0.25
        tr = (get_light(x, y + 1) + get_light(x + 1, y + 1) + get_light(x + 1, y) + center) * 0.25
        bl = (get_light(x - 1, y) + get_light(x - 1, y - 1) + get_light(x, y - 1) + center) * 0.25
        br = (get_light(x, y - 1) + get_light(x + 1, y - 1) + get_light(x + 1, y) + center) * 0.25

        # ---- 2. AO ----
        if z == 0:
            ao_tl = ao_tr = ao_bl = ao_br = 1.0
        else:
            s_tl = (is_solid(x - 1, y, 1) + is_solid(x, y + 1, 1) + is_solid(x - 1, y + 1, 1) +
                    is_solid(x - 1, y, 0) + is_solid(x, y + 1, 0) + is_solid(x - 1, y + 1, 0))
            ao_tl = max(0.2, 1.0 - s_tl * ao_mul)

            s_tr = (is_solid(x + 1, y, 1) + is_solid(x, y + 1, 1) + is_solid(x + 1, y + 1, 1) +
                    is_solid(x + 1, y, 0) + is_solid(x, y + 1, 0) + is_solid(x + 1, y + 1, 0))
            ao_tr = max(0.2, 1.0 - s_tr * ao_mul)

            s_bl = (is_solid(x - 1, y, 1) + is_solid(x, y - 1, 1) + is_solid(x - 1, y - 1, 1) +
                    is_solid(x - 1, y, 0) + is_solid(x, y - 1, 0) + is_solid(x - 1, y - 1, 0))
            ao_bl = max(0.2, 1.0 - s_bl * ao_mul)

            s_br = (is_solid(x + 1, y, 1) + is_solid(x, y - 1, 1) + is_solid(x + 1, y - 1, 1) +
                    is_solid(x + 1, y, 0) + is_solid(x, y - 1, 0) + is_solid(x + 1, y - 1, 0))
            ao_br = max(0.2, 1.0 - s_br * ao_mul)

        # ---- 3. 最终角亮度 ----
        ftl = tl * ao_tl
        ftr = tr * ao_tr
        fbl = bl * ao_bl
        fbr = br * ao_br

        # ---- 4. 屏幕坐标 ----
        # 方块占据世界坐标 [y, y+1]，此处用 y+1（方块顶部）定位，
        # 纹理从顶部向下绘制，保证与 trans_world_location 一致。
        sx = (x - cam_x - 0.5) * bs + sw // 2
        sy = sh - (((y + 1) - cam_y + 0.5) * bs + sh // 2)

        # ---- 5. 全黑快速路径 ----
        if ftl == 0.0 and ftr == 0.0 and fbl == 0.0 and fbr == 0.0:
            pygame.draw.rect(screen, (0, 0, 0), (sx, sy, bs, bs))
            # 调试文本
            if debug:
                light_val = int(get_light(x, y) * 15)
                text = font.render(str(light_val), True, (255, 255, 255))
                text_rect = text.get_rect(center=(sx + bs // 2, sy + bs // 2))
                screen.blit(text, text_rect)
            return

        # ---- 6. 获取纹理 ----
        tex = block.get_texture(bs)
        if tex is None:
            return

        # ---- 7. 光照纹理缓存 ----
        # 键使用 block_id 与离散化亮度（0-255）
        key = (block.block_id, int(ftl * 255), int(ftr * 255), int(fbl * 255), int(fbr * 255))
        cache = self.lit_tex_cache
        if key in cache:
            lit_tex = cache[key]
            cache.move_to_end(key)
        else:
            # 7a. 获取/生成渐变纹理
            grad_key = (round(ftl, 3), round(ftr, 3), round(fbl, 3), round(fbr, 3))
            grad_cache = self.gradient_cache
            if grad_key in grad_cache:
                grad = grad_cache[grad_key]
                grad_cache.move_to_end(grad_key)
            else:
                small = pygame.Surface((2, 2), pygame.SRCALPHA)
                small.fill((int(255 * ftl),) * 3, (0, 0, 1, 1))
                small.fill((int(255 * ftr),) * 3, (1, 0, 1, 1))
                small.fill((int(255 * fbl),) * 3, (0, 1, 1, 1))
                small.fill((int(255 * fbr),) * 3, (1, 1, 1, 1))
                # 改用 scale 代替 smoothscale，速度提升显著，画质略有下降但可接受
                grad = pygame.transform.smoothscale(small, (bs, bs)).convert_alpha()
                grad_cache[grad_key] = grad
                if len(grad_cache) > self.MAX_GRADIENT_CACHE:
                    grad_cache.popitem(last=False)

            # 7b. 生成最终光照纹理
            lit_tex = tex.copy()
            lit_tex.blit(grad, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            cache[key] = lit_tex
            if len(cache) > self.MAX_LIT_CACHE:
                cache.popitem(last=False)

        # ---- 8. 绘制到屏幕 ----
        screen.blit(lit_tex, (sx, sy))

        # ---- 9. 调试文本（仅在 debug=True 时） ----
        if debug:
            light_val = int(get_light(x, y) * 15)
            text = font.render(str(light_val), True, (255, 255, 255))
            text_rect = text.get_rect(center=(sx + bs // 2, sy + bs // 2))
            screen.blit(text, text_rect)

    def draw_gui(self):
        for gui in self.drawing_GUIs:
            gui.draw()

    def draw_player(self):
        self.client.client_player.skeleton.draw()
        pygame.draw.rect(
            self.screen, (0, 0, 255),
            ((self.SCREEN_WIDTH - 2) / 2, (self.SCREEN_HEIGHT - 2) / 2, 2, 2)
        )

    def get_hovered_block_position(self):
        self.mouse_x, self.mouse_y = pygame.mouse.get_pos()
        camera_x = self.camera.x
        camera_y = self.camera.y
        world_x = (self.mouse_x - self.SCREEN_WIDTH // 2) / self.block_size + camera_x + 0.5
        world_y = -(self.mouse_y - self.SCREEN_HEIGHT // 2) / self.block_size + camera_y - 0.5
        block_x = math.floor(world_x)
        block_y = math.floor(world_y)
        distance = math.sqrt(
            (self.mouse_x - self.SCREEN_WIDTH / 2) ** 2 +
            (self.mouse_y - self.SCREEN_HEIGHT / 2) ** 2
        ) / self.block_size
        if distance > self.client.client_player.interact_range:
            return None, None
        self.choosing_position = (block_x, block_y)
        return block_x, block_y

    def draw_hovered_block_outline(self):
        block_x, block_y = self.get_hovered_block_position()
        if block_x is None or block_y is None:
            return
        camera_x = self.camera.x
        camera_y = self.camera.y
        screen_x = (block_x - camera_x - 0.5) * self.block_size + self.SCREEN_WIDTH // 2
        # 方块占据世界坐标 [block_y, block_y+1]，用 block_y+1 定位顶部，与 _draw_block_optimized 一致
        screen_y = self.SCREEN_HEIGHT - (((block_y + 1) - camera_y + 0.5) * self.block_size + self.SCREEN_HEIGHT // 2)
        outline_rect = pygame.Rect(screen_x, screen_y, self.block_size, self.block_size)
        pygame.draw.rect(self.screen, (0, 0, 0), outline_rect, 1)

    def debug_mode(self):
        self.debug = not self.debug

    def get_font(self, size) -> pygame.font.Font:
        if self.font_cache.get(size) is not None:
            return self.font_cache.get(size)
        font = pygame.font.Font(self.font_path, size)
        if self.font_cache.get(size) is None:
            self.font_cache[size] = font
        return font

    def show_gui(self, gui: GUI):
        self.drawing_GUIs.append(gui)
        self.drawing_GUIs.sort(key=lambda gui_: gui_.priority)
        gui.on_open()

    def close_gui(self, gui: GUI):
        self.drawing_GUIs.remove(gui)
        gui.on_close()



