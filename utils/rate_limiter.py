import time
import threading
from typing import Dict, List

class SlidingWindowRateLimiter:
    """
    Thread-safe, sliding-window rate limiter.
    Limits actions (e.g. queries, file uploads) per client IP address.
    """
    def __init__(self, limit: int = 60, window_seconds: int = 3600):
        self.limit = limit
        self.window = window_seconds
        self.history: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def is_allowed(self, ip: str) -> bool:
        """
        Returns True if the client IP is within rate limits, False otherwise.
        """
        with self.lock:
            now = time.time()
            cutoff = now - self.window

            # Retrieve and clean history for this IP
            timestamps = self.history.get(ip, [])
            filtered_timestamps = [t for t in timestamps if t > cutoff]

            if len(filtered_timestamps) >= self.limit:
                self.history[ip] = filtered_timestamps
                return False

            # Add current request timestamp
            filtered_timestamps.append(now)
            self.history[ip] = filtered_timestamps
            return True

    def get_remaining(self, ip: str) -> int:
        """
        Returns number of requests remaining for the current window.
        """
        with self.lock:
            now = time.time()
            cutoff = now - self.window
            timestamps = self.history.get(ip, [])
            filtered_timestamps = [t for t in timestamps if t > cutoff]
            return max(0, self.limit - len(filtered_timestamps))
