import re
import sqlite3
import threading
import zipfile
from dataclasses import dataclass
from pathlib import Path

from config import GTFS_CACHE_DIR
from schemas import ServiceKind

INDEX_PATH = GTFS_CACHE_DIR / "trip-index-v2.sqlite"
_GENERIC_TOKENS = {"san", "santa", "sant", "el", "la", "los", "las", "les", "l'"}
_BUCKET_LABEL = {
    "alta": "Alta velocidad",
    "media": "Media distancia",
    "larga": "Larga distancia",
    "cercanias": "Cercanías",
    "rodalies": "Rodalies",
}
_BUCKET_COLOR = {
    "alta": "#7b2d8e",
    "media": "#0f9d8a",
    "larga": "#3b6dff",
    "cercanias": "#e10600",
    "rodalies": "#ff7a00",
}
_ALTA = {"AVE", "AVLO", "AVE INT"}
_MEDIA = {"MD", "REGIONAL", "REG.EXP.", "PROXIMDAD", "Intercity", "AVANT", "AVANT EXP"}
_LARGA = {"ALVIA", "EUROMED", "TRENCELTA"}
_NUCLEUS_CITIES = {
    "10": "Madrid",
    "20": "Gijón",
    "30": "Sevilla",
    "31": "Cádiz",
    "32": "Málaga",
    "40": "Valencia",
    "41": "Alicante",
    "45": "Murcia",
    "46": "Ferrol",
    "47": "León",
    "51": "Barcelona",
    "60": "Bilbao",
    "61": "Irún",
    "62": "Santander",
    "70": "Zaragoza",
}
_NUCLEUS_COLORS = {
    "10": "#e10600",
    "20": "#1e8449",
    "30": "#b7950b",
    "31": "#ca6f1e",
    "32": "#0e6655",
    "40": "#5dade2",
    "41": "#a04000",
    "45": "#5d6d7e",
    "46": "#1a5276",
    "47": "#873600",
    "51": "#ff7a00",
    "60": "#148f77",
    "61": "#cd6155",
    "62": "#196f3d",
    "70": "#6e2c00",
}
# Colores publicados en route_color del núcleo 10. C4 es azul y C5 amarillo.
_MADRID_LINE_COLORS = {
    "C1": "#75b6e0",
    "C2": "#00943d",
    "C3": "#952585",
    "C4": "#2c2a86",
    "C4A": "#2c2a86",
    "C4B": "#2c2a86",
    "C5": "#fecb00",
    "C7": "#e5202a",
    "C8": "#868584",
    "C8A": "#868584",
    "C8B": "#868584",
    "C9": "#915419",
    "C10": "#bccf00",
}
_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None
_CONN_MTIME: float | None = None


@dataclass(frozen=True)
class Call:
    name: str | None
    arrival: str | None
    departure: str | None


def describe_train(
    *,
    line: str | None,
    product: str | None,
    route_long: str | None,
    status: str | None,
    stop_id: str | None,
    calls: list[tuple[str, Call]],
) -> dict[str, str]:
    fields: dict[str, str] = {}
    shown_product = product if product and product != line else None
    if shown_product:
        fields["product"] = shown_product
    route = _route_label(route_long, calls)
    if route:
        fields["route"] = route
    if not stop_id or not calls:
        return fields
    index = next((pos for pos, (call_stop, _call) in enumerate(calls) if call_stop == stop_id), None)
    if index is None:
        return fields
    previous = calls[index - 1][1] if index > 0 else None
    current = calls[index][1]
    following = calls[index + 1][1] if index + 1 < len(calls) else None
    if status == "STOPPED_AT":
        _put_stop(fields, "currentStop", current, current.departure or current.arrival)
        if "currentStop" in fields:
            fields["_currentStopId"] = stop_id
        if following is not None:
            _put_stop(fields, "nextStop", following, None)
            if "nextStop" in fields:
                fields["_nextStopId"] = calls[index + 1][0]
        if previous is not None:
            _put_stop(fields, "previousStop", previous, None)
            if "previousStop" in fields:
                fields["_previousStopId"] = calls[index - 1][0]
    elif status in {"IN_TRANSIT_TO", "INCOMING_AT"}:
        _put_stop(fields, "nextStop", current, current.arrival or current.departure)
        if "nextStop" in fields:
            fields["_nextStopId"] = stop_id
        if previous is not None:
            _put_stop(fields, "previousStop", previous, None)
            if "previousStop" in fields:
                fields["_previousStopId"] = calls[index - 1][0]
    return fields


