import numpy as np

from src.preprocessing.catalogue import SceneRecord
from src.preprocessing.triage import (
    calculate_scl_metrics,
    cloud_triage_csv,
    in_season,
    selected_scenes_jsonl,
    triage_scenes,
)


def _scene(day: str, product_suffix: str, *, epoch=2024, preferred=True, complete=True):
    product = f"S2A_MSIL2A_{day}T045201_N0510_R076_T44QQE_{day}T070000{product_suffix}"
    return SceneRecord(
        object_key=f"raw/{product}.SAFE.zip", size_bytes=1000, product_id=product,
        mission="S2A", level="L2A", sensing_date=f"{day}T045201", epoch=epoch,
        processing_baseline="N0510", relative_orbit="R076", tile="T44QQE",
        processing_date=f"{day}T070000", format="zip", complete=complete,
        covers_required_tile=True, duplicate=not preferred, preferred=preferred,
    )


def test_scl_metrics_are_scoped_to_aoi_and_mutually_exclusive():
    scl = np.array([[8, 4, 3], [0, 5, 11]], dtype="uint8")
    mask = np.array([[1, 1, 1], [1, 1, 0]], dtype=bool)
    result = calculate_scl_metrics(scl, mask)
    assert result["aoi_pixels"] == 5
    assert result["cloud_fraction"] == 1 / 5
    assert result["shadow_fraction"] == 1 / 5
    assert result["nodata_fraction"] == 1 / 5
    assert result["usable_fraction"] == 2 / 5
    assert result["unusable_fraction"] == 3 / 5


def test_scl_triage_selects_lowest_cloud_scenes_per_epoch():
    scenes = [_scene("20240110", "A"), _scene("20240120", "B"), _scene("20240201", "C")]
    values = {
        scenes[0].product_id: np.array([[8, 8], [4, 4]], dtype="uint8"),
        scenes[1].product_id: np.array([[4, 4], [4, 8]], dtype="uint8"),
        scenes[2].product_id: np.array([[4, 4], [4, 4]], dtype="uint8"),
    }
    records = triage_scenes(
        scenes, read_scl=lambda scene: (values[scene.product_id], np.ones((2, 2), dtype=bool)),
        top_k_per_epoch=2, start_month_day="12-01", end_month_day="03-31",
    )
    selected = [record for record in records if record.selected]
    assert [record.product_id for record in selected] == [scenes[2].product_id, scenes[1].product_id]


def test_triage_reads_only_scl_not_10m_bands():
    calls = []
    scene = _scene("20240110", "A")

    def reader(candidate):
        calls.append((candidate.product_id, "SCL"))
        return np.full((2, 2), 4, dtype="uint8"), np.ones((2, 2), dtype=bool)

    triage_scenes(
        [scene], read_scl=reader, top_k_per_epoch=1,
        start_month_day="12-01", end_month_day="03-31",
    )
    assert calls == [(scene.product_id, "SCL")]


def test_out_of_season_and_nonpreferred_scenes_are_not_read():
    scenes = [_scene("20240415", "A"), _scene("20240110", "B", preferred=False)]
    calls = []
    records = triage_scenes(
        scenes,
        read_scl=lambda scene: calls.append(scene) or (np.ones((1, 1)), np.ones((1, 1), dtype=bool)),
        top_k_per_epoch=8, start_month_day="12-01", end_month_day="03-31",
    )
    assert records == []
    assert calls == []


def test_cross_year_dry_season_window():
    assert in_season("20240110T000000", "12-01", "03-31")
    assert in_season("20231215T000000", "12-01", "03-31")
    assert not in_season("20240401T000000", "12-01", "03-31")


def test_selection_is_deterministic_on_ties():
    scenes = [_scene("20240201", "B"), _scene("20240101", "A")]
    reader = lambda _scene: (np.full((2, 2), 4, dtype="uint8"), np.ones((2, 2), dtype=bool))
    first = triage_scenes(
        scenes, read_scl=reader, top_k_per_epoch=1,
        start_month_day="12-01", end_month_day="03-31",
    )
    second = triage_scenes(
        reversed(scenes), read_scl=reader, top_k_per_epoch=1,
        start_month_day="12-01", end_month_day="03-31",
    )
    assert [r.product_id for r in first if r.selected] == [r.product_id for r in second if r.selected]


def test_outputs_include_only_selected_jsonl_and_all_csv_rows():
    scenes = [_scene("20240101", "A"), _scene("20240201", "B")]
    records = triage_scenes(
        scenes, read_scl=lambda _scene: (np.full((1, 1), 4), np.ones((1, 1), dtype=bool)),
        top_k_per_epoch=1, start_month_day="12-01", end_month_day="03-31",
    )
    assert selected_scenes_jsonl(records).count("\n") == 1
    assert cloud_triage_csv(records).count("\n") == 3
