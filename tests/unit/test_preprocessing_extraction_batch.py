import pytest

from src.preprocessing.extraction_batch import (
    OutputPairState,
    build_extraction_manifest,
    classify_output_pair,
    output_keys,
    recovery_checkpoint_matches,
    validate_selected_scenes,
)


def _scene(index: int, epoch: int = 2018) -> dict:
    identifier = f"S2A_MSIL2A_{epoch}0101T000000_N0500_R000_T44QQE_{epoch}0101T000000_{index}"
    return {
        "scene_id": identifier,
        "epoch": epoch,
        "object_key": f"vizag-geoai/data/raw/sentinel2/{epoch}/{identifier}.SAFE.zip",
    }


def test_output_keys_use_isolated_versioned_prefix():
    keys = output_keys(
        "vizag-geoai/v2/processed/", _scene(1), contract_version="3.3.2"
    )
    assert keys.reflectance.endswith("_reflectance.tif")
    assert keys.scl.endswith("_scl.tif")
    assert "/2018/" in keys.reflectance
    assert "/contract-3.3.2/" in keys.reflectance


@pytest.mark.parametrize(
    ("reflectance", "scl", "expected"),
    [
        (False, False, OutputPairState.ABSENT),
        (True, True, OutputPairState.COMPLETE),
        (True, False, OutputPairState.PARTIAL),
        (False, True, OutputPairState.PARTIAL),
    ],
)
def test_output_pair_classification(reflectance, scl, expected):
    assert classify_output_pair(
        reflectance_exists=reflectance, scl_exists=scl
    ) is expected


def test_validate_selected_scenes_accepts_exact_approved_shape():
    scenes = [
        _scene(index, epoch)
        for epoch in (2018, 2020, 2022, 2024)
        for index in range(8)
    ]
    validate_selected_scenes(scenes)


def test_validate_selected_scenes_rejects_duplicate_source():
    scenes = [
        _scene(index, epoch)
        for epoch in (2018, 2020, 2022, 2024)
        for index in range(8)
    ]
    scenes[-1]["object_key"] = scenes[0]["object_key"]
    with pytest.raises(ValueError, match="duplicate source object key"):
        validate_selected_scenes(scenes)


def test_validate_selected_scenes_rejects_wrong_epoch_distribution():
    scenes = [_scene(index, 2018) for index in range(32)]
    with pytest.raises(ValueError, match="epoch counts"):
        validate_selected_scenes(scenes)


def _result(scene_id: str, epoch: int) -> dict:
    return {
        "scene_id": scene_id,
        "epoch": epoch,
        "remote_reopen_validated": True,
        "outputs": {
            "reflectance": {"bytes": 10, "sha256": "a" * 64},
            "scl": {"bytes": 5, "sha256": "b" * 64},
        },
    }


def test_build_extraction_manifest_is_deterministic_and_sorted():
    body = build_extraction_manifest(
        [_result("scene-b", 2024), _result("scene-a", 2018)], expected_count=2
    )
    lines = body.decode().splitlines()
    assert '"scene_id":"scene-a"' in lines[0]
    assert '"scene_id":"scene-b"' in lines[1]
    assert body.endswith(b"\n")


def test_build_extraction_manifest_rejects_incomplete_identity():
    result = _result("scene-a", 2018)
    result["outputs"]["scl"].pop("sha256")
    with pytest.raises(ValueError, match="output identity is incomplete"):
        build_extraction_manifest([result], expected_count=1)


def test_recovery_checkpoint_requires_exact_current_object_identities():
    checkpoint = {
        **_result("scene-a", 2018),
        "contract_version": "3.3.2",
        "source_key": "raw/scene-a.SAFE.zip",
        "source_identity": {"size_bytes": 100, "etag": "source-etag"},
    }
    expected_outputs = {
        "reflectance": {"key": None, "bytes": 10},
        "scl": {"key": None, "bytes": 5},
    }
    assert recovery_checkpoint_matches(
        checkpoint,
        scene_id="scene-a",
        contract_version="3.3.2",
        source_key="raw/scene-a.SAFE.zip",
        source_size=100,
        source_etag="source-etag",
        outputs=expected_outputs,
    )
    expected_outputs["scl"]["bytes"] = 6
    assert not recovery_checkpoint_matches(
        checkpoint,
        scene_id="scene-a",
        contract_version="3.3.2",
        source_key="raw/scene-a.SAFE.zip",
        source_size=100,
        source_etag="source-etag",
        outputs=expected_outputs,
    )

