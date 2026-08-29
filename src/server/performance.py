from collections import deque
from dataclasses import dataclass
import threading
import time


TPS_WINDOWS = (60.0, 300.0, 900.0)
MSPT_WINDOWS = (5.0, 10.0, 60.0)


@dataclass(frozen=True)
class TickPerformanceSnapshot:
    current_tps: float
    current_mspt: float
    tps_averages: tuple[float, float, float]
    mspt_stats: tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]


class TickPerformanceMonitor:
    """Thread-safe rolling tick statistics backed by monotonic timestamps."""

    def __init__(self, target_tps: float, clock=time.perf_counter):
        self.target_tps = float(target_tps)
        self._clock = clock
        self._started_at = clock()
        self._last_tick_completed_at: float | None = None
        self._samples: deque[tuple[float, float]] = deque()
        self._lock = threading.Lock()
        self.current_tps = self.target_tps
        self.current_mspt = 0.0

    def reset(self, started_at: float | None = None) -> None:
        now = self._clock() if started_at is None else float(started_at)
        with self._lock:
            self._started_at = now
            self._last_tick_completed_at = None
            self._samples.clear()
            self.current_tps = self.target_tps
            self.current_mspt = 0.0

    def record_tick(
        self, mspt: float, completed_at: float | None = None
    ) -> tuple[float, float]:
        now = self._clock() if completed_at is None else float(completed_at)
        mspt = max(0.0, float(mspt))
        with self._lock:
            if self._last_tick_completed_at is None:
                current_tps = self.target_tps
            else:
                tick_interval = now - self._last_tick_completed_at
                current_tps = (
                    self.target_tps
                    if tick_interval <= 0.0
                    else min(self.target_tps, 1.0 / tick_interval)
                )
            self._last_tick_completed_at = now
            self.current_tps = current_tps
            self.current_mspt = mspt
            self._samples.append((now, mspt))
            self._prune(now)
            return current_tps, mspt

    def snapshot(self, now: float | None = None) -> TickPerformanceSnapshot:
        now = self._clock() if now is None else float(now)
        with self._lock:
            self._prune(now)
            samples = tuple(self._samples)
            current_tps = self.current_tps
            current_mspt = self.current_mspt
            started_at = self._started_at

        tps_averages = tuple(
            self._average_tps(samples, started_at, now, window)
            for window in TPS_WINDOWS
        )
        mspt_stats = tuple(
            self._mspt_stats(samples, now, window) for window in MSPT_WINDOWS
        )
        return TickPerformanceSnapshot(
            current_tps=current_tps,
            current_mspt=current_mspt,
            tps_averages=tps_averages,
            mspt_stats=mspt_stats,
        )

    def _prune(self, now: float) -> None:
        cutoff = now - max(TPS_WINDOWS)
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def _average_tps(
        self,
        samples: tuple[tuple[float, float], ...],
        started_at: float,
        now: float,
        window: float,
    ) -> float:
        window_started_at = max(started_at, now - window)
        elapsed = now - window_started_at
        if elapsed <= 0.0:
            return self.target_tps
        tick_count = sum(1 for completed_at, _ in samples if completed_at > window_started_at)
        return min(self.target_tps, tick_count / elapsed)

    @staticmethod
    def _mspt_stats(
        samples: tuple[tuple[float, float], ...], now: float, window: float
    ) -> tuple[float, float, float]:
        cutoff = now - window
        values = [mspt for completed_at, mspt in samples if completed_at > cutoff]
        if not values:
            return 0.0, 0.0, 0.0
        return sum(values) / len(values), min(values), max(values)
