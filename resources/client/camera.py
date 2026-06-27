import time


class Camera:
    def __init__(self):
        self.x = 0
        self.y = 0
        self._target_x = None
        self._target_y = None
        self._start_x = None
        self._start_y = None
        self._start_time = None
        self._duration = 0.05  # 50ms

    def move_to(self, target_x: float, target_y: float, duration: float = 0.1):
        """启动线性移动到目标位置"""
        self._target_x = target_x
        self._target_y = target_y
        self._start_x = self.x
        self._start_y = self.y
        self._start_time = time.perf_counter()
        self._duration = duration

    def update(self):
        """更新相机位置（每帧调用）"""
        if self._target_x is None:
            return

        elapsed = time.perf_counter() - self._start_time
        progress = min(elapsed / self._duration, 1.0)

        self.x = self._start_x + (self._target_x - self._start_x) * progress
        self.y = self._start_y + (self._target_y - self._start_y) * progress

        if progress >= 1.0:
            self._target_x = None
            self._target_y = None
            self._start_x = None
            self._start_y = None
            self._start_time = None
