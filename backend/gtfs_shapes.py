import asyncio
import csv
import io
import json
import logging
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import httpx

from config import (
    CERCANIAS_GTFS_URL,
    GTFS_CACHE_DIR,
    GTFS_CACHE_SECONDS,
    LD_GTFS_URL,
    USER_AGENT,
)
from parser import extract_line
from schemas import ServiceKind

logger = logging.getLogger("renfe_tracker.shapes")

GTFS_FEEDS: dict[ServiceKind, str] = {
    "cercanias": CERCANIAS_GTFS_URL,
    "ld": LD_GTFS_URL,
}
CACHE_VERSION = 1
CACHE_FILE = GTFS_CACHE_DIR / "route-lines-v1.json"
_PALETTE = ("#75B6E0", "#00943D", "#952585", "#E54A3C", "#BCCF00", "#2C2A86", "#E93CAC", "#F4A261")


class ShapeLoadError(Exception):
    pass


class ShapeStore:
    def __init__(self) -> None:
        self._bodies: dict[str, bytes] | None = None

    async def ensure_loaded(self) -> None:
        if self._bodies is not None:
            return
        async with _GUARD:
            if self._bodies is not None:
                return
            self._bodies = await asyncio.to_thread(load_route_lines)

    def body(self, feed: str) -> bytes:
        if self._bodies is None:
            raise ShapeLoadError("los trazados no están listos")
        return self._bodies[feed]


_GUARD = asyncio.Lock()


def load_route_lines() -> dict[str, bytes]:
    cached = _read_cache()
    if cached is not None and _fresh(CACHE_FILE):
        return _encode(cached["collections"])
    collections, skipped, failed = _collections_from_disk_or_network()
    if failed and not any(item["features"] for item in collections.values()):
        if cached is not None:
            logger.warning("GTFS no disponible; se usa la caché antigua")
            return _encode(cached["collections"])
        raise ShapeLoadError("No se han podido cargar los trazados")
    for note in skipped:
        logger.info("Trazado omitido: %s", note)
    _write_cache({"version": CACHE_VERSION, "skipped": skipped, "collections": collections})
    return _encode(collections)


def collection_from_zip(blob: bytes, service: ServiceKind) -> tuple[dict[str, Any] | None, str | None]:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            names = set(archive.namelist())
            if "shapes.txt" not in names:
                return None, "el zip no incluye shapes.txt"
            routes = _routes(archive.read("routes.txt"))
            chosen = _choose_lines(archive.read("trips.txt"), routes)
            features = _line_features(archive.read("shapes.txt"), chosen, service)
    except (zipfile.BadZipFile, KeyError) as exc:
        return None, f"GTFS ilegible ({exc.__class__.__name__})"
    return {"type": "FeatureCollection", "features": features}, None


def _collections_from_disk_or_network() -> tuple[dict[str, dict[str, Any]], list[str], bool]:
    collections: dict[str, dict[str, Any]] = {}
    skipped: list[str] = []
    failed = False
    for service, url in GTFS_FEEDS.items():
        try:
            blob = _zip_bytes(service, url)
        except (httpx.HTTPError, OSError) as exc:
            failed = True
            skipped.append(f"{service}: no se pudo descargar el GTFS ({exc.__class__.__name__})")
            collections[service] = _empty()
            continue
        collection, reason = collection_from_zip(blob, service)
        if reason:
            skipped.append(f"{service}: {reason}")
            collections[service] = _empty()
            continue
        collections[service] = collection or _empty()
    return collections, skipped, failed


def _zip_bytes(service: str, url: str) -> bytes:
    GTFS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = GTFS_CACHE_DIR / f"{service}.zip"
    if _fresh(path):
        return path.read_bytes()
    try:
        _download(url, path)
    except (httpx.HTTPError, OSError):
        if path.is_file():
            logger.warning("Se reutiliza el zip antiguo de %s", service)
            return path.read_bytes()
        raise
    return path.read_bytes()


def _download(url: str, path: Path) -> None:
    timeout = httpx.Timeout(60.0, connect=10.0)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/zip"}
    temporary = path.with_suffix(".zip.part")
    with httpx.Client(timeout=timeout, headers=headers, follow_redirects=True) as client:
        with client.stream("GET", url) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
    temporary.replace(path)


