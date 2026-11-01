"""Parse Renfe GTFS-RT trip updates and merge them onto live trains."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")
_CLOCK_TAIL = re.compile(r"\s·\s\d{2}:\d{2}$")


@dataclass(frozen=True)
class StopPrediction:
    stop_id: str
    arrival_time: int | None = None
    departure_time: int | None = None
    delay: int | None = None


@dataclass
class TripUpdateInfo:
    trip_id: str
    delay: int | None = None
    stops: dict[str, StopPrediction] = field(default_factory=dict)

    def predicted_clock(self, stop_id: str | None) -> int | None:
        if not stop_id:
            return None
        prediction = self.stops.get(stop_id)
        if prediction is None:
            return None
        if prediction.arrival_time is not None:
            return prediction.arrival_time
        return prediction.departure_time


def parse_trip_updates(payload: object) -> dict[str, TripUpdateInfo]:
    entities = payload.get("entity") if isinstance(payload, dict) else None
    if not isinstance(entities, list):
        return {}
    by_trip: dict[str, TripUpdateInfo] = {}
    for raw in entities:
        parsed = _parse_entity(raw)
        if parsed is not None:
            by_trip[parsed.trip_id] = parsed
    return by_trip


def enrich_with_trip_update(
    fields: dict[str, str],
    *,
    stop_id: str | None,
    status: str | None,
    update: TripUpdateInfo | None,
) -> dict[str, str | int]:
    public: dict[str, str | int] = {key: value for key, value in fields.items() if not key.startswith("_")}
    if update is None:
        return public
    delay_label = format_delay(update.delay)
    if delay_label and update.delay is not None:
        public["delayLabel"] = delay_label
        public["delaySeconds"] = update.delay
    used = False
    roles = (
        ("previousStop", fields.get("_previousStopId")),
        ("currentStop", fields.get("_currentStopId")),
        ("nextStop", fields.get("_nextStopId")),
    )
    for field_name, role_stop_id in roles:
        predicted = update.predicted_clock(role_stop_id)
        if predicted is None and role_stop_id is None and stop_id:
            # Fall back: single STU often matches the vehicle stopId.
            if status == "STOPPED_AT" and field_name == "currentStop":
                predicted = update.predicted_clock(stop_id)
            elif status in {"IN_TRANSIT_TO", "INCOMING_AT"} and field_name == "nextStop":
                predicted = update.predicted_clock(stop_id)
        if predicted is None:
            continue
        name = stop_name_only(public.get(field_name))
        if not name:
            continue
        clock = format_unix_clock(predicted)
        if not clock:
            continue
        public[field_name] = f"{name} · {clock}"
        used = True
    if used:
        public["predictionsLabel"] = "Previsión Renfe"
    return public


def format_delay(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    if seconds == 0:
        return "En hora"
    minutes = max(1, int(round(abs(seconds) / 60)))
    unit = "min"
    if seconds > 0:
        return f"Retraso {minutes} {unit}"
    return f"Adelanto {minutes} {unit}"


def format_unix_clock(timestamp: int) -> str | None:
    if timestamp <= 0:
        return None
    try:
        moment = datetime.fromtimestamp(timestamp, tz=MADRID_TZ)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.strftime("%H:%M")


def stop_name_only(value: str | None) -> str | None:
    if not value:
        return None
    return _CLOCK_TAIL.sub("", value).strip() or None


def _parse_entity(raw: object) -> TripUpdateInfo | None:
    if not isinstance(raw, dict):
        return None
    trip_update = raw.get("tripUpdate")
    if not isinstance(trip_update, dict):
        return None
    trip = trip_update.get("trip")
    if not isinstance(trip, dict):
        return None
    trip_id = trip.get("tripId")
    if not isinstance(trip_id, str) or not trip_id.strip():
        return None
    delay = _optional_int(trip_update.get("delay"))
    stops: dict[str, StopPrediction] = {}
    updates = trip_update.get("stopTimeUpdate")
    if isinstance(updates, list):
        for item in updates:
            prediction = _parse_stop_update(item)
            if prediction is not None:
                stops[prediction.stop_id] = prediction
    return TripUpdateInfo(trip_id=trip_id.strip(), delay=delay, stops=stops)


def _parse_stop_update(raw: object) -> StopPrediction | None:
    if not isinstance(raw, dict):
        return None
    stop_id = raw.get("stopId")
    if not isinstance(stop_id, str) or not stop_id.strip():
        return None
    arrival = raw.get("arrival") if isinstance(raw.get("arrival"), dict) else {}
    departure = raw.get("departure") if isinstance(raw.get("departure"), dict) else {}
    arrival_time = _optional_int(arrival.get("time"))
    departure_time = _optional_int(departure.get("time"))
    delay = _optional_int(arrival.get("delay"))
    if delay is None:
        delay = _optional_int(departure.get("delay"))
    if arrival_time is None and departure_time is None and delay is None:
        return None
    return StopPrediction(
        stop_id=stop_id.strip(),
        arrival_time=arrival_time,
        departure_time=departure_time,
        delay=delay,
    )


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None
