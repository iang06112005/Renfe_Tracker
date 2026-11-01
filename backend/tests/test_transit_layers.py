import json
import zipfile
from pathlib import Path

import pytest

from transit_layers import load_transit_layers


def test_metro_gtfs_builds_lines_and_stations_without_vehicles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive_path = tmp_path / "metro.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "routes.txt",
            "route_id,route_short_name,route_color\nL1,1,ED1C24\nLR,R,FFFFFF\n",
        )
        archive.writestr("trips.txt", "route_id,shape_id\nL1,s1\nLR,s2\n")
        archive.writestr(
            "shapes.txt",
            "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
            "s1,40.40,-3.70,1\n"
            "s1,40.41,-3.69,2\n"
            "s2,40.42,-3.71,1\n"
            "s2,40.43,-3.72,2\n",
        )
        archive.writestr(
            "stops.txt",
            "stop_id,stop_name,stop_lat,stop_lon,location_type\n"
            "est1,SOL,40.416,-3.703,1\n"
            "par1,SOL ANDEN,40.4161,-3.7031,0\n",
        )

    def open_zip(_service: str, _url: str) -> zipfile.ZipFile:
        return zipfile.ZipFile(archive_path)

    monkeypatch.setattr("transit_layers._open_feed_zip", open_zip)
    monkeypatch.setattr("transit_layers.GTFS_CACHE_DIR", tmp_path)
    bodies = load_transit_layers()
    lines = json.loads(bodies["metro-lines"])
    colors = {feature["properties"]["line"]: feature["properties"]["color"] for feature in lines["features"]}
    assert colors["1"] == "#ED1C24"
    assert colors["R"] == "#5C6B73"
    assert all(feature["properties"]["service"] == "metro" for feature in lines["features"])
    assert all(feature["geometry"]["type"] == "LineString" for feature in lines["features"])
    stops = json.loads(bodies["stops-metro"])
    assert [feature["properties"]["name"] for feature in stops["features"]] == ["Sol"]
    assert "Iryo" not in json.dumps(lines)
    assert json.loads(bodies["stops-cercanias"])["features"] == []
