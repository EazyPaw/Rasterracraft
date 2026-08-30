# Commented and arranged by ChatGPT
import time
from enum import Enum


class CameraMode(str, Enum):
    """玩家跟随镜头的工作模式。"""

    CENTERED = "centered"
    MOUSE_LEAD = "mouse_lead"


class Camera:
    def __init__(self, mode: CameraMode | str = CameraMode.MOUSE_LEAD):
        self.x = 0
        self.y = 0
        self.mode = CameraMode(mode)
        self.mouse_lead_strength = 0.05
        # 单独保存引导量，供屏幕固定绘制的主玩家使用。
        self.lead_x = 0.0
        self.lead_y = 0.0
        self._target_lead_x = 0.0
        self._target_lead_y = 0.0
        self._start_lead_x = 0.0
        self._start_lead_y = 0.0
        self._target_x = None
        self._target_y = None
        self._start_x = None
        self._start_y = None
        self._start_time = None
        self._duration = 0.05  # 50ms

    def set_mode(self, mode: CameraMode | str) -> None:
        """切换镜头模式。

        可传入 ``CameraMode.MOUSE_LEAD`` / ``CameraMode.CENTERED``，
        也可直接传入对应字符串 ``"mouse_lead"`` / ``"centered"``。
        """
        self.mode = CameraMode(mode)

    def toggle_mode(self) -> CameraMode:
        """在居中和鼠标引导模式间切换，并返回新模式。"""
        if self.mode is CameraMode.CENTERED:
            self.mode = CameraMode.MOUSE_LEAD
        else:
            self.mode = CameraMode.CENTERED
        return self.mode

    def get_follow_target(
        self,
        anchor_x: float,
        anchor_y: float,
        mouse_pos: tuple[int, int],
        viewport_size: tuple[int, int],
        block_size: float,
    ) -> tuple[float, float]:
        """返回当前模式下的镜头世界坐标目标。"""
        if self.mode is CameraMode.CENTERED:
            return anchor_x, anchor_y

        width, height = viewport_size
        if width <= 0 or height <= 0 or block_size <= 0:
            return anchor_x, anchor_y

        mouse_x, mouse_y = mouse_pos
        horizontal = max(
            -1.0, min(1.0, (mouse_x - width / 2) / (width / 2))
        )
        # 屏幕 Y 轴向下，世界 Y 轴向上，因此需要取反。
        vertical = max(
            -1.0, min(1.0, (height / 2 - mouse_y) / (height / 2))
        )

        max_x = width / block_size * self.mouse_lead_strength
        max_y = height / block_size * self.mouse_lead_strength
        return anchor_x + horizontal * max_x, anchor_y + vertical * max_y

    def get_lead_screen_offset(self, block_size: float) -> tuple[float, float]:
        """返回镜头引导量对应的玩家屏幕像素偏移。"""
        return -self.lead_x * block_size, self.lead_y * block_size

    def get_player_screen_center(
        self, viewport_size: tuple[int, int], block_size: float
    ) -> tuple[float, float]:
        """返回绕过服务器位置插值的主玩家当前屏幕中心。"""
        width, height = viewport_size
        offset_x, offset_y = self.get_lead_screen_offset(block_size)
        return width / 2 + offset_x, height / 2 + offset_y

    def rescale_lead_for_zoom(
        self, old_block_size: float, new_block_size: float
    ) -> None:
        """缩放镜头时保持鼠标引导产生的屏幕像素偏移不变。"""
        if old_block_size <= 0 or new_block_size <= 0:
            return

        ratio = old_block_size / new_block_size

        def rescale_pair(position, lead):
            if position is None:
                return position, lead * ratio
            anchor = position - lead
            lead *= ratio
            return anchor + lead, lead

        self.x, self.lead_x = rescale_pair(self.x, self.lead_x)
        self.y, self.lead_y = rescale_pair(self.y, self.lead_y)
        self._target_x, self._target_lead_x = rescale_pair(
            self._target_x, self._target_lead_x
        )
        self._target_y, self._target_lead_y = rescale_pair(
            self._target_y, self._target_lead_y
        )
        self._start_x, self._start_lead_x = rescale_pair(
            self._start_x, self._start_lead_x
        )
        self._start_y, self._start_lead_y = rescale_pair(
            self._start_y, self._start_lead_y
        )

    def move_to(
        self,
        target_x: float,
        target_y: float,
        duration: float = 0.1,
        *,
        lead_offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        """启动线性移动到目标位置"""
        self._target_x = target_x
        self._target_y = target_y
        self._target_lead_x, self._target_lead_y = lead_offset
        self._start_x = self.x
        self._start_y = self.y
        self._start_lead_x = self.lead_x
        self._start_lead_y = self.lead_y
        self._start_time = time.perf_counter()
        self._duration = duration

    def snap_to(self, target_x: float, target_y: float) -> None:
        self.x = target_x
        self.y = target_y
        self.lead_x = 0.0
        self.lead_y = 0.0
        self._target_lead_x = 0.0
        self._target_lead_y = 0.0
        self._start_lead_x = 0.0
        self._start_lead_y = 0.0
        self._target_x = None
        self._target_y = None
        self._start_x = None
        self._start_y = None
        self._start_time = None

    def update(self):
        """更新相机位置（每帧调用）"""
        if self._target_x is None:
            return

        elapsed = time.perf_counter() - self._start_time
        progress = min(elapsed / self._duration, 1.0)

        self.x = self._start_x + (self._target_x - self._start_x) * progress
        self.y = self._start_y + (self._target_y - self._start_y) * progress
        self.lead_x = self._start_lead_x + (
            self._target_lead_x - self._start_lead_x
        ) * progress
        self.lead_y = self._start_lead_y + (
            self._target_lead_y - self._start_lead_y
        ) * progress

        if progress >= 1.0:
            self._target_x = None
            self._target_y = None
            self._start_x = None
            self._start_y = None
            self._start_time = None
