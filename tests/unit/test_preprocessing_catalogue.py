import json

from src.preprocessing.catalogue import (
    assess_epoch_feasibility,
    build_scene_catalogue,
    catalogue_jsonl,
    generate_feasibility_report,
    load_inventory_jsonl,
)


def _item(product_id: str, *, statuses=None, size_bytes=1000):
    return {
        "key": f"raw/{product_id}.SAFE.zip",
        "size_bytes": size_bytes,
        "source": "sentinel2",
        "format": "zip",
        "statuses": statuses or [],
    }


def test_catalogue_parses_tile_date_baseline_level_format():
    product = "S2A_MSIL2A_20180103T045201_N0500_R076_T44QQE_20230717T103013"
    scenes = build_scene_catalogue([_item(product)], required_tiles=["T44QQE"])
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene.tile == "T44QQE"
    assert scene.sensing_date == "20180103T045201"
    assert scene.processing_baseline == "N0500"
    assert scene.level == "L2A"
    assert scene.format == "zip"
    assert scene.epoch == 2018
    assert scene.covers_required_tile is True


def test_epoch_feasibility_flags_l1c_only_epoch_and_halts():
    product = "S2A_MSIL1C_20200103T045201_N0208_R076_T44QQE_20200103T070000"
    scenes = build_scene_catalogue([_item(product)], required_tiles=["T44QQE"])
    summary = assess_epoch_feasibility(scenes, epochs=[2020], required_tiles=["T44QQE"])[0]
    assert summary["feasible"] is False
    assert "l1c_only_epoch" in summary["issues"]
    assert "no_complete_l2a_candidates" in summary["issues"]


def test_missing_required_tile_coverage_halts():
    product = "S2A_MSIL2A_20220103T045201_N0400_R076_T44QPE_20220103T070000"
    scenes = build_scene_catalogue([_item(product)], required_tiles=["T44QQE"])
    summary = assess_epoch_feasibility(scenes, epochs=[2022], required_tiles=["T44QQE"])[0]
    assert summary["feasible"] is False
    assert summary["missing_required_tiles"] == ["T44QQE"]


def test_duplicate_same_acquisition_prefers_latest_complete_baseline():
    old = "S2A_MSIL2A_20220103T045201_N0400_R076_T44QQE_20220103T070000"
    new = "S2A_MSIL2A_20220103T045201_N0511_R076_T44QQE_20240103T070000"
    scenes = build_scene_catalogue([_item(old), _item(new)], required_tiles=["T44QQE"])
    assert all(scene.duplicate for scene in scenes)
    preferred = [scene for scene in scenes if scene.preferred]
    assert len(preferred) == 1
    assert preferred[0].processing_baseline == "N0511"


def test_complete_product_is_preferred_over_newer_incomplete_duplicate():
    complete = "S2A_MSIL2A_20220103T045201_N0400_R076_T44QQE_20220103T070000"
    incomplete = "S2A_MSIL2A_20220103T045201_N0511_R076_T44QQE_20240103T070000"
    scenes = build_scene_catalogue(
        [_item(complete), _item(incomplete, statuses=["INCOMPLETE"])],
        required_tiles=["T44QQE"],
    )
    assert next(scene for scene in scenes if scene.preferred).product_id == complete


def test_non_raw_inventory_objects_are_excluded():
    item = _item("S2A_MSIL2A_20220103T045201_N0400_R076_T44QQE_20220103T070000")
    item["format"] = "processed_derivative"
    assert build_scene_catalogue([item], required_tiles=["T44QQE"]) == []


def test_jsonl_loader_and_serializer_round_trip():
    product = "S2B_MSIL2A_20240301T045201_N0511_R076_T44QQE_20240301T070000"
    inventory_text = json.dumps(_item(product)) + "\n"
    inventory = load_inventory_jsonl(inventory_text)
    scenes = build_scene_catalogue(inventory, required_tiles=["T44QQE"])
    output = catalogue_jsonl(scenes)
    assert json.loads(output)["product_id"] == product


def test_report_contains_epoch_counts_baselines_and_decision():
    product = "S2B_MSIL2A_20240301T045201_N0511_R076_T44QQE_20240301T070000"
    scenes = build_scene_catalogue([_item(product)], required_tiles=["T44QQE"])
    summaries = assess_epoch_feasibility(scenes, epochs=[2024], required_tiles=["T44QQE"])
    report = generate_feasibility_report(summaries)
    assert "2024 — FEASIBLE" in report
    assert "L2A / L1C: 1 / 0" in report
    assert "N0511" in report
    assert "User confirmation is still required" in report
