from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Dict, List, Optional

from backend.app.schemas.weather import ForecastPoint, ProviderHealth


class ProviderError(RuntimeError):
    """Raised when an upstream provider cannot satisfy a request.

    The API layer turns this into an explicit DEGRADED response rather than
    letting an httpx exception escape as an opaque 500.
    """

    def __init__(self, message: str, *, upstream_status: Optional[int] = None):
        super().__init__(message)
        self.upstream_status = upstream_status


class WeatherProvider(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def fetch_forecast(
        self, latitude: float, longitude: float, forecast_days: int
    ) -> Dict[str, List[ForecastPoint]]:
        """Return {model_key: [ForecastPoint, ...]} aligned on a common time axis."""

    @abstractmethod
    async def check_health(self) -> List[ProviderHealth]:
        """Probe each model independently and report per-model status."""

    @abstractmethod
    def close(self) -> None:
        """Release pooled connections."""


class TTLCache:
    """Bounded LRU cache with a monotonic clock.

    The previous implementation was an unbounded dict keyed by rounded
    coordinates, so every distinct lat/lon permanently retained hundreds of
    Pydantic objects and a client varying coordinates could exhaust memory.
    It also used ``time.time()``, which is not monotonic and can be nudged
    backwards by NTP corrections.
    """

    def __init__(self, max_entries: int):
        self._data: "OrderedDict[str, Any]" = OrderedDict()
        self._expires: Dict[str, float] = {}
        self._max = max(1, max_entries)
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._data:
                return None
            if time.monotonic() >= self._expires.get(key, 0.0):
                self._data.pop(key, None)
                self._expires.pop(key, None)
                return None
            self._data.move_to_end(key)
            return self._data[key]

    async def set(self, key: str, value: Any, ttl: int) -> None:
        async with self._lock:
            self._data[key] = value
            self._expires[key] = time.monotonic() + ttl
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                evicted, _ = self._data.popitem(last=False)
                self._expires.pop(evicted, None)

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
            self._expires.clear()

    @property
    def size(self) -> int:
        return len(self._data)
