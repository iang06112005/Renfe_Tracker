import zipfile
from pathlib import Path

import pytest

from trip_info import (
    Call,
    city_name,
    describe_train,
    ensure_trip_index,
    lookup,
    madrid_line_color,
    nucleus_label,
    product_bucket,
    product_color,
)


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
    assert "nucleus" not in fields


def test_nucleus_label_uses_a_station_the_feed_repeats() -> None:
    assert nucleus_label({"Valencia Nord": 19, "Buñol": 8, "Moixent": 6}) == "Valencia"
    assert nucleus_label({"Barcelona-Fabra i Puig": 10, "Barcelona-Estació de França": 8, "Vic": 10}) == "Barcelona"


def test_cities_replace_the_repeated_station() -> None:
    assert city_name("10") == "Madrid"
    assert city_name("30") == "Sevilla"
    assert city_name("70") == "Zaragoza"
    assert city_name("41") == "Alicante"
    assert city_name("45") == "Murcia"
    assert city_name("32") == "Málaga"
    assert city_name("60") == "Bilbao"
    assert city_name("20") == "Gijón"
    assert city_name("61") == "Irún"
    assert city_name("51") == "Barcelona"
    assert city_name("47") == "León"
    assert city_name("99") is None


def test_products_share_three_tags_and_skip_other_operators() -> None:
    assert product_bucket("AVE") == product_bucket("AVLO") == product_bucket("AVE INT") == "alta"
    assert product_bucket("MD") == product_bucket("AVANT") == product_bucket("REGIONAL") == "media"
    assert product_bucket("REG.EXP.") == product_bucket("PROXIMDAD") == product_bucket("Intercity") == "media"
    assert product_bucket("ALVIA") == product_bucket("EUROMED") == product_bucket("TRENCELTA") == "larga"
    assert product_bucket("Iryo") is None
    assert product_bucket("Ouigo") is None
    assert product_color("AVE") == product_color("AVLO")
    assert product_color("MD") == product_color("AVANT")
    assert product_color("ALVIA") == product_color("EUROMED")
    assert len({product_color("AVE"), product_color("MD"), product_color("ALVIA")}) == 3


def test_madrid_lines_use_their_public_colors() -> None:
    assert madrid_line_color("C4") == madrid_line_color("C4a") == "#2c2a86"
    assert madrid_line_color("C5") == "#fecb00"
    assert madrid_line_color("C2") == "#00943d"
    assert madrid_line_color("C10") == "#bccf00"
    assert madrid_line_color("C1") != madrid_line_color("C5")


def test_index_separates_nucleus_and_long_distance_product(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cercanias = tmp_path / "cercanias.zip"
    with zipfile.ZipFile(cercanias, "w") as archive:
        archive.writestr("stops.txt", "stop_id,stop_name\nA,Chamartín - Clara Campoamor\n")
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name\n"
            "10T0001C1,C1,Chamartín - Clara Campoamor          -Atocha\n"
            "10T0002C1,C2,Atocha                              -Chamartín - Clara Campoamor\n"
            "10T0003C1,C3,Chamartín - Clara Campoamor          -Cercedilla\n"
            "10T0004C1,C4,Cercedilla                          -Chamartín - Clara Campoamor\n",
        )
        archive.writestr("trips.txt", "route_id,trip_id\n10T0001C1,trip-mad\n")
        archive.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\ntrip-mad,08:00:00,08:01:00,A,1\n",
        )
    long_distance = tmp_path / "ld.zip"
    with zipfile.ZipFile(long_distance, "w") as archive:
        archive.writestr("stops.txt", "stop_id,stop_name\nS,Madrid Puerta de Atocha\n")
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name\nAV1,AVE,\nMD1,MD,\nAL1,ALVIA,\nEU1,EUROMED,\n",
        )
        archive.writestr("trips.txt", "route_id,trip_id\nAV1,trip-ave\nMD1,trip-md\n")
        archive.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
            "trip-ave,09:00:00,09:05:00,S,1\n"
            "trip-md,10:00:00,10:04:00,S,1\n",
        )
    monkeypatch.setattr("trip_info.INDEX_PATH", tmp_path / "trip-index-v2.sqlite")
    monkeypatch.setattr("trip_info.GTFS_CACHE_DIR", tmp_path)
    monkeypatch.setattr("gtfs_shapes.GTFS_FEEDS", {"cercanias": "unused", "ld": "unused"})
    ensure_trip_index()

    cercanias_fields = lookup("cercanias", "trip-mad", "A", "STOPPED_AT", "C1")
    assert cercanias_fields["nucleus"] == "10"
    assert cercanias_fields["nucleusLabel"] == "Madrid"
    assert cercanias_fields["bucketLabel"] == "Cercanías"
    assert cercanias_fields["groupColor"] == "#75b6e0"
    assert cercanias_fields["nucleusColor"] == "#e10600"

    ave = lookup("ld", "trip-ave", "S", "STOPPED_AT", None)
    media = lookup("ld", "trip-md", "S", "STOPPED_AT", None)
    assert ave["product"] == "AVE"
    assert ave["bucket"] == "alta"
    assert ave["bucketLabel"] == "Alta velocidad"
    assert media["product"] == "MD"
    assert media["bucket"] == "media"
    assert media["bucketLabel"] == "Media distancia"
    assert "AVE" not in media["bucketLabel"]
    assert ave["groupColor"] == product_color("AVE")
    assert media["groupColor"] == product_color("MD")
    assert ave["groupColor"] != media["groupColor"]
    assert "nucleus" not in ave
    joined = " ".join(ave.values()) + " " + " ".join(media.values())
    assert "Iryo" not in joined
    assert "Ouigo" not in joined


def test_barcelona_is_rodalies_and_not_a_madrid_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "cercanias.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("stops.txt", "stop_id,stop_name\nA,Barcelona-Sants\n")
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_long_name\n51T1,R1,Barcelona-Sants                    -Mataró\n",
        )
        archive.writestr("trips.txt", "route_id,trip_id\n51T1,trip-bcn\n")
        archive.writestr(
            "stop_times.txt",
            "trip_id,arrival_time,departure_time,stop_id,stop_sequence\ntrip-bcn,08:00:00,08:01:00,A,1\n",
        )
    monkeypatch.setattr("trip_info.INDEX_PATH", tmp_path / "trip-index.sqlite")
    monkeypatch.setattr("trip_info.GTFS_CACHE_DIR", tmp_path)
    monkeypatch.setattr("gtfs_shapes.GTFS_FEEDS", {"cercanias": "unused"})
    ensure_trip_index()
    fields = lookup("cercanias", "trip-bcn", "A", "STOPPED_AT", "R1")
    assert fields["nucleusLabel"] == "Barcelona"
    assert fields["bucket"] == "rodalies"
    assert fields["bucketLabel"] == "Rodalies"
    assert fields["groupColor"] == "#ff7a00"
    assert fields["groupColor"] != madrid_line_color("C5")


def test_hours_past_midnight_stay_on_the_clock() -> None:
    calls = [("A", Call("Lora del Río", "25:10:00", "25:12:00"))]
    fields = describe_train(line="C1", product=None, route_long=None, status="IN_TRANSIT_TO", stop_id="A", calls=calls)
    assert fields["nextStop"] == "Lora del Río · 01:10"
