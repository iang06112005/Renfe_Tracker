import json
import logging
import re
from typing import Any

import httpx

from config import GTFS_CACHE_DIR, METRO_GTFS_URL
from gtfs_shapes import _choose_lines, _color, _line_features, _member, _open_feed_zip, _rows

logger = logging.getLogger("renfe_tracker.transit")

EMPTY_COLLECTION = {"type": "FeatureCollection", "features": []}
METRO_ATTRIBUTION = "Líneas y estaciones: CRTM (Powered by MITRAMS)"
_STOP_FEEDS = ("cercanias", "ld")


def load_transit_layers() -> dict[str, bytes]:
    lines = _metro_lines()
    stops = {
        "cercanias": _stops_from_zip("cercanias", parents_only=False),
        "ld": _stops_from_zip("ld", parents_only=False),
        "metro": _stops_from_zip("metro", parents_only=True),
    }
    merged = {
        "type": "FeatureCollection",
        "features": [*stops["cercanias"]["features"], *stops["ld"]["features"]],
    }
    bodies = {
        "metro-lines": lines,
        "stops-cercanias": stops["cercanias"],
        "stops-ld": stops["ld"],
        "stops-all": merged,
        "stops-metro": stops["metro"],
    }
    return {name: _dump(body) for name, body in bodies.items()}


def _metro_lines() -> dict[str, Any]:
    try:
        archive = _open_feed_zip("metro", METRO_GTFS_URL)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("GTFS de Metro no disponible (%s)", exc.__class__.__name__)
        return EMPTY_COLLECTION
    with archive:
        if "shapes.txt" not in archive.namelist() or "routes.txt" not in archive.namelist():
            logger.warning("El GTFS de Metro no trae geometría de líneas")
            return EMPTY_COLLECTION
        with _member(archive, "routes.txt") as handle:
            routes = _metro_routes(_rows(handle))
        if "trips.txt" not in archive.namelist():
            return EMPTY_COLLECTION
        with _member(archive, "trips.txt") as handle:
            chosen = _choose_lines(_rows(handle), routes)
        with _member(archive, "shapes.txt") as handle:
            features = _line_features(_rows(handle), chosen, "metro")
    return {"type": "FeatureCollection", "features": features}


def _metro_routes(rows: Any) -> dict[str, tuple[str | None, str | None]]:
    indexed: dict[str, tuple[str | None, str | None]] = {}
    for row in rows:
        route_id = row.get("route_id") or ""
        line = _metro_line(row.get("route_short_name"))
        if not route_id or not line:
            continue
        indexed[route_id] = (line, _readable_color(_color(row.get("route_color") or "")))
    return indexed


def _metro_line(value: str | None) -> str | None:
    text = (value or "").strip()
    if text and len(text) <= 3 and text.isalnum():
        return text
    return None


def _readable_color(color: str | None) -> str | None:
    if not color:
        return None
    text = color.lstrip("#")
    if len(text) != 6:
        return color
    red = int(text[0:2], 16)
    green = int(text[2:4], 16)
    blue = int(text[4:6], 16)
    if (0.299 * red + 0.587 * green + 0.114 * blue) / 255 > 0.9:
        return "#5C6B73"
    return color


def _stops_from_zip(service: str, parents_only: bool) -> dict[str, Any]:
    path = GTFS_CACHE_DIR / f"{service}.zip"
    if not path.is_file():
        return EMPTY_COLLECTION
    try:
        import zipfile

        with zipfile.ZipFile(path) as archive:
            if "stops.txt" not in archive.namelist():
                return EMPTY_COLLECTION
            with _member(archive, "stops.txt") as handle:
                return _stations(_rows(handle), service, parents_only)
    except (zipfile.BadZipFile, OSError):
        logger.warning("No se han podido leer las estaciones de %s", service, exc_info=True)
        return EMPTY_COLLECTION


def _stations(rows: Any, service: str, parents_only: bool) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    seen: set[tuple[float, float, str]] = set()
    for row in rows:
        if parents_only and (row.get("location_type") or "").strip() != "1":
            continue
        name = _display_name(row.get("stop_name"))
        stop_id = (row.get("stop_id") or "").strip()
        try:
            lat = float(row.get("stop_lat") or "")
            lon = float(row.get("stop_lon") or "")
        except ValueError:
            continue
        if not name or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        key = (round(lon, 5), round(lat, 5), name.casefold())
        if key in seen:
            continue
        seen.add(key)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
                "properties": {"name": name, "service": service, "stopId": stop_id},
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _display_name(value: str | None) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if text.isupper():
        return text.title()
    return text


def _dump(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
