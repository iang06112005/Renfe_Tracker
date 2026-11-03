import logging
import math
import re

from pydantic import ValidationError

from schemas import (
    FeatureCollection,
    GtfsEntity,
    GtfsPosition,
    PointGeometry,
    ServiceKind,
    TrainFeature,
    TrainProperties,
)

logger = logging.getLogger("renfe_tracker.parser")
PLATFORM_RE = re.compile(r"PLATF\.\((\w+)\)")
LINE_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def extract_platform(label: str | None) -> str | None:
    if not label:
        return None
    match = PLATFORM_RE.search(label)
    return match.group(1) if match else None


def extract_line(label: str | None, entity_id: str | None = None) -> str | None:
    from_label = _line_token(label)
    if from_label:
        return from_label
    if not entity_id or not entity_id.startswith("VP_"):
        return None
    return _line_token(entity_id.removeprefix("VP_"))


def parse_feed(payload: object, service: ServiceKind) -> FeatureCollection:
    entities = payload.get("entity") if isinstance(payload, dict) else None
    if not isinstance(entities, list):
        return FeatureCollection(features=[])
    by_id: dict[str, TrainFeature] = {}
    for raw in entities:
        try:
            feature = entity_to_feature(raw, service)
        except Exception:
            logger.debug("entidad GTFS omitida", exc_info=True)
            continue
        if feature is not None:
            by_id[feature.properties.id] = feature
    return FeatureCollection(features=list(by_id.values()))


def entity_to_feature(raw: object, service: ServiceKind) -> TrainFeature | None:
    entity = _read_entity(raw)
    if entity is None or entity.id is None or entity.vehicle is None:
        return None
    position = entity.vehicle.position
    if position is None or not _in_range(position):
        return None
    descriptor = entity.vehicle.vehicle
    label = descriptor.label if descriptor else None
    return TrainFeature(
        geometry=PointGeometry(coordinates=(position.longitude, position.latitude)),
        properties=TrainProperties(
            id=entity.id,
            vehicleId=descriptor.id if descriptor else None,
            label=label,
            line=extract_line(label, entity.id),
            platform=extract_platform(label),
            tripId=entity.vehicle.trip.tripId if entity.vehicle.trip else None,
            stopId=entity.vehicle.stopId,
            status=entity.vehicle.currentStatus,
            timestamp=entity.vehicle.timestamp,
            service=service,
        ),
    )


def _read_entity(raw: object) -> GtfsEntity | None:
    if not isinstance(raw, dict):
        return None
    try:
        return GtfsEntity.model_validate(raw)
    except ValidationError:
        return None


def _line_token(value: str | None) -> str | None:
    if not value:
        return None
    head = re.split(r"[-_]", value.strip(), maxsplit=1)[0]
    match = LINE_RE.fullmatch(head)
    return match.group(0) if match else None


def _in_range(position: GtfsPosition) -> bool:
    return (
        math.isfinite(position.latitude)
        and math.isfinite(position.longitude)
        and -90 <= position.latitude <= 90
        and -180 <= position.longitude <= 180
    )
