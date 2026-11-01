import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from config import CERCANIAS_URL, CACHE_TTL_SECONDS, HTTP_TIMEOUT_SECONDS, LD_URL, USER_AGENT
from schemas import RenfeKind

logger = logging.getLogger("renfe_tracker.client")

FEED_URLS: dict[RenfeKind, str] = {
    "cercanias": CERCANIAS_URL,
    "ld": LD_URL,
}


class RenfeUnavailable(Exception):
    def __init__(self, kind: RenfeKind) -> None:
        super().__init__(kind)
        self.kind = kind


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
        self._cache: dict[RenfeKind, dict[str, Any]] = {}
        self._fetched_at: dict[RenfeKind, float] = {}
        self._inflight: dict[RenfeKind, asyncio.Task[dict[str, Any]]] = {}
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
        reserved = await self._reserve(kind)
        if not isinstance(reserved, asyncio.Task):
            return reserved
        try:
            payload = await reserved
        except (httpx.HTTPError, ValueError) as exc:
            await self._remember(kind, reserved, None)
            stale = self._cache.get(kind)
            if stale is not None:
                logger.warning("Renfe falló en %s; se sirve la caché anterior", kind)
                return stale
            logger.warning("Renfe falló en %s: %s", kind, exc)
            raise RenfeUnavailable(kind) from exc
        await self._remember(kind, reserved, payload)
        return payload

    async def _reserve(self, kind: RenfeKind) -> dict[str, Any] | asyncio.Task[dict[str, Any]]:
        async with self._lock:
            if self._within_ttl(kind):
                cached = self._cache.get(kind)
                if cached is None:
                    raise RenfeUnavailable(kind)
                return cached
            task = self._inflight.get(kind)
            if task is None:
                task = asyncio.create_task(self._download(kind))
                self._inflight[kind] = task
            return task

    async def _remember(
        self,
        kind: RenfeKind,
        task: asyncio.Task[dict[str, Any]],
        payload: dict[str, Any] | None,
    ) -> None:
        async with self._lock:
            if self._inflight.get(kind) is task:
                self._inflight.pop(kind, None)
            self._fetched_at[kind] = self._clock()
            if payload is not None:
                self._cache[kind] = payload

    def _within_ttl(self, kind: RenfeKind) -> bool:
        fetched = self._fetched_at.get(kind)
        return fetched is not None and self._clock() - fetched < self._ttl

    async def _download(self, kind: RenfeKind) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("RenfeClient no está abierto")
        response = await self._client.get(FEED_URLS[kind])
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("el feed no es un objeto JSON")
        return payload
