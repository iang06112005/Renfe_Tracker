"""Estimate Metro Madrid vehicles from public teleindicador arrival times."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import math
import re
import time
import unicodedata
import zipfile
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from config import GTFS_CACHE_DIR, HTTP_TIMEOUT_SECONDS, USER_AGENT
from schemas import FeatureCollection, PointGeometry, TrainFeature, TrainProperties

logger = logging.getLogger("renfe_tracker.metro")

METRO_TELEINDICADORES_URL = "https://serviciosapp.metromadrid.es/servicios/rest/teleindicadores"
METRO_CACHE_TTL_SECONDS = 20.0
DEFAULT_SEGMENT_SECONDS = 90.0
MAX_ETA_SECONDS = 210.0
MADRID_TZ = ZoneInfo("Europe/Madrid")
LINE_ALIASES = {0: "R", 51: None}


@dataclass(frozen=True)
class StopInfo:
    stop_id: str
    name: str
    lon: float
    lat: float


@dataclass(frozen=True)
class LineSequence:
    line: str
    direction: str
    headsign: str
    stop_ids: tuple[str, ...]
    segment_seconds: tuple[float, ...]


@dataclass
class MetroTopology:
    stops: dict[str, StopInfo]
    by_name: dict[str, list[str]]
    sequences: dict[tuple[str, str], LineSequence]
    colors: dict[str, str]
    lines_by_stop: dict[str, set[str]]


class MetroUnavailable(Exception):
    pass


class MetroVehicleStore:
    def __init__(
        self,
        *,
        ttl_seconds: float = METRO_CACHE_TTL_SECONDS,
        client: httpx.AsyncClient | None = None,
        clock: Callable[[], float] | None = None,
        topology: MetroTopology | None = None,
    ) -> None:
        self._ttl = ttl_seconds
        self._client = client
        self._owns_client = client is None
        self._clock = clock or time.monotonic
        self._topology = topology
        self._cache: FeatureCollection | None = None
        self._fetched_at: float | None = None
        self._inflight: asyncio.Task[FeatureCollection] | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=5.0),
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                follow_redirects=True,
            )
        if self._topology is None:
            self._topology = await asyncio.to_thread(load_metro_topology)

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def vehicles(self) -> FeatureCollection:
        reserved = await self._reserve()
        if not isinstance(reserved, asyncio.Task):
            return reserved
        try:
            payload = await reserved
        except (httpx.HTTPError, ValueError, OSError) as exc:
            await self._remember(reserved, None)
            if self._cache is not None:
                logger.warning("Teleindicadores de Metro fallaron; se sirve la caché anterior")
                return self._cache
            logger.warning("Teleindicadores de Metro no disponibles: %s", exc)
            raise MetroUnavailable from exc
        await self._remember(reserved, payload)
        return payload

    async def _reserve(self) -> FeatureCollection | asyncio.Task[FeatureCollection]:
        async with self._lock:
            if self._within_ttl() and self._cache is not None:
                return self._cache
            if self._inflight is None:
                self._inflight = asyncio.create_task(self._download())
            return self._inflight

    async def _remember(self, task: asyncio.Task[FeatureCollection], payload: FeatureCollection | None) -> None:
        async with self._lock:
            if self._inflight is task:
                self._inflight = None
            self._fetched_at = self._clock()
            if payload is not None:
                self._cache = payload

    def _within_ttl(self) -> bool:
        return self._fetched_at is not None and self._clock() - self._fetched_at < self._ttl

    async def _download(self) -> FeatureCollection:
        if self._client is None or self._topology is None:
            raise RuntimeError("MetroVehicleStore no está abierto")
        response = await self._client.get(METRO_TELEINDICADORES_URL)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("teleindicadores no es un objeto JSON")
        return estimate_vehicles(payload, self._topology)


def load_metro_topology(path: Any | None = None) -> MetroTopology:
    archive_path = path or (GTFS_CACHE_DIR / "metro.zip")
    if not archive_path.is_file():
        raise FileNotFoundError(f"falta {archive_path}")
    with zipfile.ZipFile(archive_path) as archive:
        stops = _read_stops(archive)
        colors, route_ids = _read_routes(archive)
        trips = _read_trips(archive, route_ids)
        sequences = _read_sequences(archive, trips)
    by_name: dict[str, list[str]] = defaultdict(list)
    lines_by_stop: dict[str, set[str]] = defaultdict(set)
    for stop_id, stop in stops.items():
        by_name[normalize_name(stop.name)].append(stop_id)
    for (line, _direction), sequence in sequences.items():
        for stop_id in sequence.stop_ids:
            lines_by_stop[stop_id].add(line)
    return MetroTopology(
        stops=stops,
        by_name=dict(by_name),
        sequences=sequences,
        colors=colors,
        lines_by_stop=dict(lines_by_stop),
    )


def estimate_vehicles(payload: dict[str, Any], topology: MetroTopology) -> FeatureCollection:
    rows = payload.get("Vtelindicadores")
    if not isinstance(rows, list):
        return FeatureCollection(features=[])
    features: list[TrainFeature] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        feature = _row_to_feature(row, topology)
        if feature is None or feature.properties.id in seen:
            continue
        seen.add(feature.properties.id)
        features.append(feature)
    return FeatureCollection(features=features)


def normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper().replace("Ñ", "N").replace("’", "'").replace("´", "'").replace("`", "'")
    text = text.replace("O'DONNELL", "ODONNELL").replace("O´DONNELL", "ODONNELL")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def _row_to_feature(row: dict[str, Any], topology: MetroTopology) -> TrainFeature | None:
    line = _line_code(row.get("linea"))
    if not line or line not in topology.colors:
        return None
    eta = _eta_minutes(row)
    if eta is None or eta * 60 > MAX_ETA_SECONDS:
        return None
    station_name = str(row.get("nombreest") or "").strip()
    if not station_name:
        return None
    stop_id = _match_stop(station_name, line, topology)
    if stop_id is None:
        return None
    sense = str(row.get("sentido") or "").strip()
    sequence = _pick_sequence(line, sense, stop_id, topology)
    if sequence is None:
        return None
    index = sequence.stop_ids.index(stop_id)
    previous_id = sequence.stop_ids[index - 1] if index > 0 else stop_id
    segment = sequence.segment_seconds[index - 1] if index > 0 else DEFAULT_SEGMENT_SECONDS
    progress = 1.0 if eta <= 0 or index == 0 else max(0.0, min(1.0, 1.0 - (eta * 60.0) / max(segment, 30.0)))
    lon, lat = _lerp_stop(topology.stops[previous_id], topology.stops[stop_id], progress)
    color = topology.colors.get(line, "#5C6B73")
    platform = row.get("anden")
    stop = topology.stops[stop_id]
    previous = topology.stops[previous_id]
    timestamp = _timestamp(row)
    status = "INCOMING_AT" if eta <= 0 else "IN_TRANSIT_TO"
    vehicle_id = f"{line}-{sequence.direction}-{stop_id}-{platform or 0}"
    return TrainFeature(
        geometry=PointGeometry(coordinates=(lon, lat)),
        properties=TrainProperties(
            id=f"metro-{vehicle_id}",
            vehicleId=vehicle_id,
            label=line,
            line=line,
            platform=str(platform) if platform not in (None, "") else None,
            tripId=None,
            stopId=stop_id,
            status=status,
            timestamp=timestamp,
            service="metro",
            product="Metro",
            bucket="metro",
            bucketLabel="Metro Madrid",
            bucketColor=color,
            nucleus=None,
            nucleusLabel=None,
            nucleusColor=None,
            groupColor=color,
            route=f"{previous.name} — {sequence.headsign}" if previous_id != stop_id else sequence.headsign,
            previousStop=None if previous_id == stop_id else _display_stop_name(previous.name),
            nextStop=_next_label(stop.name, eta),
            currentStop=_display_stop_name(stop.name) if eta <= 0 else None,
        ),
    )


def _line_code(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
        if number in LINE_ALIASES:
            return LINE_ALIASES[number]
        return str(number)
    text = str(value).strip().upper()
    if not text:
        return None
    if text == "R":
        return "R"
    if text.isdigit():
        return _line_code(int(text))
    return text


def _eta_minutes(row: dict[str, Any]) -> float | None:
    proximo = row.get("proximo")
    siguiente = row.get("siguiente")
    if proximo is not None and proximo != "":
        try:
            return max(0.0, float(proximo))
        except (TypeError, ValueError):
            return None
    if siguiente is not None and siguiente != "":
        try:
            return max(0.0, float(siguiente))
        except (TypeError, ValueError):
            return None
    return None


def _match_stop(station_name: str, line: str, topology: MetroTopology) -> str | None:
    key = normalize_name(station_name)
    aliases = {
        "ARROYO FRESNO": "ARROYOFRESNO",
        "FUENTE DE LA MORA": "FUENTE DE LA MORA",
        "ODONNELL": "O DONNELL",
        "PARQUE DE LISBOA": "PARQUE DE LISBOA",
        "ALVAREZ DE VILLAAMIL": "ALVAREZ DE VILLAAMIL",
        "MARIA TUDOR": "MARIA TUDOR",
        "BLASCO IBANEZ": "BLASCO IBANEZ",
        "ANTONIO SAURA": "ANTONIO SAURA",
        "PALAS DEL REY": "PALAS DEL REY",
        "VIRGEN DEL CORTIJO": "VIRGEN DEL CORTIJO",
    }
    key = aliases.get(key, key)
    candidates = topology.by_name.get(key) or []
    if not candidates:
        for name, stop_ids in topology.by_name.items():
            if key in name or name in key:
                candidates = stop_ids
                break
    if not candidates:
        return None
    for stop_id in candidates:
        if line in topology.lines_by_stop.get(stop_id, set()):
            return stop_id
    return candidates[0]


def _pick_sequence(line: str, sense: str, stop_id: str, topology: MetroTopology) -> LineSequence | None:
    options = [sequence for (code, _direction), sequence in topology.sequences.items() if code == line and stop_id in sequence.stop_ids]
    if not options:
        return None
    target = normalize_name(sense)
    scored: list[tuple[int, LineSequence]] = []
    for sequence in options:
        head = normalize_name(sequence.headsign)
        score = 0
        if target and (target in head or head in target):
            score += 5
        if target:
            for token in target.split():
                if token in head:
                    score += 1
        scored.append((score, sequence))
    scored.sort(key=lambda item: (-item[0], item[1].direction))
    return scored[0][1]


def _lerp_stop(previous: StopInfo, current: StopInfo, progress: float) -> tuple[float, float]:
    progress = max(0.0, min(1.0, progress))
    return (
        previous.lon + (current.lon - previous.lon) * progress,
        previous.lat + (current.lat - previous.lat) * progress,
    )


def _next_label(name: str, eta: float) -> str | None:
    title = _display_stop_name(name)
    if not title:
        return None
    if eta <= 0:
        return title
    minutes = int(math.ceil(eta))
    if minutes < 0 or minutes > 30:
        return title
    if minutes <= 1:
        return f"{title} · 1 min"
    return f"{title} · {minutes} min"


def _display_stop_name(name: str) -> str | None:
    text = re.sub(r"\s+", " ", name or "").strip()
    if len(text) < 2 or re.search(r"\s[A-Za-zÁÉÍÓÚÜáéíóúü]$", text):
        return None
    return text.title() if text.isupper() else text


def _timestamp(row: dict[str, Any]) -> int | None:
    for key in ("fechaHoraEmisionPrevision", "FECHAHORAEMISIONPREVISION", "fechaHoraRegistro", "FECHAHORAREGISTRO"):
        raw = row.get(key)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            return int(datetime.fromisoformat(raw).timestamp())
        except ValueError:
            continue
    return int(datetime.now(tz=MADRID_TZ).timestamp())


def _read_stops(archive: zipfile.ZipFile) -> dict[str, StopInfo]:
    stops: dict[str, StopInfo] = {}
    with archive.open("stops.txt") as handle:
        for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
            stop_id = row.get("stop_id") or ""
            if not stop_id.startswith("par_4_"):
                continue
            try:
                lat = float(row["stop_lat"])
                lon = float(row["stop_lon"])
            except (KeyError, TypeError, ValueError):
                continue
            stops[stop_id] = StopInfo(stop_id=stop_id, name=(row.get("stop_name") or stop_id).strip(), lon=lon, lat=lat)
    return stops


def _read_routes(archive: zipfile.ZipFile) -> tuple[dict[str, str], dict[str, str]]:
    colors: dict[str, str] = {}
    route_ids: dict[str, str] = {}
    with archive.open("routes.txt") as handle:
        for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
            short = (row.get("route_short_name") or "").strip()
            route_id = row.get("route_id") or ""
            if not short or not route_id:
                continue
            raw = (row.get("route_color") or "").strip().lstrip("#")
            color = f"#{raw}" if len(raw) == 6 else "#5C6B73"
            if color.upper() == "#FFFFFF":
                color = "#5C6B73"
            colors[short] = color
            route_ids[route_id] = short
    return colors, route_ids


def _read_trips(archive: zipfile.ZipFile, route_ids: dict[str, str]) -> dict[str, tuple[str, str, str]]:
    trips: dict[str, tuple[str, str, str]] = {}
    with archive.open("trips.txt") as handle:
        for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
            trip_id = row.get("trip_id") or ""
            route_id = row.get("route_id") or ""
            line = route_ids.get(route_id)
            direction = row.get("direction_id") or "0"
            headsign = (row.get("trip_headsign") or "").strip()
            if trip_id and line:
                trips[trip_id] = (line, direction, headsign)
    return trips


def _read_sequences(
    archive: zipfile.ZipFile,
    trips: dict[str, tuple[str, str, str]],
) -> dict[tuple[str, str], LineSequence]:
    times: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
    with archive.open("stop_times.txt") as handle:
        for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
            trip_id = row.get("trip_id") or ""
            if trip_id not in trips:
                continue
            stop_id = row.get("stop_id") or ""
            if not stop_id.startswith("par_4_"):
                continue
            try:
                sequence = int(row.get("stop_sequence") or "0")
            except ValueError:
                continue
            seconds = _hhmmss(row.get("arrival_time") or row.get("departure_time"))
            times[trip_id].append((sequence, stop_id, seconds))
    best: dict[tuple[str, str], LineSequence] = {}
    for trip_id, calls in times.items():
        line, direction, headsign = trips[trip_id]
        calls = sorted(calls, key=lambda item: item[0])
        stop_ids = tuple(stop_id for _sequence, stop_id, _seconds in calls)
        if len(stop_ids) < 2:
            continue
        segments: list[float] = []
        for index in range(1, len(calls)):
            delta = calls[index][2] - calls[index - 1][2]
            segments.append(float(delta) if delta > 0 else DEFAULT_SEGMENT_SECONDS)
        current = best.get((line, direction))
        if current is None or len(stop_ids) > len(current.stop_ids):
            best[(line, direction)] = LineSequence(
                line=line,
                direction=direction,
                headsign=headsign,
                stop_ids=stop_ids,
                segment_seconds=tuple(segments),
            )
    return best


def _hhmmss(value: str | None) -> int:
    if not value:
        return 0
    parts = value.strip().split(":")
    if len(parts) != 3:
        return 0
    try:
        hours, minutes, seconds = (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return 0
    return hours * 3600 + minutes * 60 + seconds
