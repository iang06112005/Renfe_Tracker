from main import _fallback_group_color
from schemas import TrainProperties


def test_fallback_uses_madrid_line_color_for_cercanias() -> None:
    props = TrainProperties(id="t1", service="cercanias", line="C5")
    extra = _fallback_group_color(props)
    assert extra["groupColor"] == "#fecb00"
    assert extra["bucketLabel"] == "Cercanías"


def test_fallback_marks_ld_bucket_when_product_known() -> None:
    props = TrainProperties(id="t2", service="ld", product="AVE")
    extra = _fallback_group_color(props)
    assert extra["bucket"] == "alta"
    assert extra["groupColor"] == "#7b2d8e"
