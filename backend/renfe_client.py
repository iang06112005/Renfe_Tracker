import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Literal

import httpx

from config import (
    CERCANIAS_TRIP_UPDATES_URL,
    CERCANIAS_URL,
    CACHE_TTL_SECONDS,
    HTTP_TIMEOUT_SECONDS,
    LD_TRIP_UPDATES_URL,
    LD_URL,
    USER_AGENT,
)
from schemas import RenfeKind

logger = logging.getLogger("renfe_tracker.client")

FeedKind = Literal["positions", "trip_updates"]
CacheKey = tuple[FeedKind, RenfeKind]

FEED_URLS: dict[CacheKey, str] = {
    ("positions", "cercanias"): CERCANIAS_URL,
    ("positions", "ld"): LD_URL,
    ("trip_updates", "cercanias"): CERCANIAS_TRIP_UPDATES_URL,
    ("trip_updates", "ld"): LD_TRIP_UPDATES_URL,
}


class RenfeUnavailable(Exception):
    def __init__(self, kind: RenfeKind, feed: FeedKind = "positions") -> None:
        super().__init__(kind)
        self.kind = kind
        self.feed = feed


class RenfeClient:
    def __init__(
        self,
        *,
        ttl_seconds: float = CACHE_TTL_SECONDS,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._client = client
        self._owns_client = client is None
        self._clock = clock or time.monotonic
        self._cache: dict[CacheKey, dict[str, Any]] = {}
        self._fetched_at: dict[CacheKey, float] = {}
        self._inflight: dict[CacheKey, asyncio.Task[dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=5.0),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                follow_redirects=True,
            )

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def fetch_feed(self, kind: RenfeKind) -> dict[str, Any]:
        return await self._fetch("positions", kind)

    async def fetch_trip_updates(self, kind: RenfeKind) -> dict[str, Any]:
        return await self._fetch("trip_updates", kind)

    async def _fetch(self, feed: FeedKind, kind: RenfeKind) -> dict[str, Any]:
        key: CacheKey = (feed, kind)
        reserved = await self._reserve(key)
        if not isinstance(reserved, asyncio.Task):
            return reserved
        try:
            payload = await reserved
        except (httpx.HTTPError, ValueError) as exc:
            await self._remember(key, reserved, None)
            stale = self._cache.get(key)
            if stale is not None:
                logger.warning("Renfe falló en %s/%s; se sirve la caché anterior", feed, kind)
                return stale
            logger.warning("Renfe falló en %s/%s: %s", feed, kind, exc)
            raise RenfeUnavailable(kind, feed) from exc
        await self._remember(key, reserved, payload)
        return payload

    async def _reserve(self, key: CacheKey) -> dict[str, Any] | asyncio.Task[dict[str, Any]]:
        async with self._lock:
            if self._within_ttl(key):
                cached = self._cache.get(key)
                if cached is None:
                    raise RenfeUnavailable(key[1], key[0])
                return cached
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._download(key))
                self._inflight[key] = task
            return task

    async def _remember(
        self,
        key: CacheKey,
        task: asyncio.Task[dict[str, Any]],
        payload: dict[str, Any] | None,
    ) -> None:
        async with self._lock:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)
            self._fetched_at[key] = self._clock()
            if payload is not None:
                self._cache[key] = payload

    def _within_ttl(self, key: CacheKey) -> bool:
        fetched = self._fetched_at.get(key)
        return fetched is not None and self._clock() - fetched < self._ttl

    async def _download(self, key: CacheKey) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("RenfeClient no está abierto")
        response = await self._client.get(FEED_URLS[key])
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("el feed no es un objeto JSON")
        return payload
