import logging
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
        self.last_pressed_time = {}
        self.last_space_time = 0.0
        self.event_queue = []
        self.ing_mouse_lock = 0 # 鼠标锁，大于0时鼠标的操作不会影响游戏内动作（大于零时的数值即占用鼠标的GUI个数）
        # GUI 关闭时，物理上仍按住的键不能立即“穿透”回游戏。
        # 等所有键鼠释放后才恢复游戏输入，适用于聊天、背包等所有 GUI。
        self._wait_for_input_release = False
        self._pressed_keys: set[int] = set()
        self._pressed_mouse_buttons: set[int] = set()

    def acquire_game_input(self):
        """让 GUI 独占键鼠输入。"""
        self.ing_mouse_lock += 1
        self.client.hold_mouse_buttons = [False, False, False]

    def release_game_input(self):
        """释放一次 GUI 输入独占，并阻止仍按住的键泄漏到游戏。"""
        if self.ing_mouse_lock <= 0:
            self.ing_mouse_lock = 0
            return
        self.ing_mouse_lock -= 1
        if self.ing_mouse_lock == 0:
            self._wait_for_input_release = True
            self.client.hold_mouse_buttons = [False, False, False]

    def reset_game_input(self):
        """切换世界/界面时清空输入独占状态。"""
        self.ing_mouse_lock = 0
        self._wait_for_input_release = False
        self._pressed_keys.clear()
        self._pressed_mouse_buttons.clear()
        self.client.hold_mouse_buttons = [False, False, False]

    def gameplay_input_blocked(self) -> bool:
        """返回游戏动作当前是否必须忽略键鼠状态。"""
        if self.ing_mouse_lock > 0:
            return True
        if not self._wait_for_input_release:
            return False
        if self._pressed_keys or self._pressed_mouse_buttons:
            return True
        self._wait_for_input_release = False
        return False

    def _track_physical_input(self, events):
        """记录 GUI 消费前的原始按键状态，供释放门闩使用。"""
        for event in events:
            if event.type == pygame.KEYDOWN:
                self._pressed_keys.add(event.key)
            elif event.type == pygame.KEYUP:
                self._pressed_keys.discard(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._pressed_mouse_buttons.add(event.button)
            elif event.type == pygame.MOUSEBUTTONUP:
                self._pressed_mouse_buttons.discard(event.button)
            elif event.type == pygame.WINDOWFOCUSLOST:
                # 失焦后可能收不到对应 KEYUP；SDL 也会清空硬件状态。
                self._pressed_keys.clear()
                self._pressed_mouse_buttons.clear()

    def tick_ig(self):
        """执行一次游戏内逻辑更新"""
        if self.client.client_player is None:
            return
        try:
            self.handle_events()
            self.handle_key_pressed()
            self.sync_player_camera()
            self.client.client_player.move_update()
            self.client.client_player.game_mode.get_choosing_block()
            self.client.particle_manager.update()
            self.client.client_world.tick_fluid_sounds()
        except AttributeError:
            pass

    def client_tick(self):
        ...


    def handle_key_pressed(self):
        """处理键盘输入"""
        if self.gameplay_input_blocked():
            return
        keys = pygame.key.get_pressed()
        mouse_button = pygame.mouse.get_pressed()
        for key, action in self.client.hold_key_map.items():
            if type(key) == str: continue
            if keys[key]:
                action()
                self.last_pressed_time[key] = time.perf_counter()

        if self.client.fore_place_switch_mode == "hold":
            if keys[pygame.K_q]:
                self.client.client_player.fore_place = True
            else:
                self.client.client_player.fore_place = False

        if self.client.client_player is None:
            return

        if self.ing_mouse_lock == 0:
            player = self.client.client_player
            player.choosing_entity = self.client.render.get_hovered_entity()
            if mouse_button[0]:
                if player.choosing_entity is not None:
                    player.game_mode.left_click_on_entity(player.choosing_entity)
                    self.client.hold_mouse_buttons[0] = True
                    player.skeleton.trigger_swing()
                elif player.choosing_block is not None and (loc := player.choosing_block.location) is not None:
                    x = loc.x
                    y = loc.y
                    self.client.hold_key_map["mouse_left"](self.client.client_world.get_block(x, y, 0))
                    self.client.hold_mouse_buttons[0] = True
                    player.skeleton.trigger_swing()
            else:
                self.client.hold_mouse_buttons[0] = False
            if mouse_button[2]:
                if player.choosing_entity is not None:
                    player.game_mode.right_click_on_entity(player.choosing_entity)
                    self.client.hold_mouse_buttons[2] = True
                    player.skeleton.trigger_swing()
                elif player.choosing_block is not None and (loc := player.choosing_block.location) is not None:
                    x = loc.x
                    y = loc.y
                    self.client.hold_key_map["mouse_right"](self.client.client_world.get_block(x, y, 0))
                    self.client.hold_mouse_buttons[2] = True
                    player.skeleton.trigger_swing()
            else:
                self.client.hold_mouse_buttons[2] = False


    def sync_player_camera(self):
        """同步玩家位置到相机。
        trans_world_location 内置了方块网格的 -0.5/+0.5 偏移，
        这里反向补偿，并跟踪视觉模型中点（而非碰撞体中点）。"""
        player = self.client.client_player
        if player is None:
            return
        # 视觉模型中心 Y = 玩家脚底 + 视觉高度的一半
        visual_mid_y = player.y + player.skeleton.size * player.skeleton.AUTHORED_HEIGHT_BLOCKS / 2
        self.client.render.camera.move_to(
            player.x + player.width / 2 - 0.5,
            visual_mid_y + 0.5,
            1 / self.client.rate
        )

    def handle_events(self):
        # 先把自己队列里的副本取出来（避免在遍历时 render 又往里加）
        events = self.event_queue
        self.event_queue = []
        self._track_physical_input(events)

        for gui in self.client.render.drawing_GUIs[:]:
            gui.handle_events(events)  # GUI 处理事件, 被GUI处理的事件会从事件队列中删除

        # GUI 可能刚在本批事件中关闭。此时丢弃剩余游戏事件，并等当前
        # 物理按键全部释放，防止回车、Shift、Space 等穿透到游戏。
        if self.gameplay_input_blocked():
            return

        for event in events:
            if not self.client.in_game or self.client.client_player is None:
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.client.open_pause_menu()
                    continue
                if event.key == pygame.K_SPACE:
                    now = time.perf_counter()
                    last = self.last_pressed_time.get(pygame.K_SPACE, 0)
                    if now - last < 0.2 and self.client.client_player.flyable:
                        self.client.client_player.flying = not self.client.client_player.flying
                    self.last_pressed_time[pygame.K_SPACE] = now
                if event.key in self.client.key_map:
                    self.client.key_map[event.key]()
            if event.type == pygame.MOUSEWHEEL:
                self.client.client_player.game_mode.mouse_wheel(event.y)

    def start_game_loop(self):
        """启动游戏主循环"""
        next_time = time.perf_counter()

        while self.running:
            interval = 1.0 / self.client.rate

            if self.client.in_game:
                self.tick_ig()
            else:
                self.handle_events()
            self.client_tick()

            self.client.client_ticks += 1

            next_time += interval
            sleep_time = next_time - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        """停止游戏循环"""
        self.running = False