def lookup(service: ServiceKind, trip_id: str | None, stop_id: str | None, status: str | None, line: str | None) -> dict[str, str]:
    if not trip_id and not stop_id:
        return {}
    with _LOCK:
        connection = _connection()
        if connection is None or not trip_id:
            return {}
        trip = connection.execute(
            """
            SELECT t.product, t.route_long, t.nucleus, n.label
            FROM trip t
            LEFT JOIN nucleus n ON n.service = t.service AND n.code = t.nucleus
            WHERE t.service = ? AND t.trip_id = ?
            """,
            (service, trip_id),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT c.stop_id, s.stop_name, c.arrival, c.departure
            FROM call c
            LEFT JOIN stop s ON s.service = c.service AND s.stop_id = c.stop_id
            WHERE c.service = ? AND c.trip_id = ?
            ORDER BY c.seq
            """,
            (service, trip_id),
        ).fetchall()
    calls = [(row[0], Call(row[1], row[2] or None, row[3] or None)) for row in rows]
    fields = describe_train(
        line=line,
        product=trip[0] if trip else None,
        route_long=trip[1] if trip else None,
        status=status,
        stop_id=stop_id,
        calls=calls,
    )
    if trip and trip[2]:
        code = trip[2]
        fields["nucleus"] = code
        label = city_name(code) or (trip[3] or None)
        if label:
            fields["nucleusLabel"] = label
        fields["nucleusColor"] = nucleus_color(code)
        bucket = "rodalies" if code == "51" else "cercanias"
        _put_bucket(fields, bucket)
        if code == "10":
            fields["groupColor"] = madrid_line_color(line) or _BUCKET_COLOR["cercanias"]
        else:
            fields["groupColor"] = nucleus_color(code)
    elif trip and trip[0] and service == "ld":
        bucket = product_bucket(trip[0])
        if bucket:
            _put_bucket(fields, bucket)
            fields["groupColor"] = _BUCKET_COLOR[bucket]
    return fields


def ensure_trip_index() -> None:
    from gtfs_shapes import GTFS_FEEDS

    zips = [(service, GTFS_CACHE_DIR / f"{service}.zip") for service in GTFS_FEEDS]
    present = [path for _service, path in zips if path.is_file()]
    if not present:
        return
    newest = max(path.stat().st_mtime for path in present)
    if INDEX_PATH.is_file() and INDEX_PATH.stat().st_mtime >= newest:
        return
    temporary = INDEX_PATH.with_suffix(".sqlite.building")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.executescript(
            """
            CREATE TABLE trip (
              service TEXT NOT NULL,
              trip_id TEXT NOT NULL,
              product TEXT,
              route_long TEXT,
              nucleus TEXT,
              PRIMARY KEY (service, trip_id)
            );
            CREATE TABLE nucleus (
              service TEXT NOT NULL,
              code TEXT NOT NULL,
              label TEXT NOT NULL,
              color TEXT NOT NULL,
              PRIMARY KEY (service, code)
            );
            CREATE TABLE stop (
              service TEXT NOT NULL,
              stop_id TEXT NOT NULL,
              stop_name TEXT NOT NULL,
              PRIMARY KEY (service, stop_id)
            );
            CREATE TABLE call (
              service TEXT NOT NULL,
              trip_id TEXT NOT NULL,
              seq INTEGER NOT NULL,
              stop_id TEXT NOT NULL,
              arrival TEXT,
              departure TEXT,
              PRIMARY KEY (service, trip_id, seq)
            );
            """
        )
        # Core index first (colors / nuclei / products). stop_times is huge and can
        # OOM a 256–512 MB Fly VM; publish the core DB before attempting calls.
        for service, path in zips:
            if path.is_file():
                _fill_core(connection, service, path)
        connection.commit()
    finally:
        connection.close()
    temporary.replace(INDEX_PATH)
    with _LOCK:
        _close_connection()
    try:
        _append_calls(zips)
    except Exception:
        import logging

        logging.getLogger("renfe_tracker.trip_info").exception(
            "Índice de horarios (stop_times) omitido; colores siguen disponibles"
        )


def _fill_core(connection: sqlite3.Connection, service: ServiceKind, path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "stops.txt" in names:
            _insert_stops(connection, service, archive)
        if "trips.txt" in names and "routes.txt" in names:
            _insert_trips(connection, service, archive)


def _append_calls(zips: list[tuple[ServiceKind, Path]]) -> None:
    """Merge stop_times into a copy of the core index so an OOM cannot wipe colors."""
    import shutil

    if not INDEX_PATH.is_file():
        return
    staging = INDEX_PATH.with_suffix(".sqlite.calls")
    if staging.exists():
        staging.unlink()
    shutil.copy2(INDEX_PATH, staging)
    connection = sqlite3.connect(staging)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        for service, path in zips:
            if not path.is_file():
                continue
            with zipfile.ZipFile(path) as archive:
                if "stop_times.txt" in archive.namelist():
                    _insert_calls(connection, service, archive)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_call_trip ON call (service, trip_id, seq)")
        connection.commit()
    finally:
        connection.close()
    staging.replace(INDEX_PATH)
    with _LOCK:
        _close_connection()


def _fill(connection: sqlite3.Connection, service: ServiceKind, path: Path) -> None:
    _fill_core(connection, service, path)
    with zipfile.ZipFile(path) as archive:
        if "stop_times.txt" in archive.namelist():
            _insert_calls(connection, service, archive)


def _insert_stops(connection: sqlite3.Connection, service: ServiceKind, archive: zipfile.ZipFile) -> None:
    rows = []
    for row in _zip_rows(archive, "stops.txt"):
        stop_id = row.get("stop_id") or ""
        name = _clean(row.get("stop_name"))
        if stop_id and name:
            rows.append((service, stop_id, name))
    connection.executemany("INSERT OR REPLACE INTO stop (service, stop_id, stop_name) VALUES (?, ?, ?)", rows)


def nucleus_label(endpoint_counts: dict[str, int]) -> str:
    if not endpoint_counts:
        return ""
    scores: dict[str, int] = {}
    for name, count in endpoint_counts.items():
        token = _place_token(name)
        if token:
            scores[token] = scores.get(token, 0) + count
    if scores:
        winner = max(scores, key=lambda token: (scores[token], token))
        second = sorted(scores.values(), reverse=True)
        if scores[winner] > (second[1] if len(second) > 1 else 0):
            return winner
    ranked = sorted(endpoint_counts, key=lambda name: (-endpoint_counts[name], len(name), name))
    return ranked[0]


def city_name(code: str) -> str | None:
    return _NUCLEUS_CITIES.get(code)


def nucleus_color(code: str) -> str:
    return _NUCLEUS_COLORS.get(code) or _palette_color(code)


def product_bucket(name: str | None) -> str | None:
    if name in _ALTA:
        return "alta"
    if name in _MEDIA:
        return "media"
    if name in _LARGA:
        return "larga"
    return None


def product_color(name: str) -> str:
    bucket = product_bucket(name)
    if bucket:
        return _BUCKET_COLOR[bucket]
    return _palette_color(name)


def madrid_line_color(line: str | None) -> str | None:
    if not line:
        return None
    return _MADRID_LINE_COLORS.get(line.upper())


def _put_bucket(fields: dict[str, str], bucket: str) -> None:
    fields["bucket"] = bucket
    fields["bucketLabel"] = _BUCKET_LABEL[bucket]
    fields["bucketColor"] = _BUCKET_COLOR[bucket]


def _palette_color(value: str) -> str:
    palette = ("#7fb3d5", "#82e0aa", "#f7dc6f", "#d7bde2", "#aed6f1", "#f5cba7")
    return palette[sum(ord(char) for char in value) % len(palette)]


def _nucleus_code(service: str, route_id: str) -> str | None:
    if service != "cercanias":
        return None
    match = re.match(r"^(\d{2})", route_id)
    return match.group(1) if match else None


def _place_token(name: str) -> str | None:
    head = re.split(r"\s+-\s+|–|\(", name)[0].strip()
    word = re.split(r"[\s\-]", head)[0]
    if word.lower() in _GENERIC_TOKENS:
        parts = head.split()
        if len(parts) >= 2:
            return " ".join(parts[:2])
        return None
    if len(word) < 4:
        return None
    return word


def _route_ends(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [re.sub(r"\s+", " ", part).strip(" -") for part in re.split(r"\s{2,}-", value.strip())]
    return [part for part in parts if part]


def _insert_nuclei(connection: sqlite3.Connection, service: ServiceKind, archive: zipfile.ZipFile) -> None:
    if service != "cercanias":
        return
    counts: dict[str, dict[str, int]] = {}
    for row in _zip_rows(archive, "routes.txt"):
        code = _nucleus_code(service, row.get("route_id") or "")
        if not code:
            continue
        bucket = counts.setdefault(code, {})
        for name in _route_ends(row.get("route_long_name")):
            bucket[name] = bucket.get(name, 0) + 1
    rows = []
    for code, bucket in counts.items():
        label = city_name(code) or nucleus_label(bucket)
        if label:
            rows.append((service, code, label, nucleus_color(code)))
    connection.executemany(
        "INSERT OR REPLACE INTO nucleus (service, code, label, color) VALUES (?, ?, ?, ?)",
        rows,
    )


def _insert_trips(connection: sqlite3.Connection, service: ServiceKind, archive: zipfile.ZipFile) -> None:
    routes: dict[str, tuple[str | None, str | None, str | None]] = {}
    for row in _zip_rows(archive, "routes.txt"):
        route_id = row.get("route_id") or ""
        if route_id:
            routes[route_id] = (
                _clean(row.get("route_short_name")),
                _clean_route(row.get("route_long_name")),
                _nucleus_code(service, route_id),
            )
    _insert_nuclei(connection, service, archive)
    batch: list[tuple[str, str, str | None, str | None, str | None]] = []
    for row in _zip_rows(archive, "trips.txt"):
        trip_id = row.get("trip_id") or ""
        if not trip_id:
            continue
        product, route_long, nucleus = routes.get(row.get("route_id") or "", (None, None, None))
        batch.append((service, trip_id, product, route_long, nucleus))
        if len(batch) >= 5000:
            connection.executemany(
                "INSERT OR REPLACE INTO trip (service, trip_id, product, route_long, nucleus) VALUES (?, ?, ?, ?, ?)",
                batch,
            )
            batch.clear()
    if batch:
        connection.executemany(
            "INSERT OR REPLACE INTO trip (service, trip_id, product, route_long, nucleus) VALUES (?, ?, ?, ?, ?)",
            batch,
        )


def _insert_calls(connection: sqlite3.Connection, service: ServiceKind, archive: zipfile.ZipFile) -> None:
    batch: list[tuple[str, str, int, str, str | None, str | None]] = []
    for row in _zip_rows(archive, "stop_times.txt"):
        trip_id = row.get("trip_id") or ""
        stop_id = row.get("stop_id") or ""
        try:
            sequence = int(row.get("stop_sequence") or "")
        except ValueError:
            continue
        if not trip_id or not stop_id:
            continue
        batch.append((service, trip_id, sequence, stop_id, row.get("arrival_time") or None, row.get("departure_time") or None))
        if len(batch) >= 5000:
            connection.executemany(
                "INSERT OR REPLACE INTO call (service, trip_id, seq, stop_id, arrival, departure) VALUES (?, ?, ?, ?, ?, ?)",
                batch,
            )
            batch.clear()
    if batch:
        connection.executemany(
            "INSERT OR REPLACE INTO call (service, trip_id, seq, stop_id, arrival, departure) VALUES (?, ?, ?, ?, ?, ?)",
            batch,
        )


def _zip_rows(archive: zipfile.ZipFile, name: str):
    from gtfs_shapes import _member, _rows

    with _member(archive, name) as handle:
        yield from _rows(handle)


def _connection() -> sqlite3.Connection | None:
    global _CONN, _CONN_MTIME
    if not INDEX_PATH.is_file():
        _close_connection()
        return None
    mtime = INDEX_PATH.stat().st_mtime
    if _CONN is None or _CONN_MTIME != mtime:
        _close_connection()
        _CONN = sqlite3.connect(INDEX_PATH, check_same_thread=False)
        _CONN_MTIME = mtime
    return _CONN


def _close_connection() -> None:
    global _CONN, _CONN_MTIME
    if _CONN is not None:
        _CONN.close()
    _CONN = None
    _CONN_MTIME = None


def _put_stop(fields: dict[str, str], key: str, call: Call, clock_value: str | None) -> None:
    name = _stop_label(call.name)
    if not name:
        return
    clock = _clock(clock_value)
    fields[key] = f"{name} · {clock}" if clock else name


def _route_label(route_long: str | None, calls: list[tuple[str, Call]]) -> str | None:
    names = [label for _stop, call in calls if (label := _stop_label(call.name))]
    if len(names) >= 2 and names[0] != names[-1]:
        return f"{names[0]} – {names[-1]}"
    return _clean_route(route_long)


def _clock(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    match = re.fullmatch(r"(\d{1,2}):([0-5]\d)(?::([0-5]\d))?", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    # GTFS may use 24–47 for times after midnight; anything beyond that is junk.
    if hour > 47:
        return None
    return f"{hour % 24:02d}:{minute:02d}"


def _stop_label(value: str | None) -> str | None:
    text = _clean(value)
    if not text or len(text) < 2:
        return None
    # Prefer omitting fragments that look truncated or unfinished.
    if text.endswith((" -", " –", "/", "-")):
        return None
    if re.search(r"\s[A-Za-zÁÉÍÓÚÜáéíóúü]$", text):
        return None
    if re.fullmatch(r"[A-Za-zÁÉÍÓÚÜáéíóúü]{1,3}", text) and text.lower() in _GENERIC_TOKENS:
        return None
    return text


def _clean(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def _clean_route(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s{2,}-\s*", " – ", value)
    text = re.sub(r"\s+", " ", text).strip(" –")
    return text or None
