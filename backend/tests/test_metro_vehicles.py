from pathlib import Path

from metro_vehicles import estimate_vehicles, load_metro_topology, normalize_name


def test_normalize_name_strips_accents() -> None:
    assert normalize_name("Ópera") == "OPERA"
    assert normalize_name("Avenida de América") == "AVENIDA DE AMERICA"


def test_estimate_vehicles_places_train_before_arrival_stop() -> None:
    topology = load_metro_topology(Path("data/gtfs/metro.zip"))
    # Pick a real stop on line 1 from the topology.
    sequence = topology.sequences[("1", "0")]
    stop_id = sequence.stop_ids[5]
    previous_id = sequence.stop_ids[4]
    stop = topology.stops[stop_id]
    previous = topology.stops[previous_id]
    payload = {
        "Vtelindicadores": [
            {
                "linea": 1,
                "nombreest": stop.name,
                "anden": 1,
                "sentido": sequence.headsign,
                "proximo": 1,
                "siguiente": None,
                "fechaHoraEmisionPrevision": "2026-11-01T15:00:00.000+01:00",
            }
        ]
    }
    features = estimate_vehicles(payload, topology).features
    assert len(features) == 1
    feature = features[0]
    assert feature.properties.service == "metro"
    assert feature.properties.line == "1"
    assert feature.properties.groupColor
    lon, lat = feature.geometry.coordinates
    assert min(previous.lon, stop.lon) - 0.01 <= lon <= max(previous.lon, stop.lon) + 0.01
    assert min(previous.lat, stop.lat) - 0.01 <= lat <= max(previous.lat, stop.lat) + 0.01


def test_estimate_vehicles_skips_unknown_line() -> None:
    topology = load_metro_topology(Path("data/gtfs/metro.zip"))
    payload = {
        "Vtelindicadores": [
            {
                "linea": 51,
                "nombreest": "Sol",
                "anden": 1,
                "sentido": "Algo",
                "proximo": 1,
                "siguiente": None,
            }
        ]
    }
    assert estimate_vehicles(payload, topology).features == []
