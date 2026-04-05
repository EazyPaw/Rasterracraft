import time
from collections import deque
from functools import wraps

def rate_limit(max_calls: int = 20, period: float = 1.0):
    """
    限流装饰器
    :param max_calls: 在 period 秒内最多允许调用的次数
    :param period: 时间窗口长度（秒）
    """
    def decorator(func):
        # 记录最近调用时间戳的队列，最大长度即为 max_calls
        timestamps = deque(maxlen=max_calls)

        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.monotonic()

            # 清理时间窗口外的旧记录
            while timestamps and timestamps[0] <= now - period:
                timestamps.popleft()

            # 如果已达上限，则等待到最早记录移出窗口
            if len(timestamps) >= max_calls:
                sleep_time = timestamps[0] + period - now
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.monotonic()          # 更新当前时间
                    # 再次清理过期的记录
                    while timestamps and timestamps[0] <= now - period:
                        timestamps.popleft()

            # 记录本次调用时间戳
            timestamps.append(now)
            return func(*args, **kwargs)

        return wrapper
    return decorator