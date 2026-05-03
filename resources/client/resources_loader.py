import pygame
import miniaudio
import json
import random
import os

class ResourcesManager:
    def __init__(self):
        self.textures = {}
        self.sounds = {}          # 存储解析后的音效信息
        self.sound_objects = {}   # 缓存已加载的 pygame.mixer.Sound 对象

    def get_texture_img(self, key: str):
        if key in self.textures:
            return self.textures[key]
        path = key.split('.')
        if path[0] == 'blocks':
            texture = pygame.image.load(f'assets/minecraft/textures/blocks/{path[1]}.png').convert_alpha()
            self.textures[key] = texture
            return texture
        elif path[0] == 'sounds':
            # 注意：此分支已不再用于声音加载，声音统一由 load_sounds_json 和 play_sound 处理
            pass
        return None

    def load_sounds_json(self, json_path: str = 'assets/minecraft/sounds.json'):
        """
        加载 sounds.json 并解析到 self.sounds 中。
        """
        if not os.path.exists(json_path):
            print(f"Warning: sounds.json not found at {json_path}")
            return

        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for sound_id, info in data.items():
            self.sounds[sound_id] = {
                'category': info.get('category', 'master'),
                'sounds': info.get('sounds', [])
            }

    def play_sound(self, sound_id: str, volume: float = 1.0, stereo_balance: tuple = None):
        """
        播放音效。
        :param sound_id: 音效 ID（对应 sounds.json 中的键）
        :param volume: 单通道音量（当 stereo_balance 为 None 时使用）
        :param stereo_balance: 可选的 (left, right) 音量元组，用于立体声定位。
        """
        if sound_id not in self.sounds:
            print(f"Sound ID '{sound_id}' not found in loaded sounds.json")
            return

        sound_data = self.sounds[sound_id]
        sound_list = sound_data['sounds']
        if not sound_list:
            print(f"No sound files defined for ID '{sound_id}'")
            return

        # 随机选择一个条目
        chosen = random.choice(sound_list)

        # 解析路径和属性
        if isinstance(chosen, str):
            sound_path = chosen
            stream = False
            base_volume = volume
        elif isinstance(chosen, dict):
            sound_path = chosen.get('name')
            if not sound_path:
                print(f"Invalid sound entry for ID '{sound_id}': missing 'name'")
                return
            stream = chosen.get('stream', False)
            base_volume = chosen.get('volume', volume)
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
                pygame.mixer.music.set_volume(base_volume)
                pygame.mixer.music.play()
            else:
                # 非流式音效
                if full_path not in self.sound_objects:
                    self.sound_objects[full_path] = pygame.mixer.Sound(full_path)
                sound_obj = self.sound_objects[full_path]

                if stereo_balance is not None:
                    left, right = stereo_balance
                    # 播放并获取 Channel，直接设置左右音量
                    channel = sound_obj.play()
                    if channel:
                        channel.set_volume(left, right)
                else:
                    sound_obj.set_volume(base_volume)
                    sound_obj.play()
        except pygame.error as e:
            print(f"Error playing sound '{full_path}': {e}")