def _routes(raw: bytes) -> dict[str, tuple[str | None, str | None]]:
    indexed: dict[str, tuple[str | None, str | None]] = {}
    for row in _rows(raw):
        route_id = row.get("route_id") or ""
        if not route_id:
            continue
        indexed[route_id] = (extract_line(row.get("route_short_name")), _color(row.get("route_color") or ""))
    return indexed


def _choose_lines(
    raw: bytes,
    routes: dict[str, tuple[str | None, str | None]],
) -> dict[str, tuple[str | None, str]]:
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    colors: dict[tuple[str, str], str] = {}
    seen: set[str] = set()
    for row in _rows(raw):
        shape_id = row.get("shape_id") or ""
        if not shape_id:
            continue
        seen.add(shape_id)
        route = routes.get(row.get("route_id") or "")
        line = route[0] if route else None
        line = line or _line_from_shape_id(shape_id)
        if not line:
            continue
        votes[shape_id][line] += 1
        if route and route[1]:
            colors[(shape_id, line)] = route[1]
    chosen: dict[str, tuple[str | None, str]] = {}
    for shape_id in seen:
        tally = votes.get(shape_id)
        line = tally.most_common(1)[0][0] if tally else _line_from_shape_id(shape_id)
        color = colors.get((shape_id, line or ""), "") or _fallback_color(line)
        chosen[shape_id] = (line, color)
    return chosen


def _line_features(raw: bytes, chosen: dict[str, tuple[str | None, str]], service: ServiceKind) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[int, float, float]]] = defaultdict(list)
    for row in _rows(raw):
        shape_id = row.get("shape_id") or ""
        point = _point(row)
        if not shape_id or point is None or shape_id not in chosen:
            continue
        grouped[shape_id].append(point)
    features: list[dict[str, Any]] = []
    for shape_id, points in grouped.items():
        coordinates = [[lon, lat] for _seq, lon, lat in sorted(points)]
        if len(coordinates) < 2:
            continue
        line, color = chosen[shape_id]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coordinates},
                "properties": {"line": line, "color": color, "service": service, "shapeId": shape_id},
            }
        )
    return features


def _point(row: dict[str, str]) -> tuple[int, float, float] | None:
    try:
        sequence = int(row.get("shape_pt_sequence") or "")
        lat = float(row.get("shape_pt_lat") or "")
        lon = float(row.get("shape_pt_lon") or "")
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return sequence, round(lon, 6), round(lat, 6)


def _rows(raw: bytes):
    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    try:
        headers = [cell.strip() for cell in next(reader)]
    except StopIteration:
        return
    for cells in reader:
        yield {headers[index]: cells[index].strip() if index < len(cells) else "" for index in range(len(headers))}


def _line_from_shape_id(shape_id: str) -> str | None:
    return extract_line(shape_id.rsplit("_", 1)[-1])


def _color(value: str) -> str | None:
    text = value.strip().lstrip("#")
    if len(text) == 6 and all(char in "0123456789abcdefABCDEF" for char in text):
        return f"#{text.upper()}"
    return None


def _fallback_color(line: str | None) -> str:
    if not line:
        return "#F3EFE4"
    return _PALETTE[sum(ord(char) for char in line) % len(_PALETTE)]


def _empty() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def _encode(collections: dict[str, dict[str, Any]]) -> dict[str, bytes]:
    cercanias = _as_collection(collections.get("cercanias"))
    ld = _as_collection(collections.get("ld"))
    merged = {"type": "FeatureCollection", "features": [*cercanias["features"], *ld["features"]]}
    bodies = {"cercanias": cercanias, "ld": ld, "all": merged}
    return {name: json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode() for name, body in bodies.items()}


def _as_collection(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("features"), list):
        return _empty()
    return value


def _read_cache() -> dict[str, Any] | None:
    if not CACHE_FILE.is_file():
        return None
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
        return None
    collections = payload.get("collections")
    if not isinstance(collections, dict):
        return None
    return payload


def _write_cache(payload: dict[str, Any]) -> None:
    GTFS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_FILE.with_suffix(".json.part")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(CACHE_FILE)


def _fresh(path: Path) -> bool:
    if not path.is_file():
        return False
    return time.time() - path.stat().st_mtime < GTFS_CACHE_SECONDS
