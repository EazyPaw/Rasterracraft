"""
方块渲染 Mixin
==============
提供世界中方块的批量绘制功能，包括光照计算、环境光遮蔽 (AO)、
纹理着色与缓存等。
"""

import math as _math
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Optional

import pygame

from .constants import (
    BLOCK_LIGHT_LEVELS,
    BLOCK_LIGHT_TINT,
    BLOCK_RATIO_LEVELS,
    BLOCK_TINT_COLOR_STEP,
)
from .math_utils import clamp, cyclic_lerp_color, lerp_color, quantize_color, quantize_unit

if TYPE_CHECKING:
    from resources.server.block_class import Block


class BlockRenderMixin:
    """方块渲染 Mixin，提供光照+AO 方块绘制能力。

    需要宿主类提供以下属性：
        - screen: pygame 主 Surface
        - block_size: 方块渲染尺寸
        - camera: 相机对象（含 x, y 属性）
        - client_world: 世界对象（含 light_map, get_block 等）
        - current_sky_state: 当前天空状态
        - day_time: 当前游戏时间
        - gradient_cache, lit_tex_cache, corner_color_cache: 渲染缓存
        - MAX_GRADIENT_CACHE, MAX_LIT_CACHE, MAX_CORNER_COLOR_CACHE: 缓存上限
        - ao_multiple: AO 系数
        - debug: 调试开关
        - default_font: 默认字体
        - SKY_LOWER_KEYFRAMES: 天空下层颜色关键帧
    """

    def _compute_corner_color(
        self,
        brightness: float,
        sky_ratio: float,
        sky_color: tuple[int, int, int],
    ) -> tuple[int, int, int]:
        """根据亮度和天空/方块光源比例计算角落着色颜色。

        算法：
        - brightness=0 → (0,0,0)，brightness=1 → (255,255,255)
        - 中间亮度时混入光源色调（天空色或方块光源暖色）
        - 色调强度在亮度 0.5 时最大，两端收敛为纯灰阶

        参数:
            brightness: 亮度值 [0, 1]
            sky_ratio: 天空光照占比 [0, 1]（0=纯方块光源，1=纯天空光源）
            sky_color: 天空颜色 RGB

        返回:
            着色后的 RGB 颜色元组
        """
        b_key, b = quantize_unit(brightness, BLOCK_LIGHT_LEVELS)
        r_key, sky_ratio = quantize_unit(sky_ratio, BLOCK_RATIO_LEVELS)
        key = (b_key, r_key, sky_color)

        cache = self.corner_color_cache
        if key in cache:
            cache.move_to_end(key)
            return cache[key]

        base = int(b * 255)
        # 色调强度：亮度 0 和 1 时为 0，亮度 0.5 时最大（二次函数 b*(1-b)*4）
        tint_amount = b * (1.0 - b) * 4.0

        if tint_amount < 0.005:
            # 色调可忽略，直接返回灰阶
            result = (base, base, base)
        else:
            tint = lerp_color(BLOCK_LIGHT_TINT, sky_color, sky_ratio)
            # 保持亮度不变，只改变色相（通过缩放保持亮度分量）
            tint_lum = tint[0] * 0.299 + tint[1] * 0.587 + tint[2] * 0.114
            if tint_lum > 0:
                scale = base / tint_lum
                scaled = (
                    min(255, int(tint[0] * scale)),
                    min(255, int(tint[1] * scale)),
                    min(255, int(tint[2] * scale)),
                )
            else:
                scaled = (base, base, base)
            result = lerp_color((base, base, base), scaled, tint_amount)

        # 写入缓存并维持 LRU 淘汰
        cache[key] = result
        if len(cache) > self.MAX_CORNER_COLOR_CACHE:
            cache.popitem(last=False)
        return result

    def draw_block(self) -> None:
        """批量绘制所有可见方块，应用光照+AO。

        采用三步优化策略：
        1. 预取批次：一次性读取整个可见区域+邻域的区块数据
        2. 缓存纹理：基于光照参数构建缓存键，复用光照纹理
        3. 内联计算：关键路径使用内联辅助函数消除函数调用开销

        绘制顺序：先 z=1（前景），后 z=0（背景）。
        """
        # ---- 局部变量绑定，消除属性查找开销 ----
        screen = self.screen
        block_size = self.block_size
        cam_x = self.camera.x
        cam_y = self.camera.y
        cw = self.client_world
        light_map = cw.light_map
        sky_light_map = getattr(cw, "sky_light_map", {})
        block_light_map = getattr(cw, "block_light_map", {})
        NIGHT_TINT = (36, 48, 128)

        # 获取当前天空状态
        sky_state = self.current_sky_state or self.get_sky_state()
        sky_light_weight = sky_state["sky_light_weight"]

        # 计算当前天空颜色（含暮色和夜间色调）
        sky_color = lerp_color(
            cyclic_lerp_color(self.SKY_LOWER_KEYFRAMES, self.day_time),
            sky_state["twilight_color"],
            sky_state["twilight"],
        )
        sky_color = lerp_color(sky_color, NIGHT_TINT, sky_state["night"] * 0.85)
        sky_color = quantize_color(sky_color, BLOCK_TINT_COLOR_STEP)

        get_block = cw.get_block
        width = self.SCREEN_WIDTH
        height = self.SCREEN_HEIGHT
        ao_mul = self.ao_multiple
        debug = self.debug
        font = self.default_font

        # ---- 计算可见方块范围 ----
        x_blocks = _math.ceil(width / block_size)
        y_blocks = _math.ceil(height / block_size)
        x_start = int(cam_x - x_blocks // 2 - 1)
        x_end = int(cam_x + x_blocks // 2 + 2)
        y_start = int(cam_y - y_blocks // 2 - 1)
        y_end = int(cam_y + y_blocks // 2 + 2)

        # 扩展一圈用于 AO / 光照邻域计算
        x_min = x_start - 1
        x_max = x_end + 1
        y_min = y_start - 1
        y_max = y_end + 1

        x_len = x_max - x_min + 1
        y_len = y_max - y_min + 1

        # ---- 预取区块数据（批量读取，减少属性访问） ----
        # block_info:   bit0 = z0固体, bit1 = z1固体
        # blocks0/1:    方块对象引用
        # light_levels: 归一化总光照 [0, 1]
        # sky_levels:   归一化天空光照贡献 [0, 1]
        # block_light_levels: 归一化方块光照贡献 [0, 1]
        block_info = [[0] * y_len for _ in range(x_len)]
        blocks0: list[list[Optional['Block']]] = [[None] * y_len for _ in range(x_len)]
        blocks1: list[list[Optional['Block']]] = [[None] * y_len for _ in range(x_len)]
        light_levels = [[0.0] * y_len for _ in range(x_len)]
        sky_levels = [[0.0] * y_len for _ in range(x_len)]
        block_light_levels = [[0.0] * y_len for _ in range(x_len)]

        for i in range(x_len):
            x = x_min + i
            # 按区块索引批量获取光照数据
            chunk_light = light_map.get(x // 16)
            chunk_sky_light = sky_light_map.get(x // 16)
            chunk_block_light = block_light_map.get(x // 16)
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

                # 分离天空光照和方块光照
                if chunk_sky_light is not None and chunk_block_light is not None:
                    if y >= chunk_sky_light.shape[1]:
                        sky_light = 15.0
                        block_light = 0.0
                    elif y >= 0:
                        sky_light = float(chunk_sky_light[local_x, y])
                        block_light = float(chunk_block_light[local_x, y])
                    else:
                        sky_light = 0.0
                        block_light = 0.0
                    sky_levels[i][j] = sky_light / 15.0 * sky_light_weight
                    block_light_levels[i][j] = block_light / 15.0
                    light_levels[i][j] = min(1.0, sky_levels[i][j] + block_light_levels[i][j])
                elif chunk_light is not None and 0 <= y < chunk_light.shape[1]:
                    light_levels[i][j] = chunk_light[local_x, y] * sky_light_weight / 15.0
                    sky_levels[i][j] = light_levels[i][j]
                    block_light_levels[i][j] = 0.0

        # ---- 内联辅助函数（闭包捕获预取数据，消除重复边界检查） ----
        def is_solid(x: int, y: int, z: int) -> bool:
            """判断方块是否固体（超出边界视为固体用于 AO 计算）。"""
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return True
            i = x - x_min
            j = y - y_min
            return (block_info[i][j] & (1 << z)) != 0

        def get_light(x: int, y: int) -> float:
            """安全获取总光照值。"""
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return 0.0
            return light_levels[x - x_min][y - y_min]

        def get_sky(x: int, y: int) -> float:
            """安全获取天空光照值。"""
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return 0.0
            return sky_levels[x - x_min][y - y_min]

        def get_block_l(x: int, y: int) -> float:
            """安全获取方块光照值。"""
            if x < x_min or x > x_max or y < y_min or y > y_max:
                return 0.0
            return block_light_levels[x - x_min][y - y_min]

        # ---- 主绘制循环 ----
        for x in range(x_start, x_end + 1):
            i = x - x_min
            for y in range(y_start, y_end + 1):
                j = y - y_min
                b0 = blocks0[i][j]
                b1 = blocks1[i][j]

                if b1 is not None and b1.block_id != 'air' and b0.has_transparent_pixels:
                    self._draw_block_optimized(
                        screen, block_size, cam_x, cam_y, width, height,
                        x, y, 1, b1,
                        light_levels, block_info, is_solid, get_light,
                        get_sky, get_block_l, sky_color,
                        x_min, y_min, ao_mul, debug, font,
                    )

                if b0 is not None and b0.block_id != 'air':
                    self._draw_block_optimized(
                        screen, block_size, cam_x, cam_y, width, height,
                        x, y, 0, b0,
                        light_levels, block_info, is_solid, get_light,
                        get_sky, get_block_l, sky_color,
                        x_min, y_min, ao_mul, debug, font,
                    )

    def _draw_block_optimized(
        self,
        screen: pygame.Surface,
        bs: int,
        cam_x: float,
        cam_y: float,
        sw: float,
        sh: float,
        x: int,
        y: int,
        z: int,
        block: 'Block',
        light_levels: list[list[float]],
        block_info: list[list[int]],
        is_solid,
        get_light,
        get_sky,
        get_block_l,
        sky_color: tuple[int, int, int],
        x_min: int,
        y_min: int,
        ao_mul: float,
        debug: bool,
        font: pygame.font.Font,
    ) -> None:
        """绘制单个方块，应用四角光照 + AO + 纹理缓存。

        管线：
        1. 计算四角总光照（TL/TR/BL/BR 四点平均）
        2. 分离天空/方块光照贡献，计算天空占比
        3. AO 计算（仅 z=1 层受周围实体方块影响）
        4. 计算最终角颜色（含色调）
        5. 从缓存获取/生成光照纹理
        6. 绘制到屏幕

        参数较多以消除属性访问开销——这是每帧调用的热路径。
        """
        # ---- 1. 四角总光照（四点平均平滑） ----
        center = get_light(x, y)
        tl = (get_light(x - 1, y) + get_light(x - 1, y + 1) + get_light(x, y + 1) + center) * 0.25
        tr = (get_light(x, y + 1) + get_light(x + 1, y + 1) + get_light(x + 1, y) + center) * 0.25
        bl = (get_light(x - 1, y) + get_light(x - 1, y - 1) + get_light(x, y - 1) + center) * 0.25
        br = (get_light(x, y - 1) + get_light(x + 1, y - 1) + get_light(x + 1, y) + center) * 0.25

        # ---- 1b. 四角天空/方块光照分离 ----
        center_sky = get_sky(x, y)
        tl_sky = (get_sky(x - 1, y) + get_sky(x - 1, y + 1) + get_sky(x, y + 1) + center_sky) * 0.25
        tr_sky = (get_sky(x, y + 1) + get_sky(x + 1, y + 1) + get_sky(x + 1, y) + center_sky) * 0.25
        bl_sky = (get_sky(x - 1, y) + get_sky(x - 1, y - 1) + get_sky(x, y - 1) + center_sky) * 0.25
        br_sky = (get_sky(x, y - 1) + get_sky(x + 1, y - 1) + get_sky(x + 1, y) + center_sky) * 0.25

        center_bl = get_block_l(x, y)
        tl_bl = (get_block_l(x - 1, y) + get_block_l(x - 1, y + 1) + get_block_l(x, y + 1) + center_bl) * 0.25
        tr_bl = (get_block_l(x, y + 1) + get_block_l(x + 1, y + 1) + get_block_l(x + 1, y) + center_bl) * 0.25
        bl_bl = (get_block_l(x - 1, y) + get_block_l(x - 1, y - 1) + get_block_l(x, y - 1) + center_bl) * 0.25
        br_bl = (get_block_l(x, y - 1) + get_block_l(x + 1, y - 1) + get_block_l(x + 1, y) + center_bl) * 0.25

        # ---- 1c. 计算各角天空光照占比 ----
        def _sky_ratio(sky_v: float, block_v: float) -> float:
            """计算天空光照在总光照中的占比（用于色调混合）。"""
            total = sky_v + block_v
            return sky_v / total if total > 0.001 else 0.5

        sr_tl = _sky_ratio(tl_sky, tl_bl)
        sr_tr = _sky_ratio(tr_sky, tr_bl)
        sr_bl = _sky_ratio(bl_sky, bl_bl)
        sr_br = _sky_ratio(br_sky, br_bl)

        # ---- 2. AO 环境光遮蔽 ----
        # 仅 z=1 层受周围方块遮挡影响
        if z == 0:
            ao_tl = ao_tr = ao_bl = ao_br = 1.0
        else:
            # 统计各角 6 个邻域方块中的固体数量
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

        # ---- 3. 最终角亮度 = 光照 × AO ----
        ftl = tl * ao_tl
        ftr = tr * ao_tr
        fbl = bl * ao_bl
        fbr = br * ao_br

        # ---- 3b. 离散化用于缓存键 ----
        q_ftl, ftl_q = quantize_unit(ftl, BLOCK_LIGHT_LEVELS)
        q_ftr, ftr_q = quantize_unit(ftr, BLOCK_LIGHT_LEVELS)
        q_fbl, fbl_q = quantize_unit(fbl, BLOCK_LIGHT_LEVELS)
        q_fbr, fbr_q = quantize_unit(fbr, BLOCK_LIGHT_LEVELS)
        q_sr_tl, sr_tl_q = quantize_unit(sr_tl, BLOCK_RATIO_LEVELS)
        q_sr_tr, sr_tr_q = quantize_unit(sr_tr, BLOCK_RATIO_LEVELS)
        q_sr_bl, sr_bl_q = quantize_unit(sr_bl, BLOCK_RATIO_LEVELS)
        q_sr_br, sr_br_q = quantize_unit(sr_br, BLOCK_RATIO_LEVELS)

        # ---- 3c. 计算着色后的角落 RGB ----
        color_tl = self._compute_corner_color(ftl_q, sr_tl_q, sky_color)
        color_tr = self._compute_corner_color(ftr_q, sr_tr_q, sky_color)
        color_bl = self._compute_corner_color(fbl_q, sr_bl_q, sky_color)
        color_br = self._compute_corner_color(fbr_q, sr_br_q, sky_color)

        # ---- 4. 屏幕坐标 ----
        # 方块占据世界坐标 [y, y+1]，用 y+1 定位顶部，纹理从顶部向下绘制
        sx = (x - cam_x - 0.5) * bs + sw // 2
        sy = sh - (((y + 1) - cam_y + 0.5) * bs + sh // 2)

        # ---- 5. 全黑快速路径 ----
        # 完全无光且无透明像素的方块直接绘制黑色矩形
        if ftl == 0.0 and ftr == 0.0 and fbl == 0.0 and fbr == 0.0 and not block.has_transparent_pixels:
            pygame.draw.rect(screen, (0, 0, 0), (sx, sy, bs, bs))
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

        tex_h = tex.get_height()

        # ---- 7. 光照纹理缓存 ----
        # 构建缓存键：包含方块ID、纹理帧标识、离散化光照和色调
        sky_key = (
            sky_color[0] // BLOCK_TINT_COLOR_STEP,
            sky_color[1] // BLOCK_TINT_COLOR_STEP,
            sky_color[2] // BLOCK_TINT_COLOR_STEP,
        )
        key = (
            block.block_id, id(tex),
            q_ftl, q_ftr, q_fbl, q_fbr,
            q_sr_tl, q_sr_tr, q_sr_bl, q_sr_br,
            sky_key,
        )

        cache = self.lit_tex_cache
        if key in cache:
            lit_tex = cache[key]
            cache.move_to_end(key)
        elif tex_h < bs:
            # ---- 非完整高度方块（如雪层） ----
            # 为纹理实际高度创建独立渐变，避免与下方方块光照叠加造成视觉断层
            ratio = tex_h / bs
            color_tl_p = lerp_color(color_bl, color_tl, ratio)
            color_tr_p = lerp_color(color_br, color_tr, ratio)

            small = pygame.Surface((2, 2), pygame.SRCALPHA)
            small.fill(color_tl_p, (0, 0, 1, 1))
            small.fill(color_tr_p, (1, 0, 1, 1))
            small.fill(color_bl, (0, 1, 1, 1))
            small.fill(color_br, (1, 1, 1, 1))
            grad = pygame.transform.smoothscale(small, (bs, tex_h)).convert_alpha()

            lit_tex = tex.copy()
            lit_tex.blit(grad, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            cache[key] = lit_tex
            if len(cache) > self.MAX_LIT_CACHE:
                cache.popitem(last=False)
        else:
            # ---- 完整高度方块（走缓存） ----
            # 7a. 获取/生成渐变纹理
            _q = lambda c: (c[0] >> 3, c[1] >> 3, c[2] >> 3)
            grad_key = (_q(color_tl), _q(color_tr), _q(color_bl), _q(color_br))
            grad_cache = self.gradient_cache
            if grad_key in grad_cache:
                grad = grad_cache[grad_key]
                grad_cache.move_to_end(grad_key)
            else:
                # 从 2×2 颜色角平滑放大到目标尺寸
                small = pygame.Surface((2, 2), pygame.SRCALPHA)
                small.fill(color_tl, (0, 0, 1, 1))
                small.fill(color_tr, (1, 0, 1, 1))
                small.fill(color_bl, (0, 1, 1, 1))
                small.fill(color_br, (1, 1, 1, 1))
                grad = pygame.transform.smoothscale(small, (bs, bs)).convert_alpha()
                grad_cache[grad_key] = grad
                if len(grad_cache) > self.MAX_GRADIENT_CACHE:
                    grad_cache.popitem(last=False)

            # 7b. 生成最终光照纹理（纹理 × 光照渐变）
            lit_tex = tex.copy()
            lit_tex.blit(grad, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            cache[key] = lit_tex
            if len(cache) > self.MAX_LIT_CACHE:
                cache.popitem(last=False)

        # ---- 8. 绘制到屏幕（非满高方块底部对齐） ----
        screen.blit(lit_tex, (sx, sy + bs - tex_h))

        # ---- 9. 调试文本 ----
        if debug:
            light_val = int(get_light(x, y) * 15)
            text = font.render(str(light_val), True, (255, 255, 255))
            text_rect = text.get_rect(center=(sx + bs // 2, sy + bs // 2))
            screen.blit(text, text_rect)
