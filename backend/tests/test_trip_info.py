import zipfile
from pathlib import Path

import pytest

from trip_info import Call, describe_train, ensure_trip_index, lookup


def test_incoming_train_gets_real_neighbors_and_timetable() -> None:
    calls = [
        ("A", Call("El Cáñamo", "11:48:00", "11:49:00")),
        ("B", Call("Brenes", "11:55:00", "11:56:00")),
        ("C", Call("Cantillana", "12:00:00", "12:00:00")),
    ]
    fields = describe_train(
        line="C1",
        product="C1",
        route_long="Lebrija                                 -Lora del Rio",
        status="INCOMING_AT",
        stop_id="B",
        calls=calls,
    )
    assert "product" not in fields
    assert fields["route"] == "El Cáñamo – Cantillana"
    assert fields["previousStop"] == "El Cáñamo"
    assert fields["nextStop"] == "Brenes · 11:55"
    assert "currentStop" not in fields


def test_stopped_train_uses_the_current_stop() -> None:
    calls = [
        ("A", Call("San Bernardo", "11:27:00", "11:28:00")),
        ("B", Call("Sevilla-Santa Justa", "11:32:00", "11:34:00")),
    ]
    fields = describe_train(line="C1", product=None, route_long=None, status="STOPPED_AT", stop_id="B", calls=calls)
    assert fields["currentStop"] == "Sevilla-Santa Justa · 11:34"
    assert fields["previousStop"] == "San Bernardo"
    assert "nextStop" not in fields


def test_unknown_stop_does_not_invent_neighbors() -> None:
    calls = [("A", Call("Utrera", "10:58:00", "10:58:00"))]
    fields = describe_train(line="C1", product="AVE", route_long=None, status="IN_TRANSIT_TO", stop_id="missing", calls=calls)
    assert fields == {"product": "AVE"}
    assert "nextStop" not in fields
    assert "previousStop" not in fields


def test_missing_name_is_omitted() -> None:
    calls = [("A", Call(None, "11:55:00", "11:56:00"))]
    fields = describe_train(line=None, product=None, route_long=None, status="INCOMING_AT", stop_id="A", calls=calls)
    assert fields == {}


def test_sqlite_index_resolves_a_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "cercanias.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name\nA,El Cáñamo\nB,Brenes\n",
        )
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name\n1,C1,Lebrija - Lora del Rio\n",
        )
        archive.writestr(
            "trips.txt",
            "route_id,trip_id\n1,3004D23533C1\n",
        )
        archive.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "3004D23533C1,11:48:00,11:49:00,A,1\n"
            "3004D23533C1,11:55:00,11:56:00,B,2\n",
        )
        archive.writestr("stop_times_unused.txt", "nope")
    monkeypatch.setattr("trip_info.INDEX_PATH", tmp_path / "trip-index.sqlite")
    monkeypatch.setattr("trip_info.GTFS_CACHE_DIR", tmp_path)
    monkeypatch.setattr("gtfs_shapes.GTFS_FEEDS", {"cercanias": "unused"})
    ensure_trip_index()
    fields = lookup("cercanias", "3004D23533C1", "B", "INCOMING_AT", "C1")
    assert fields["previousStop"] == "El Cáñamo"
    assert fields["nextStop"] == "Brenes · 11:55"
    assert "product" not in fields


def test_hours_past_midnight_stay_on_the_clock() -> None:
    calls = [("A", Call("Lora del Río", "25:10:00", "25:12:00"))]
    fields = describe_train(line="C1", product=None, route_long=None, status="IN_TRANSIT_TO", stop_id="A", calls=calls)
    assert fields["nextStop"] == "Lora del Río · 01:10"
