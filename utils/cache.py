import time
import threading
from collections import OrderedDict
from typing import Any, Optional, Dict

class InMemoryCache:
    """
    A thread-safe In-Memory LRU (Least Recently Used) cache with TTL (Time-To-Live) support.
    Used to store LLM response mappings to reduce model calling costs and latency.
    """
    def __init__(self, limit: int = 500, ttl_seconds: int = 3600):
        self.limit = limit
        self.ttl = ttl_seconds
        self.cache: OrderedDict = OrderedDict()
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieves an item from cache. Returns None if not found or expired.
        """
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            value, expiry = self.cache[key]
            
            # Check for TTL expiry
            if time.time() > expiry:
                del self.cache[key]
                self.misses += 1
                return None
                
            # Move to end (LRU behavior)
            self.cache.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        """
        Saves an item to cache. Evicts oldest item if limit exceeded.
        """
        with self.lock:
            # If key already exists, delete it first to update its position
            if key in self.cache:
                del self.cache[key]
                
            expiry = time.time() + self.ttl
            self.cache[key] = (value, expiry)
            
            # Eviction policy
            if len(self.cache) > self.limit:
                self.cache.popitem(last=False)

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns diagnostics statistics of the cache.
        """
        with self.lock:
            # Clean expired items to get exact active size
            now = time.time()
            expired_keys = [k for k, (_, exp) in self.cache.items() if now > exp]
            for k in expired_keys:
                del self.cache[k]
                
            total_requests = self.hits + self.misses
            hit_ratio = round(self.hits / total_requests, 4) if total_requests > 0 else 0.0
            
            return {
                "size": len(self.cache),
                "limit": self.limit,
                "hits": self.hits,
                "misses": self.misses,
                "hit_ratio": hit_ratio
            }

    def clear(self) -> None:
        """
        Clears all items in the cache.
        """
        with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
