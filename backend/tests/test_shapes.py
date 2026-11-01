import io
import zipfile

from gtfs_shapes import collection_from_zip
from schemas import RouteLineFeature


def test_shapes_become_a_line_colored_by_commercial_line() -> None:
    collection, reason = collection_from_zip(_zip(with_shapes=True), "cercanias")
    assert reason is None
    assert collection is not None
    feature = collection["features"][0]
    RouteLineFeature.model_validate(feature)
    assert feature["geometry"]["type"] == "LineString"
    assert feature["geometry"]["coordinates"] == [[-3.6, 40.5], [-3.7, 40.4], [-3.5, 40.6]]
    assert feature["properties"]["line"] == "C1"
    assert feature["properties"]["color"] == "#75B6E0"
    assert feature["properties"]["service"] == "cercanias"
    assert feature["properties"]["shapeId"] == "10_C1"


def test_padded_gtfs_headers_still_parse() -> None:
    blob = _zip(with_shapes=True, padded=True)
    collection, reason = collection_from_zip(blob, "cercanias")
    assert reason is None
    assert collection is not None
    assert collection["features"][0]["properties"]["line"] == "C4"


def test_feed_without_shapes_is_skipped() -> None:
    collection, reason = collection_from_zip(_zip(with_shapes=False), "ld")
    assert collection is None
    assert reason == "el zip no incluye shapes.txt"


def _zip(*, with_shapes: bool, padded: bool = False) -> bytes:
    buffer = io.BytesIO()
    pad = " " * 6 if padded else ""
    short = "C4" if padded else "C1"
    shape = "40_C4" if padded else "10_C1"
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "routes.txt",
            f"route_id,route_short_name,route_color\n10,{short}{pad},75B6E0{pad}\n",
        )
        archive.writestr(
            "trips.txt",
            f"route_id,trip_id,shape_id{pad}\n10,1003S19799{short},{shape}{pad}\n",
        )
        if with_shapes:
            archive.writestr(
                "shapes.txt",
                "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
                f"{shape},40.4,-3.7,2\n"
                f"{shape},40.5,-3.6,1\n"
                f"{shape},40.6,-3.5,3\n"
                f"{shape},999,-3.5,4\n",
            )
    return buffer.getvalue()
