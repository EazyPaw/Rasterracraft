# Commented and arranged by ChatGPT
import logging
import threading

import pygame
import json
import random
import os
import numpy as np
from collections import OrderedDict

from pygame import Surface

from src.server.location import Location
from src.server.biome import get_biome_by_id
from src.server.utils import client_method


BUILTIN_SOUND_FALLBACKS = {
    "item.hoe.till": {
        "category": "block",
        "sounds": [
            {"name": f"dig/gravel{index}", "volume": 0.8} for index in range(1, 5)
        ],
    },
}

DEFAULT_SOUND_CHANNELS = 32
SOUND_CATEGORY_PRIORITIES = {
    "ambient": 0,
    "weather": 0,
    "block": 1,
    "neutral": 1,
    "hostile": 2,
    "player": 2,
    "master": 2,
}


class ResourcesManager:
    def __init__(self, client):
        self.client = client
        self.textures = {}
        self.sounds = {}  # 存储解析后的音效信息
        self.sound_objects = {}  # 缓存已加载的 pygame.mixer.Sound 对象
        self._audio_lock = threading.RLock()
        self._active_sound_channels = {}
        self._sound_sequence = 0
        self._ensure_sound_channels()
        self.stained_cache: OrderedDict[tuple, pygame.Surface] = OrderedDict()
        self.MAX_STAINED_CACHE = 512  # 染色缓存上限
        self._lang_map = {}
        self._fallback_lang_map = {}
        self.load_lang("en_US", target=self._fallback_lang_map)
        self.load_lang(self.client.language)

        missing_surface = pygame.Surface((16, 16), pygame.SRCALPHA)
        missing_surface.fill((0, 0, 0, 255))
        for x in range(8, 16):
            for y in range(0, 8):
                missing_surface.set_at((x, y), (128, 0, 128, 255))
        for x in range(0, 8):
            for y in range(8, 16):
                missing_surface.set_at((x, y), (128, 0, 128, 255))
        self.missing_texture = missing_surface.convert()

    def load_lang(self, lang: str, *, target: dict | None = None):
        if target is None:
            target = self._lang_map
        lang_path = f"assets/minecraft/lang/{lang}.lang"
        try:
            with open(lang_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        target[key] = value
                    except Exception as e:
                        logging.error(
                            f"Failed to load language '{lang}': {e} at line: {line}"
                        )
        except FileNotFoundError:
            logging.warning(f"Language file not found: '{lang_path}'")

    def get_translation_key(self, key: str, *args):
        if key in self._lang_map:
            text = self._lang_map[key]
        elif key in self._fallback_lang_map:
            text = self._fallback_lang_map[key]
        else:
            logging.warning(f"Invalid language key: '{key}'")
            text = key
        if args:
            try:
                text = self._format_translation(text, args)
            except (TypeError, ValueError):
                logging.warning(f"Failed to format language key: '{key}'")
        return text

    @staticmethod
    def _format_translation(text: str, args: tuple) -> str:
        result = []
        next_arg = 0
        i = 0
        while i < len(text):
            if text[i] != "%" or i == len(text) - 1:
                result.append(text[i])
                i += 1
                continue

            if text[i + 1] == "%":
                result.append("%")
                i += 2
                continue

            j = i + 1
            explicit_arg = None
            digit_start = j
            while j < len(text) and text[j].isdigit():
                j += 1

            if j > digit_start and j < len(text) and text[j] == "$":
                explicit_arg = int(text[digit_start:j]) - 1
                j += 1
            elif j > digit_start:
                j = i + 1

            if j >= len(text):
                result.append(text[i:])
                break

            spec = text[j]
            if spec not in "sdfi":
                result.append(text[i : j + 1])
                i = j + 1
                continue

            if explicit_arg is None:
                arg_index = next_arg
                next_arg += 1
            else:
                arg_index = explicit_arg

            if arg_index < 0 or arg_index >= len(args):
                raise ValueError("not enough arguments for translation format")

            value = args[arg_index]
            if spec in "di":
                value = int(value)
            elif spec == "f":
                value = float(value)
            result.append(str(value))
            i = j + 1

        return "".join(result)

    def get_texture_img(self, key: str, cft=False, gta=False, flip=False) -> Surface:
        """
        获取指定纹理的 Surface 对象。自带缓存，可直接调用
        :param flip: 是否镜像翻转贴图
        :param cft: 是否切除材质中完全透明的多余边缘
        :param key: 纹理的键，格式为 "类别.子路径.文件名"
                   例如："blocks.stone" -> assets/minecraft/textures/blocks/stone.png
                        "gui.sprites.hud.hotbar" -> assets/minecraft/textures/gui/sprites/hud/hotbar.png
        :param gta: 是否将灰度图转化为alpha图像
        :return: Surface 对象，如果没有找到则返回缺失纹理
        此方法本身带有缓存优化。
        """
        # 检查缓存
        ckey = (key, cft, gta, flip)
        if ckey in self.textures:
            r = self.textures[ckey]
            if isinstance(r, pygame.Surface):
                return self.textures[ckey]
            if isinstance(r, dict):
                n = self._get_animation_frame_index(r)
                return self.textures[ckey]["textures"][n]

        # 解析路径
        parts = key.split(".")
        if len(parts) < 2:
            logging.warning(f"Invalid texture key format: '{key}'")
            return self.missing_texture

        # 第一个部分是类别（blocks, gui, items等）
        category = parts[0]
        # 剩余部分组成文件路径
        file_path = "/".join(parts[1:])

        # 构建完整路径：assets/minecraft/textures/{category}/{subpath}.png
        full_path = f"assets/minecraft/textures/{category}/{file_path}.png"
        meta_path = f"assets/minecraft/textures/{category}/{file_path}.png.mcmeta"

        try:
            if not os.path.exists(full_path):
                logging.warning(f"Texture file not found: '{full_path}'")
                self.textures[ckey] = self.missing_texture
                return self.missing_texture
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta: dict = json.load(f)
            else:
                meta = {}

            texture = pygame.image.load(full_path).convert_alpha()

            # 部分带有动画的方块
            if "animation" in meta:
                animation = meta["animation"]
                frame_time = animation.get("frametime", animation.get("frame_time", 1))
                width = texture.get_size()[0]
                height = texture.get_size()[1]
                if height % width != 0:
                    logging.warning(
                        f"Texture height is not a multiple of width: {width}"
                    )
                    self.textures[ckey] = self.missing_texture
                    return self.missing_texture
                strips = self.split_horizontal_strips(texture)
                frame_indices = self._parse_animation_frames(animation, len(strips))
                self.textures[ckey] = {
                    "textures": strips,
                    "frame_time": max(1, int(frame_time)),
                    "frame_indices": frame_indices,
                }
                # 首次加载也计算当前帧（与缓存命中分支逻辑一致）
                n = self._get_animation_frame_index(self.textures[ckey])
                return strips[n]

            # 如果需要切除完全透明的边缘
            if cft:
                texture = self._crop_transparent_edges(texture)

            if gta:
                texture = self.grayscale_to_alpha(texture)

            if flip:
                texture = pygame.transform.flip(texture, True, False)

            self.textures[ckey] = texture
            return texture

        except (pygame.error, IOError) as e:
            logging.warning(f"Failed to load texture '{key}' from '{full_path}': {e}")
            self.textures[ckey] = self.missing_texture
            return self.missing_texture

    def get_texture_animation_key(self, key: str, cft=False, gta=False, flip=False):
        self.get_texture_img(key, cft=cft, gta=gta, flip=flip)
        cache_key = (key, cft, gta, flip)
        texture = self.textures.get(cache_key)
        if not isinstance(texture, dict):
            return None
        return cache_key, self._get_animation_frame_index(texture)

    def is_texture_animated(self, key: str, cft=False, gta=False, flip=False) -> bool:
        self.get_texture_img(key, cft=cft, gta=gta, flip=flip)
        return isinstance(self.textures.get((key, cft, gta, flip)), dict)

    def _get_animation_frame_index(self, animation_data: dict) -> int:
        frame_indices = animation_data.get("frame_indices")
        if not frame_indices:
            frame_indices = list(range(len(animation_data["textures"])))
        frame_time = max(1, int(animation_data.get("frame_time", 1)))
        timeline_index = int(self.client.client_ticks / frame_time) % len(frame_indices)
        frame_index = int(frame_indices[timeline_index])
        return max(0, min(frame_index, len(animation_data["textures"]) - 1))

    @staticmethod
    def _parse_animation_frames(animation: dict, frame_count: int) -> list[int]:
        frames = animation.get("frames")
        if not frames:
            return list(range(frame_count))

        result: list[int] = []
        for frame in frames:
            if isinstance(frame, int):
                index = frame
            elif isinstance(frame, dict):
                index = int(frame.get("index", 0))
            else:
                continue
            if 0 <= index < frame_count:
                result.append(index)
        return result or list(range(frame_count))

    @staticmethod
    def _crop_transparent_edges(surface):
        """
        切除 Surface 四个方向（上、下、左、右）完全透明的边缘行/列。
        遍历方向：先从上往下切除全透明行，再从下往上，然后从左往右切除全透明列，最后从右往左。
        :param surface: 带 alpha 通道的 pygame.Surface
        :return: 裁剪后的新 Surface
        """
        width, height = surface.get_size()

        # 辅助函数：检查某一行是否所有像素完全透明
        def is_row_fully_transparent(y):
            for x in range(width):
                if surface.get_at((x, y)).a != 0:
                    return False
            return True

        # 辅助函数：检查某一列是否所有像素完全透明
        def is_col_fully_transparent(x):
            for y in range(height):
                if surface.get_at((x, y)).a != 0:
                    return False
            return True

        # 上边缘：从上向下寻找第一个非全透明行
        top = 0
        while top < height and is_row_fully_transparent(top):
            top += 1

        # 下边缘：从下向上寻找第一个非全透明行
        bottom = height - 1
        while bottom >= top and is_row_fully_transparent(bottom):
            bottom -= 1

        # 左边缘：从左向右寻找第一个非全透明列
        left = 0
        while left < width and is_col_fully_transparent(left):
            left += 1

        # 右边缘：从右向左寻找第一个非全透明列
        right = width - 1
        while right >= left and is_col_fully_transparent(right):
            right -= 1

        # 如果所有像素都透明（极端情况），返回 1x1 透明表面，防止 subsurface 出错
        if top > bottom or left > right:
            return pygame.Surface((1, 1), pygame.SRCALPHA)

        # 裁剪有效区域
        crop_width = right - left + 1
        crop_height = bottom - top + 1
        cropped = surface.subsurface((left, top, crop_width, crop_height))
        # subsurface 与原表面共享数据，为避免意外修改，可返回副本
        return cropped.copy()

    @staticmethod
    def stain_grayscale(grayscale_surface: pygame.Surface, color) -> pygame.Surface:
        """
        给灰度图染色，保留透明度和明暗变化。
        使用向量化逻辑，性能更优。
        :param grayscale_surface: 灰度 Surface（带 Alpha 通道）
        :param color: 目标颜色，可以是十六进制字符串（例如 "#91bd59"）或 RGB 元组 (R, G, B)
        :return: 染色后的 Surface
        """
        # 1. 解析目标颜色为 (R, G, B) 整数元组
        if isinstance(color, str):
            hex_color = color.lstrip("#")
            if len(hex_color) != 6:
                raise ValueError("十六进制颜色格式错误，需要 6 位，如 '#91bd59'")
            r, g, b = (
                int(hex_color[0:2], 16),
                int(hex_color[2:4], 16),
                int(hex_color[4:6], 16),
            )
        elif isinstance(color, (tuple, list)) and len(color) == 3:
            r, g, b = color
        else:
            raise ValueError("color 必须为 '#RRGGBB' 字符串或 (R, G, B) 元组")
        target_color = np.array([r, g, b], dtype=np.uint8)

        # 2. 获取灰度图的宽度与高度
        w, h = grayscale_surface.get_size()

        # 3. 从 Surface 中提取 RGB 与 Alpha 数据
        #    array3d 返回形状 (width, height, 3)，通道顺序为 RGB
        rgb_array = pygame.surfarray.array3d(grayscale_surface)
        alpha = pygame.surfarray.array_alpha(grayscale_surface)

        # 4. 提取灰度值（灰度图中 R=G=B，直接使用红色通道即可）
        gray = rgb_array[:, :, 0]

        # 5. 向量化染色：new_channel = gray * target_channel / 255
        #    使用 uint16 防止乘法溢出，结果转回 uint8
        gray_expanded = gray[:, :, np.newaxis].astype(np.uint16)  # (w, h, 1)
        target_color_expanded = target_color.astype(np.uint16)  # (3,)
        colored = (gray_expanded * target_color_expanded // 255).astype(
            np.uint8
        )  # (w, h, 3)

        # 6. 合并 RGB 与 Alpha 通道为 (w, h, 4) 数组
        rgba = np.dstack((colored, alpha))

        # 7. 修正旋转问题：交换轴使形状变为 (h, w, 4)，然后创建 Surface
        rgba_swapped = np.swapaxes(rgba, 0, 1)
        result = pygame.image.frombytes(rgba_swapped.tobytes(), (w, h), "RGBA")
        return result

    @staticmethod
    def biome_stain(
        grayscale_surface: pygame.Surface, location: Location, mode="grass"
    ) -> pygame.Surface:
        """
        生成该方块所在群系的染色后贴图
        :param grayscale_surface: 原灰度图
        :param location: 方块位置
        :param mode: 染色模式，”grass“为草，”foliage“为树叶
        :return: 返回染色后 Surface
        """
        x = location.x
        y = location.y
        biome = get_biome_by_id(location.world.get_biome(x, y))
        if mode == "grass":
            r = ResourcesManager.stain_grayscale(grayscale_surface, biome.grass_color)
        elif mode == "foliage":
            r = ResourcesManager.stain_grayscale(grayscale_surface, biome.foliage_color)
        else:
            r = grayscale_surface.copy()
        return r

    def load_sounds_json(self, json_path: str = "assets/minecraft/sounds.json"):
        """
        加载 sounds.json 并解析到 self.sounds 中。
        """
        data = {}
        if not os.path.exists(json_path):
            print(f"Warning: sounds.json not found at {json_path}")
        else:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

        for sound_id, info in BUILTIN_SOUND_FALLBACKS.items():
            data.setdefault(sound_id, info)

        for sound_id, info in data.items():
            self.sounds[sound_id] = {
                "category": info.get("category", "master"),
                "sounds": info.get("sounds", []),
            }

    def _ensure_sound_channels(self, required_channel: int | None = None) -> int:
        """保证混音器拥有足够的音效频道，并返回当前频道数。"""
        if pygame.mixer.get_init() is None:
            return 0

        minimum = DEFAULT_SOUND_CHANNELS
        if required_channel is not None:
            minimum = max(minimum, required_channel + 1)
        channel_count = pygame.mixer.get_num_channels()
        if channel_count < minimum:
            pygame.mixer.set_num_channels(minimum)
            channel_count = minimum
        return channel_count

    def _acquire_sound_channel(
        self,
        *,
        audibility: float,
        priority: int,
        channel_id: int | None,
    ):
        """分配频道；满载时仅抢占优先级更低或更安静的旧音效。"""
        channel_count = self._ensure_sound_channels(channel_id)
        if channel_count <= 0:
            return None, None

        if channel_id is not None:
            return pygame.mixer.Channel(channel_id), channel_id

        busy_channels = []
        for current_id in range(channel_count):
            channel = pygame.mixer.Channel(current_id)
            if not channel.get_busy():
                self._active_sound_channels.pop(current_id, None)
                return channel, current_id
            busy_channels.append((current_id, channel))

        # 未通过资源管理器启动的频道不参与抢占，以免切断未知的持续音频。
        candidates = [
            (
                metadata["priority"],
                metadata["audibility"],
                metadata["sequence"],
                current_id,
                channel,
            )
            for current_id, channel in busy_channels
            if (metadata := self._active_sound_channels.get(current_id)) is not None
        ]
        if not candidates:
            return None, None

        candidate_priority, candidate_audibility, _, selected_id, selected = min(
            candidates
        )
        if (priority, audibility) < (candidate_priority, candidate_audibility):
            return None, None
        return selected, selected_id

    def play_sound(
        self,
        sound_id: str,
        volume: float = 1.0,
        stereo_balance: tuple = None,
        loops: int = 0,
        fade_ms: int = 0,
        channel_id: int | None = None,
        priority: int | None = None,
    ):
        """
        播放音效。
        :param sound_id: 音效 ID（对应 sounds.json 中的键）
        :param volume: 单通道音量（当 stereo_balance 为 None 时使用）
        :param stereo_balance: 可选的 (left, right) 音量元组，用于立体声定位。
        :param loops: 额外循环次数；-1 表示持续循环。
        :param fade_ms: 淡入时长（毫秒）。
        :param channel_id: 可选的固定混音通道，适合持续环境音。
        :param priority: 可选的抢占优先级；数值越大越不容易被覆盖。
        :return: 非流式音效的 pygame Channel，无法播放时返回 None。
        """
        if sound_id not in self.sounds:
            print(f"Sound ID '{sound_id}' not found in loaded sounds.json")
            return None

        sound_data = self.sounds[sound_id]
        sound_list = sound_data["sounds"]
        if not sound_list:
            print(f"No sound files defined for ID '{sound_id}'")
            return None

        # 随机选择一个条目
        chosen = random.choice(sound_list)

        # 解析路径和属性
        if isinstance(chosen, str):
            sound_path = chosen
            stream = False
            base_volume = volume
        elif isinstance(chosen, dict):
            sound_path = chosen.get("name")
            if not sound_path:
                print(f"Invalid sound entry for ID '{sound_id}': missing 'name'")
                return
            stream = chosen.get("stream", False)
            base_volume = float(chosen.get("volume", 1.0)) * volume
        else:
            print(f"Invalid sound entry type for ID '{sound_id}'")
            return

        full_path = f"assets/minecraft/sounds/{sound_path}.ogg"

        if not os.path.exists(full_path):
            print(f"Sound file not found: {full_path}")
            return

        try:
            if stream:
                # 流式播放（背景音乐）不支持立体声控制，使用基础音量
                pygame.mixer.music.load(full_path)
                pygame.mixer.music.set_volume(max(0.0, min(1.0, base_volume)))
                pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)
                return None
            else:
                with self._audio_lock:
                    # 先取得频道并设置音量，再开始播放，避免短音效以满音量起音。
                    if full_path not in self.sound_objects:
                        self.sound_objects[full_path] = pygame.mixer.Sound(full_path)
                    sound_obj = self.sound_objects[full_path]

                    if stereo_balance is None:
                        left = right = max(0.0, min(1.0, base_volume))
                    else:
                        left, right = stereo_balance
                        left = max(0.0, min(1.0, float(left) * base_volume))
                        right = max(0.0, min(1.0, float(right) * base_volume))

                    effective_priority = (
                        int(priority)
                        if priority is not None
                        else SOUND_CATEGORY_PRIORITIES.get(
                            sound_data.get("category", "master"), 1
                        )
                    )
                    audibility = max(left, right)
                    channel, selected_id = self._acquire_sound_channel(
                        audibility=audibility,
                        priority=effective_priority,
                        channel_id=channel_id,
                    )
                    if channel is None:
                        return None

                    channel.set_volume(left, right)
                    channel.play(sound_obj, loops=loops, fade_ms=fade_ms)
                    self._sound_sequence += 1
                    self._active_sound_channels[selected_id] = {
                        "priority": effective_priority,
                        "audibility": audibility,
                        "sequence": self._sound_sequence,
                    }
                    return channel
        except pygame.error as e:
            print(f"Error playing sound '{full_path}': {e}")
        return None

    @staticmethod
    def split_horizontal_strips(surface):
        """
        将 Surface 沿高度方向切割为多个等高的水平条带
        """
        width = surface.get_width()
        height = surface.get_height()
        num_parts = height // width
        part_height = height // num_parts

        strips = []
        for i in range(num_parts):
            # 截取区域: (x, y, width, height)
            rect = (0, i * part_height, width, part_height)
            strips.append(surface.subsurface(rect))

        return strips

    @staticmethod
    def has_transparent_pixels(surface: pygame.Surface) -> bool:
        """检查表面是否存在透明或半透明像素。

        仅检测逐像素 alpha，不考虑颜色键透明；未启用 SRCALPHA 的表面直接
        视为不透明。

        :param surface: 待检查的 Pygame 表面。
        :return: 存在 alpha 小于 255 的像素时返回 True。
        :rtype: bool
        """
        # 快速判断：如果没有 per-pixel alpha 支持，则所有像素均为不透明
        if not (surface.get_flags() & pygame.SRCALPHA):
            return False

        # 获取 alpha 通道视图（表面会被锁定，函数返回后自动解锁）
        alpha_arr = pygame.surfarray.pixels_alpha(surface)
        # 检查是否有任何 alpha 值小于 255
        result = np.any(alpha_arr < 255)
        # 释放数组引用以解锁表面（可选）
        del alpha_arr
        return result

    @staticmethod
    def grayscale_to_alpha(surface):
        """
                将带 alpha 的灰度 Surface 转换为纯黑半透明遮罩：
                - RGB 全部设为 0（纯黑）
                - Alpha 由灰度值决定：黑色(0) → 255 不透明，白色(255) → 0 完全透明
                - 原有的 alpha 通道被忽略，完全由灰度重新计算

        :param surface: 输入的 Surface，应为灰度图（R=G=B），且最好已有 alpha 通道。
        :type surface: pygame.Surface

        :return: 新的纯黑半透明 Surface。
        :rtype: pygame.Surface

        """
        # 确保 Surface 有 alpha 通道（若无则添加）
        if surface.get_alpha() is None:
            surface = surface.convert_alpha()

        # 复制一份，避免影响原始图像
        result = surface.copy()

        w, h = result.get_size()
        pixels = pygame.PixelArray(result)  # 锁定像素

        for x in range(w):
            for y in range(h):
                color = pixels[x, y]
                # 提取红色通道（灰度图 R=G=B）
                gray = (color >> 16) & 0xFF
                # 计算新 alpha：灰色越亮，alpha 越小（越透明）
                new_alpha = 255 - gray
                # 设置 RGB 为 0，并应用新 alpha
                pixels[x, y] = (0, 0, 0, new_alpha)

        del pixels  # 解锁
        return result


@client_method
def transkey(key: str, *args, client=None):
    return client.resources_manager.get_translation_key(key, *args)
