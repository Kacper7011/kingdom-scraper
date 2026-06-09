"""Redis queue manager: URL deduplication, stats, and engine status."""

import logging

import redis

from shared.constants import (
    KEY_ENGINE_STATUS,
    KEY_QUEUE,
    KEY_STAT_ERRORS,
    KEY_STAT_SCRAPED,
    KEY_VISITED,
    REDIS_HOST,
    REDIS_PORT,
    STATUS_STOPPED,
)

logger = logging.getLogger(__name__)


class QueueError(Exception):
    """Raised when a Redis queue operation fails."""


class QueueManager:
    """Wraps Redis operations for URL queue and scraper statistics."""

    def __init__(self) -> None:
        try:
            self._r = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
            )
            self._r.ping()
        except redis.RedisError as exc:
            raise QueueError(f"Cannot connect to Redis at {REDIS_HOST}:{REDIS_PORT}") from exc

    def push_url(self, url: str) -> bool:
        """Push a single URL if it has not been visited yet. Returns True if queued."""
        try:
            if self._r.sismember(KEY_VISITED, url):
                return False
            self._r.rpush(KEY_QUEUE, url)
            logger.debug("Queued: %s", url)
            return True
        except redis.RedisError as exc:
            raise QueueError(f"push_url failed for {url}") from exc

    def pop_url(self, timeout: int = 5) -> str | None:
        """Block until a URL is available; returns None on timeout."""
        try:
            result = self._r.blpop(KEY_QUEUE, timeout=timeout)
            if result is None:
                return None
            _, url = result
            return url
        except redis.RedisError as exc:
            raise QueueError("pop_url failed") from exc

    def mark_visited(self, url: str) -> None:
        """Add URL to the visited set so it is never queued again."""
        try:
            self._r.sadd(KEY_VISITED, url)
        except redis.RedisError as exc:
            raise QueueError(f"mark_visited failed for {url}") from exc

    def is_visited(self, url: str) -> bool:
        try:
            return bool(self._r.sismember(KEY_VISITED, url))
        except redis.RedisError as exc:
            raise QueueError(f"is_visited failed for {url}") from exc

    def push_many(self, urls: list[str]) -> int:
        """Batch-push URLs, skipping already-visited ones. Returns count queued."""
        queued = 0
        for url in urls:
            if self.push_url(url):
                queued += 1
        return queued

    def increment_stat(self, key: str) -> None:
        """Increment a numeric counter key (stats:scraped or stats:errors)."""
        try:
            self._r.incr(key)
        except redis.RedisError as exc:
            raise QueueError(f"increment_stat failed for {key}") from exc

    def get_stats(self) -> dict:
        """Return current counters and queue length."""
        try:
            return {
                "scraped": int(self._r.get(KEY_STAT_SCRAPED) or 0),
                "errors": int(self._r.get(KEY_STAT_ERRORS) or 0),
                "queue_length": self._r.llen(KEY_QUEUE),
                "visited_count": self._r.scard(KEY_VISITED),
                "status": self._r.get(KEY_ENGINE_STATUS) or STATUS_STOPPED,
            }
        except redis.RedisError as exc:
            raise QueueError("get_stats failed") from exc

    def set_engine_status(self, status: str) -> None:
        try:
            self._r.set(KEY_ENGINE_STATUS, status)
        except redis.RedisError as exc:
            raise QueueError(f"set_engine_status failed: {status}") from exc

    def get_engine_status(self) -> str:
        try:
            return self._r.get(KEY_ENGINE_STATUS) or STATUS_STOPPED
        except redis.RedisError as exc:
            raise QueueError("get_engine_status failed") from exc
