"""Простий кеш у пам'яті з терміном життя записів.

Повторні запити до тієї самої точки не витрачають квоту Places API.
"""

from __future__ import annotations

import time
from typing import Callable, Generic, Hashable, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: int = 3600, max_items: int = 1000,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._max = max_items
        self._clock = clock
        self._data: dict[Hashable, tuple[float, T]] = {}

    def get(self, key: Hashable) -> T | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self._clock() >= expires_at:
            self._data.pop(key, None)
            return None
        return value

    def set(self, key: Hashable, value: T) -> None:
        if self._ttl <= 0:
            return
        if len(self._data) >= self._max:
            # Видаляємо найстаріший запис (dict зберігає порядок вставки).
            self._data.pop(next(iter(self._data)))
        self._data[key] = (self._clock() + self._ttl, value)

    def __len__(self) -> int:
        return len(self._data)
