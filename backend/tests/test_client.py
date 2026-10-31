import asyncio

import httpx
import pytest

from config import CERCANIAS_URL, LD_URL
from renfe_client import RenfeClient, RenfeUnavailable


def test_cache_ttl_is_fifteen_seconds() -> None:
    asyncio.run(_cache_ttl())


def test_failed_refresh_serves_stale_and_does_not_retry_inside_ttl() -> None:
    asyncio.run(_stale_fallback())


def test_upstream_failure_is_remembered_for_the_ttl() -> None:
    asyncio.run(_failure_is_cached())


def test_invalid_payload_is_an_unavailable_feed() -> None:
    asyncio.run(_invalid_payload())


async def _cache_ttl() -> None:
    calls = {"n": 0}
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        seen.append(str(request.url))
        return httpx.Response(200, json={"entity": [], "n": calls["n"]})

    clock = {"t": 1_000.0}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RenfeClient(ttl_seconds=15, client=http, clock=lambda: clock["t"])
        first = await client.fetch_feed("cercanias")
        second = await client.fetch_feed("cercanias")
        assert calls["n"] == 1
        assert first == second
        clock["t"] = 1_014.9
        await client.fetch_feed("cercanias")
        assert calls["n"] == 1
        clock["t"] = 1_015.0
        third = await client.fetch_feed("cercanias")
        assert calls["n"] == 2
        assert third["n"] == 2
        await client.fetch_feed("ld")
        assert calls["n"] == 3
    assert seen == [CERCANIAS_URL, CERCANIAS_URL, LD_URL]


async def _stale_fallback() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, json={"entity": [{"ok": True}]})
        return httpx.Response(503, text="no")

    clock = {"t": 50.0}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RenfeClient(ttl_seconds=15, client=http, clock=lambda: clock["t"])
        assert (await client.fetch_feed("ld"))["entity"] == [{"ok": True}]
        clock["t"] = 70.0
        assert (await client.fetch_feed("ld"))["entity"] == [{"ok": True}]
        assert (await client.fetch_feed("ld"))["entity"] == [{"ok": True}]
        assert calls["n"] == 2


async def _failure_is_cached() -> None:
    calls = {"n": 0}

    def handler(_request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="down")

    clock = {"t": 0.0}
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RenfeClient(ttl_seconds=15, client=http, clock=lambda: clock["t"])
        with pytest.raises(RenfeUnavailable):
            await client.fetch_feed("cercanias")
        with pytest.raises(RenfeUnavailable):
            await client.fetch_feed("cercanias")
        assert calls["n"] == 1
        clock["t"] = 15.0
        with pytest.raises(RenfeUnavailable):
            await client.fetch_feed("cercanias")
        assert calls["n"] == 2


async def _invalid_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("vehicle_positions.json"):
            return httpx.Response(200, content=b"not-json")
        return httpx.Response(200, json=["nope"])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = RenfeClient(ttl_seconds=15, client=http)
        with pytest.raises(RenfeUnavailable):
            await client.fetch_feed("cercanias")
        with pytest.raises(RenfeUnavailable):
            await client.fetch_feed("ld")
