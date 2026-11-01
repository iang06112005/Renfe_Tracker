from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ServiceKind = Literal["cercanias", "ld"]
FeedType = Literal["cercanias", "ld", "all"]


def optional_str(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def optional_timestamp(value: object) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
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


class GtfsTrip(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tripId: str | None = None

    @field_validator("tripId", mode="before")
    @classmethod
    def parse_trip(cls, value: object) -> str | None:
        return optional_str(value)


class GtfsVehicleDesc(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    label: str | None = None

    @field_validator("id", "label", mode="before")
    @classmethod
    def parse_text(cls, value: object) -> str | None:
        return optional_str(value)


class GtfsPosition(BaseModel):
    model_config = ConfigDict(extra="ignore")
    latitude: float
    longitude: float

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def parse_coord(cls, value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            raise ValueError("coordenada inválida")
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError("coordenada inválida") from exc


class GtfsVehicle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    trip: GtfsTrip | None = None
    position: GtfsPosition | None = None
    currentStatus: str | None = None
    timestamp: int | None = None
    stopId: str | None = None
    vehicle: GtfsVehicleDesc | None = None

    @field_validator("currentStatus", "stopId", mode="before")
    @classmethod
    def parse_text(cls, value: object) -> str | None:
        return optional_str(value)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: object) -> int | None:
        return optional_timestamp(value)


class GtfsEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str | None = None
    vehicle: GtfsVehicle | None = None

    @field_validator("id", mode="before")
    @classmethod
    def parse_id(cls, value: object) -> str | None:
        return optional_str(value)


class PointGeometry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class TrainProperties(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    vehicleId: str | None = None
    label: str | None = None
    line: str | None = None
    platform: str | None = None
    tripId: str | None = None
    stopId: str | None = None
    status: str | None = None
    timestamp: int | None = None
    service: ServiceKind
    product: str | None = None
    bucket: str | None = None
    bucketLabel: str | None = None
    bucketColor: str | None = None
    nucleus: str | None = None
    nucleusLabel: str | None = None
    nucleusColor: str | None = None
    groupColor: str | None = None
    route: str | None = None
    previousStop: str | None = None
    nextStop: str | None = None
    currentStop: str | None = None


class TrainFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: TrainProperties


class FeatureCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[TrainFeature]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    password: str = Field(min_length=1, max_length=200)


class SessionResponse(BaseModel):
    authenticated: bool


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class LineStringGeometry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]]


class RouteLineProperties(BaseModel):
    model_config = ConfigDict(extra="ignore")
    line: str | None = None
    color: str
    service: ServiceKind
    shapeId: str


class RouteLineFeature(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["Feature"] = "Feature"
    geometry: LineStringGeometry
    properties: RouteLineProperties


class RouteLineCollection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[RouteLineFeature]
