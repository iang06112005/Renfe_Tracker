import math

from parser import PLATFORM_RE, entity_to_feature, extract_line, extract_platform, parse_feed


def test_platform_regex_matches_the_spec() -> None:
    assert PLATFORM_RE.pattern == r"PLATF\.\((\w+)\)"
    assert extract_platform("C1-23514-PLATF.(2)") == "2"
    assert extract_platform("C4-23637-PLATF.(12)") == "12"
    assert extract_platform("C3-23107") is None
    assert extract_platform(None) is None


def test_commercial_line_from_label_and_id() -> None:
    assert extract_line("C1-23514-PLATF.(2)") == "C1"
    assert extract_line("C5a-70577-PLATF.(4)") == "C5a"
    assert extract_line("R2S-25541") == "R2S"
    assert extract_line("RL4-15626") == "RL4"
    assert extract_line("15013") is None
    assert extract_line(None, "VP_C4-23637") == "C4"
    assert extract_line(None, "VP_C1_23514") == "C1"
    assert extract_line("08744", "VP_08744") is None


def test_spec_example_becomes_geojson_point() -> None:
    collection = parse_feed({"entity": [_spec_entity()]}, "cercanias")
    feature = collection.features[0]
    dumped = collection.model_dump(mode="json")
    assert feature.geometry.coordinates == (-3.6908, 40.4067)
    assert dumped["features"][0]["geometry"]["coordinates"] == [-3.6908, 40.4067]
    assert feature.properties.line == "C1"
    assert feature.properties.platform == "2"
    assert feature.properties.vehicleId == "23514"
    assert feature.properties.tripId == "23514..."
    assert feature.properties.stopId == "18000"
    assert feature.properties.status == "IN_TRANSIT_TO"
    assert feature.properties.timestamp == 1730372000
    assert feature.properties.service == "cercanias"
    assert dumped["type"] == "FeatureCollection"
    assert dumped["features"][0]["properties"]["vehicleId"] == "23514"


def test_missing_fields_do_not_drop_the_feed() -> None:
    payload = {
        "entity": [
            {"id": "no-vehicle"},
            {"id": "no-position", "vehicle": {"vehicle": {"label": "C2-1-PLATF.(3)"}}},
            {"id": "bad-row"},
            "not-a-dict",
            None,
            {"vehicle": {"position": {"latitude": 40.0, "longitude": -3.0}}},
            {
                "id": "partial",
                "vehicle": {
                    "position": {"latitude": "41.1", "longitude": "-3.2"},
                    "timestamp": "not-a-time",
                    "stopId": None,
                },
            },
            {
                "id": "numeric-stop",
                "vehicle": {
                    "position": {"latitude": 40.5, "longitude": -3.5},
                    "stopId": 18000,
                    "timestamp": "1730372000",
                    "vehicle": {"label": "C3-23107"},
                },
            },
            {
                "id": "out-of-range",
                "vehicle": {"position": {"latitude": 91, "longitude": 0}},
            },
            {
                "id": "bad-coord",
                "vehicle": {"position": {"latitude": True, "longitude": 1}},
            },
            {
                "id": "nan",
                "vehicle": {"position": {"latitude": float("nan"), "longitude": 0}},
            },
            {
                "id": "VP_C4-23637",
                "vehicle": {"position": {"latitude": "37.36", "longitude": "-5.97"}},
            },
        ]
    }
    features = {item.properties.id: item for item in parse_feed(payload, "cercanias").features}
    assert set(features) == {"partial", "numeric-stop", "VP_C4-23637"}
    partial = features["partial"].properties
    assert partial.line is None
    assert partial.platform is None
    assert partial.stopId is None
    assert partial.timestamp is None
    assert partial.label is None
    assert features["numeric-stop"].properties.line == "C3"
    assert features["numeric-stop"].properties.platform is None
    assert features["numeric-stop"].properties.stopId == "18000"
    assert features["numeric-stop"].properties.timestamp == 1730372000
    assert features["VP_C4-23637"].properties.line == "C4"
    assert math.isfinite(features["partial"].geometry.coordinates[0])


def test_long_distance_numeric_label_has_no_invented_line() -> None:
    collection = parse_feed(
        {
            "entity": [
                {
                    "id": "VP_15013",
                    "vehicle": {
                        "trip": {"tripId": "1501312026-10-30"},
                        "position": {"latitude": 41.402187, "longitude": 2.182278},
                        "currentStatus": "STOPPED_AT",
                        "vehicle": {"id": "15013", "label": "15013"},
                    },
                }
            ]
        },
        "ld",
    )
    props = collection.features[0].properties
    assert props.line is None
    assert props.platform is None
    assert props.stopId is None
    assert props.timestamp is None
    assert props.service == "ld"
    assert props.vehicleId == "15013"


def test_duplicate_id_keeps_the_latest_position() -> None:
    first = _spec_entity()
    second = _spec_entity()
    second["vehicle"]["position"] = {"latitude": 41.0, "longitude": 2.0}
    collection = parse_feed({"entity": [first, second]}, "cercanias")
    assert len(collection.features) == 1
    assert collection.features[0].geometry.coordinates == (2.0, 41.0)


def test_empty_or_invalid_payload() -> None:
    assert parse_feed({}, "ld").features == []
    assert parse_feed({"entity": None}, "cercanias").features == []
    assert parse_feed([], "ld").features == []
    assert entity_to_feature("nope", "ld") is None


def _spec_entity() -> dict[str, object]:
    return {
        "id": "VP_C1_23514",
        "vehicle": {
            "trip": {"tripId": "23514..."},
            "position": {"latitude": 40.4067, "longitude": -3.6908},
            "currentStatus": "IN_TRANSIT_TO",
            "timestamp": 1730372000,
            "stopId": "18000",
            "vehicle": {"id": "23514", "label": "C1-23514-PLATF.(2)"},
            "occupancyStatus": "MANY_SEATS_AVAILABLE",
        },
    }
