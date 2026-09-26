"""Ограничение частоты вопросов помощнику: не больше N в минуту на пользователя (в памяти)."""

import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int, *, clock=time.monotonic) -> None:
        self.per_minute = per_minute
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = self._clock()
        hits = self._hits[key]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= self.per_minute:
            return False
        hits.append(now)
        return True
