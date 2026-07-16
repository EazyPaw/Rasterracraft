"""
聊天栏 GUI 组件

实现 Minecraft 风格的聊天消息显示和输入系统。
始终存在于 drawing_GUIs 列表中，优先级低于背包等浮层 GUI。
未激活时显示最近消息；激活时（按 T 或 / 键）显示输入栏、展开历史并支持滚轮滚动。
"""

import time

import pygame

from resources.client.GUI.gui import GUI
from resources.server.text import Text

MAX_INPUT_LENGTH = 128
MESSAGE_DISPLAY_WIDTH_RATIO = 0.55


class ChatGUI(GUI):
    """聊天覆盖层 GUI。

    始终在 drawing_GUIs 中。
    优先级 = 5（高于 HotBar(0)，低于 Backpack(10)）。

    Parameters
    ----------
    render : Render
        渲染器实例。
    """

    def __init__(self, render):
        super().__init__(render)
        self.priority = 5
        self.is_open = False
        self.input_text = ""
        self.cursor_pos = 0
        self.cursor_blink_timer = 0.0
        self.cursor_visible = True
        self._input_scroll = 0
        # 历史滚动
        self._scroll_offset = 0
        self._max_scroll = 0
        # 发送历史（↑↓ 快速补全）
        self.sent_history: list[str] = []
        self._history_index = -1
        self._saved_input = ""

        self.message_fade_time = 8.0   # 8 秒后完全消失
        self.message_opaque_time = 5.0  # 前 5 秒完全不透明

        self._text_input_started = False

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------

    def _layout(self):
        sw = self.render.SCREEN_WIDTH
        sh = self.render.SCREEN_HEIGHT
        return {
            'screen_w': sw,
            'screen_h': sh,
            'msg_area_w': int(sw * MESSAGE_DISPLAY_WIDTH_RATIO),
            'msg_font_size': max(14, int(sh * 0.025)),
            'input_font_size': max(16, int(sh * 0.028)),
            'input_bar_height': max(24, int(sh * 0.04)),
            'msg_x': 6,
            'hotbar_margin': int(sh * 0.06),
        }

    def _get_msg_bottom_y(self):
        """消息区域底部 Y 坐标。"""
        lay = self._layout()
        bar_h = lay['input_bar_height']
        return (
            lay['screen_h'] - bar_h - 10
            if self.is_open
            else lay['screen_h'] - lay['hotbar_margin']
        )

    # ------------------------------------------------------------------
    # 输入状态
    # ------------------------------------------------------------------

    def open_chat(self, prefix=""):
        self.is_open = True
        self.input_text = prefix
        self.cursor_pos = len(prefix)
        self._input_scroll = 0
        self._scroll_offset = 0
        self._history_index = -1
        self._saved_input = ""
        self.cursor_blink_timer = time.time()
        self.cursor_visible = True
        self.render.client.game_manager.ing_mouse_lock += 1
        # 启用按键重复：长按 Backspace/方向键等可持续响应
        pygame.key.set_repeat(400, 30)
        if not self._text_input_started:
            pygame.key.start_text_input()
            self._text_input_started = True

    def close_chat(self):
        self.is_open = False
        self.input_text = ""
        self.cursor_pos = 0
        self._input_scroll = 0
        self._scroll_offset = 0
        self.render.client.game_manager.ing_mouse_lock -= 1
        # 关闭按键重复，恢复正常游戏输入
        pygame.key.set_repeat(0, 0)
        if self._text_input_started:
            pygame.key.stop_text_input()
            self._text_input_started = False

    def send_message(self):
        text = self.input_text.strip()
        if not text:
            self.close_chat()
            return
        if len(text) > MAX_INPUT_LENGTH:
            text = text[:MAX_INPUT_LENGTH]
        # 存入发送历史（去重：与上一条相同时不重复添加）
        if not self.sent_history or self.sent_history[-1] != text:
            self.sent_history.append(text)
        # 限制历史数量
        if len(self.sent_history) > 50:
            self.sent_history = self.sent_history[-50:]
        self.render.client.sent_packet(
            {'__class__': 'ChatMessage', 'text': text}
        )
        self.close_chat()

    def _recalc_input_scroll(self, font):
        lay = self._layout()
        prompt = "> "
        max_visible_w = lay['screen_w'] - 16
        prompt_w = font.size(prompt)[0]
        cursor_px = prompt_w + font.size(self.input_text[:self.cursor_pos])[0]

        if cursor_px - self._input_scroll < prompt_w:
            self._input_scroll = cursor_px - prompt_w
        if cursor_px - self._input_scroll > max_visible_w - prompt_w:
            self._input_scroll = cursor_px - (max_visible_w - prompt_w)

        end_px = prompt_w + font.size(self.input_text)[0]
        if end_px - self._input_scroll < max_visible_w - 4:
            if self._input_scroll > 0 and end_px - self._input_scroll < max_visible_w - 40:
                self._input_scroll = max(0, end_px - (max_visible_w - 40))

        if self._input_scroll < 0:
            self._input_scroll = 0

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def handle_events(self, events):
        for event in events[:]:
            if event.type == pygame.MOUSEWHEEL:
                if self.is_open:
                    # 滚轮滚动聊天历史
                    self._scroll_offset += event.y  # event.y = +1 向上, -1 向下
                    if self._scroll_offset < 0:
                        self._scroll_offset = 0
                    if self._scroll_offset > self._max_scroll:
                        self._scroll_offset = self._max_scroll
                    events.remove(event)

            elif event.type == pygame.KEYDOWN:
                if not self.is_open:
                    if event.key in (pygame.K_t, pygame.K_SLASH, pygame.K_RETURN, pygame.K_KP_ENTER):
                        prefix = "/" if event.key == pygame.K_SLASH else ""
                        self.open_chat(prefix)
                        events.remove(event)
                else:
                    if event.key == pygame.K_ESCAPE:
                        self.close_chat()
                        events.remove(event)
                    elif event.key == pygame.K_UP:
                        # 历史补全：向上翻
                        if self.sent_history:
                            if self._history_index == -1:
                                self._saved_input = self.input_text
                                self._history_index = len(self.sent_history) - 1
                            elif self._history_index > 0:
                                self._history_index -= 1
                            self.input_text = self.sent_history[self._history_index]
                            self.cursor_pos = len(self.input_text)
                        events.remove(event)
                    elif event.key == pygame.K_DOWN:
                        # 历史补全：向下翻
                        if self._history_index != -1:
                            if self._history_index < len(self.sent_history) - 1:
                                self._history_index += 1
                                self.input_text = self.sent_history[self._history_index]
                            else:
                                self._history_index = -1
                                self.input_text = self._saved_input
                            self.cursor_pos = len(self.input_text)
                        events.remove(event)
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        self.send_message()
                        events.remove(event)
                    elif event.key == pygame.K_BACKSPACE:
                        if self.cursor_pos > 0:
                            self.input_text = (
                                self.input_text[:self.cursor_pos - 1] +
                                self.input_text[self.cursor_pos:]
                            )
                            self.cursor_pos -= 1
                        events.remove(event)
                    elif event.key == pygame.K_DELETE:
                        if self.cursor_pos < len(self.input_text):
                            self.input_text = (
                                self.input_text[:self.cursor_pos] +
                                self.input_text[self.cursor_pos + 1:]
                            )
                        events.remove(event)
                    elif event.key == pygame.K_LEFT:
                        if self.cursor_pos > 0:
                            self.cursor_pos -= 1
                        events.remove(event)
                    elif event.key == pygame.K_RIGHT:
                        if self.cursor_pos < len(self.input_text):
                            self.cursor_pos += 1
                        events.remove(event)
                    elif event.key == pygame.K_HOME:
                        self.cursor_pos = 0
                        events.remove(event)
                    elif event.key == pygame.K_END:
                        self.cursor_pos = len(self.input_text)
                        events.remove(event)
                    elif event.key == pygame.K_PAGEUP:
                        self._scroll_offset += 3
                        if self._scroll_offset > self._max_scroll:
                            self._scroll_offset = self._max_scroll
                        events.remove(event)
                    elif event.key == pygame.K_PAGEDOWN:
                        self._scroll_offset -= 3
                        if self._scroll_offset < 0:
                            self._scroll_offset = 0
                        events.remove(event)
                    elif event.key == pygame.K_a and (
                        pygame.key.get_mods() & pygame.KMOD_CTRL
                    ):
                        # Ctrl+A: 移动光标到开头
                        self.cursor_pos = 0
                        events.remove(event)
                    elif event.key == pygame.K_c and (
                        pygame.key.get_mods() & pygame.KMOD_CTRL
                    ):
                        # Ctrl+C: 复制全部输入文字到剪贴板
                        self._copy_to_clipboard()
                        events.remove(event)
                    elif event.key == pygame.K_v and (
                        pygame.key.get_mods() & pygame.KMOD_CTRL
                    ):
                        # Ctrl+V: 粘贴
                        self._paste_from_clipboard()
                        events.remove(event)
                    else:
                        events.remove(event)

            elif event.type == pygame.TEXTINPUT and self.is_open:
                remaining = MAX_INPUT_LENGTH - len(self.input_text)
                if remaining <= 0:
                    events.remove(event)
                    continue
                char = event.text[:remaining]
                self.input_text = (
                    self.input_text[:self.cursor_pos] +
                    char +
                    self.input_text[self.cursor_pos:]
                )
                self.cursor_pos += len(char)
                events.remove(event)

            elif event.type == pygame.TEXTEDITING and self.is_open:
                events.remove(event)

    @staticmethod
    def _get_clipboard_text() -> str | None:
        """从系统剪贴板获取文本，多级回退方案。"""
        # 方案 1: pygame.scrap（跨平台但需 SDL 初始化支持）
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            clip = pygame.scrap.get(pygame.SCRAP_TEXT)
            if clip:
                return clip.decode('utf-8')
        except Exception:
            pass

        # 方案 2: Windows 剪贴板 API（ctypes 直调 Win32）
        try:
            import ctypes
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if user32.OpenClipboard(0):
                if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                    h_mem = user32.GetClipboardData(CF_UNICODETEXT)
                    if h_mem:
                        p_str = kernel32.GlobalLock(h_mem)
                        if p_str:
                            text = ctypes.wstring_at(p_str)
                            kernel32.GlobalUnlock(h_mem)
                            user32.CloseClipboard()
                            return text
                user32.CloseClipboard()
        except Exception:
            pass

        # 方案 3: tkinter（最后手段，跨平台但会短暂创建窗口）
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            text = root.clipboard_get()
            root.destroy()
            return text
        except Exception:
            pass

        return None

    @staticmethod
    def _set_clipboard_text(text: str):
        """将文本写入系统剪贴板，多级回退方案。"""
        # 方案 1: pygame.scrap
        try:
            if not pygame.scrap.get_init():
                pygame.scrap.init()
            pygame.scrap.put(pygame.SCRAP_TEXT, text.encode('utf-8'))
            return
        except Exception:
            pass

        # 方案 2: Windows 剪贴板 API
        try:
            import ctypes
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            wide_text = text + '\x00'
            buf_size = len(wide_text) * 2
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, buf_size)
            if h_mem:
                p_str = kernel32.GlobalLock(h_mem)
                if p_str:
                    ctypes.cdll.msvcrt.wcscpy(ctypes.c_wchar_p(p_str), wide_text)
                    kernel32.GlobalUnlock(h_mem)
                if user32.OpenClipboard(0):
                    user32.EmptyClipboard()
                    user32.SetClipboardData(CF_UNICODETEXT, h_mem)
                    user32.CloseClipboard()
                    return
                kernel32.GlobalFree(h_mem)
        except Exception:
            pass

        # 方案 3: tkinter
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
        except Exception:
            pass

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """清理输入文本中的非法字符（null 字符、控制字符等）。

        pygame.font.render() 遇到 \\x00 会直接崩溃，
        剪贴板粘贴或 IME 输入可能带入此类字符，必须过滤。
        """
        # 保留可打印字符（0x20-0x7E）、常见多字节字符（中文等 >0x7F），
        # 去除 null（\\x00）和其他控制字符（0x01-0x1F，保留 \\n \\r \\t）
        return ''.join(
            ch for ch in text
            if ch == '\n' or ch == '\r' or ch == '\t' or ord(ch) >= 0x20
        )

    def _paste_from_clipboard(self):
        """将剪贴板文本粘贴到输入框中。"""
        clip = self._get_clipboard_text()
        if not clip:
            return
        # 去除换行和控制字符，仅保留单行纯文本
        pasted = self._sanitize_input(clip)
        pasted = pasted.replace('\r', '').replace('\n', '')
        remaining = MAX_INPUT_LENGTH - len(self.input_text)
        if remaining <= 0:
            return
        pasted = pasted[:remaining]
        self.input_text = (
            self.input_text[:self.cursor_pos] +
            pasted +
            self.input_text[self.cursor_pos:]
        )
        self.cursor_pos += len(pasted)

    def _copy_to_clipboard(self):
        """将当前输入文本复制到剪贴板。"""
        if self.input_text:
            self._set_clipboard_text(self.input_text)

    # ------------------------------------------------------------------
    # 渲染入口
    # ------------------------------------------------------------------

    def draw(self):
        self._draw_messages()
        if self.is_open:
            self._draw_input_bar()

    # ------------------------------------------------------------------
    # 消息渲染
    # ------------------------------------------------------------------

    def _wrap_text(self, text, font_size, max_width):
        font = self.render.get_font(font_size)
        if isinstance(text, Text):
            lines = []
            current_segments = []
            current_width = 0
            for segment in text.text:
                segment_color = segment.get('color')
                segment_bold = bool(segment.get('bold', False))
                segment_font = self.render.get_font(font_size, segment_bold)
                for ch in str(segment.get('text', '')):
                    char_width = segment_font.size(ch)[0]
                    if current_segments and current_width + char_width > max_width:
                        lines.append(Text(current_segments))
                        current_segments = []
                        current_width = 0
                    if (
                        current_segments
                        and current_segments[-1]['color'] == segment_color
                        and current_segments[-1]['bold'] == segment_bold
                    ):
                        current_segments[-1]['text'] += ch
                    else:
                        current_segments.append({
                            'text': ch,
                            'color': segment_color,
                            'bold': segment_bold,
                        })
                    current_width += char_width
            if current_segments:
                lines.append(Text(current_segments))
            return lines

        lines = []
        current_line = ""
        for ch in text:
            test_line = current_line + ch
            if font.size(test_line)[0] > max_width and current_line:
                lines.append(current_line)
                current_line = ch
            else:
                current_line = test_line
        if current_line:
            lines.append(current_line)
        return lines

    def _render_row(self, text, x, y, color, alpha, font_size):
        """渲染单行（带阴影）。"""
        font = self.render.get_font(font_size)
        shadow_off = max(1, font.get_height() // 12)

        if alpha < 255:
            if isinstance(text, Text):
                segments = text.text
            else:
                segments = ({'text': text, 'color': color, 'bold': False},)
            cursor_x = x
            for segment in segments:
                segment_color = segment.get('color', color)
                if hasattr(segment_color, 'value'):
                    segment_color = segment_color.value
                segment_color = tuple(segment_color)
                segment_font = self.render.get_font(
                    font_size, bool(segment.get('bold', False))
                )
                segment_text = str(segment.get('text', ''))
                shadow_col = tuple(max(0, int(c * 0.25)) for c in segment_color)
                shadow_surface = segment_font.render(segment_text, True, shadow_col)
                shadow_surface.set_alpha(alpha)
                self.render.blit(
                    shadow_surface, (cursor_x + shadow_off, y + shadow_off)
                )
                text_surface = segment_font.render(segment_text, True, segment_color)
                text_surface.set_alpha(alpha)
                self.render.blit(text_surface, (cursor_x, y))
                cursor_x += text_surface.get_width()
        else:
            self.render.render_text(text, (x, y), color, font_size, shadow=True)

    def _draw_messages(self):
        """渲染消息历史。

        聊天关闭时：显示最近消息（更多在上，更新在下）。
        聊天打开时：显示更多消息并支持滚轮滚动，消息从上往下排列。
        """
        now = time.time()
        messages = self.render.client.chat_messages
        if not messages:
            return

        lay = self._layout()
        font = self.render.get_font(lay['msg_font_size'])
        line_h = lay['msg_font_size'] + 4
        max_msg_w = lay['msg_area_w']
        text_max_w = max_msg_w - 10

        # ---- 阶段 1: 构建所有可见行（从旧到新） ----
        all_rows = []
        for msg in messages:
            age = now - msg['time']
            if self.is_open:
                # 聊天打开时：显示全部历史消息，不透明
                alpha = 255
            else:
                # 聊天关闭时：仅显示未超时的消息，应用渐隐
                if age > self.message_fade_time:
                    continue
                if age < self.message_opaque_time:
                    alpha = 255
                else:
                    fade = (age - self.message_opaque_time) / (
                        self.message_fade_time - self.message_opaque_time
                    )
                    alpha = int(255 * (1.0 - fade))
                    if alpha <= 0:
                        continue
            color = msg.get('color', (255, 255, 255))
            wrapped = self._wrap_text(msg['text'], lay['msg_font_size'], text_max_w)
            for line in wrapped:
                all_rows.append((line, color, alpha))

        if not all_rows:
            return

        # ---- 阶段 2: 确定可见行数并计算滚动 ----
        bottom_y = self._get_msg_bottom_y()
        if self.is_open:
            # 聊天打开时：最多显示到屏幕一半高度，超出则滚轮翻阅
            max_chat_h = lay['screen_h'] // 2
            max_visible = max(1, max_chat_h // line_h)
        else:
            max_visible = 12  # 未激活时固定 12 行

        total_rows = len(all_rows)
        self._max_scroll = max(0, total_rows - max_visible)
        # 将 scroll_offset 钳制在有效范围内
        if self._scroll_offset > self._max_scroll:
            self._scroll_offset = self._max_scroll
        if self._scroll_offset < 0:
            self._scroll_offset = 0

        # 默认显示最新的消息（scroll=0 显示底部），scroll 正值向上翻
        start_idx = total_rows - max_visible - self._scroll_offset
        if start_idx < 0:
            start_idx = 0
        # 确保不会取太少：至少显示 max_visible 条（如果可用）
        visible_rows = all_rows[start_idx:start_idx + max_visible]

        # ---- 阶段 3: 从下往上绘制（最新在最下方） ----
        x = lay['msg_x']
        for i in range(len(visible_rows)):
            row_idx_from_bottom = len(visible_rows) - 1 - i
            draw_y = bottom_y - (row_idx_from_bottom + 1) * line_h

            line, color, alpha = visible_rows[i]
            # 统一宽度背景
            bg_rect = pygame.Rect(x - 2, draw_y, max_msg_w + 4, line_h)
            bg_surf = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
            bg_surf.fill((0, 0, 0, int(alpha * 0.45)))
            self.render.blit(bg_surf, (bg_rect.x, bg_rect.y))
            self._render_row(
                line, x + 2, draw_y + 2, color, alpha, lay['msg_font_size']
            )

    # ------------------------------------------------------------------
    # 输入栏
    # ------------------------------------------------------------------

    def _draw_input_bar(self):
        lay = self._layout()
        bar_h = lay['input_bar_height']
        y = lay['screen_h'] - bar_h - 10
        sw = lay['screen_w']

        bg = pygame.Surface((sw, bar_h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 180))
        self.render.blit(bg, (0, y))

        font = self.render.get_font(lay['input_font_size'])
        prompt = "" # 可自定义输入前文字
        # 渲染前清理非法字符（null 等会导致 font.render 崩溃）
        display_text = self._sanitize_input(self.input_text)

        self._recalc_input_scroll(font)

        now = time.time()
        if now - self.cursor_blink_timer >= 0.53:
            self.cursor_blink_timer = now
            self.cursor_visible = not self.cursor_visible

        text_surf = font.render(display_text, True, (255, 255, 255))
        max_visible_w = sw - 8
        if text_surf.get_width() > max_visible_w:
            clip_rect = pygame.Rect(self._input_scroll, 0, max_visible_w, text_surf.get_height())
            if clip_rect.right > text_surf.get_width():
                clip_rect.right = text_surf.get_width()
            try:
                clipped = text_surf.subsurface(clip_rect)
            except ValueError:
                clipped = text_surf
            self.render.blit(clipped, (4, y + (bar_h - text_surf.get_height()) // 2))
        else:
            self.render.blit(text_surf, (4, y + (bar_h - text_surf.get_height()) // 2))

        if self.cursor_visible:
            prompt_w = font.size(prompt)[0]
            cursor_x = (
                4 + prompt_w
                + font.size(self.input_text[:self.cursor_pos])[0]
                - self._input_scroll
            )
            if 0 <= cursor_x <= max_visible_w - 2:
                cursor_rect = pygame.Rect(cursor_x, y + 5, 2, lay['input_font_size'])
                pygame.draw.rect(self.render.screen, (255, 255, 255), cursor_rect)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def on_open(self):
        pass

    def on_close(self):
        if self.is_open:
            self.close_chat()
