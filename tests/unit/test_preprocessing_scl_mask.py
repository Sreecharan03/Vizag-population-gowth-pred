import numpy as np
import pytest

from src.preprocessing.scl_mask import (
    MaskPolicy,
    build_valid_mask,
    dilate_mask,
    mask_policy_markdown,
)


def _policy(**overrides) -> MaskPolicy:
    values = {
        "valid_classes": [4, 5, 6, 7],
        "invalid_classes": [0, 1, 3, 8, 9, 10, 11],
        "dark_class_2_valid": False,
        "dilate_classes": [3, 8, 9, 10, 11],
        "dilation_radius_pixels": 2,
        "unknown_classes_invalid": True,
    }
    values.update(overrides)
    return MaskPolicy.from_mapping(values)


def test_mask_class_config_changes_valid_pixel_set():
    scl = np.array([[2, 4, 5, 6, 7, 8]], dtype="uint8")
    invalid_dark, _ = build_valid_mask(scl, _policy(dilation_radius_pixels=0))
    valid_dark, _ = build_valid_mask(
        scl, _policy(dark_class_2_valid=True, dilation_radius_pixels=0)
    )
    np.testing.assert_array_equal(invalid_dark, [[False, True, True, True, True, False]])
    assert valid_dark[0, 0]


def test_cloud_shadow_dilation_expands_mask_by_configured_pixels():
    cloud = np.zeros((7, 7), dtype=bool)
    cloud[3, 3] = True
    expanded = dilate_mask(cloud, 2)
    assert int(expanded.sum()) == 13
    assert expanded[1, 3] and expanded[3, 1]
    assert not expanded[1, 1]


def test_mask_combines_scl_reflectance_and_aoi_validity():
    scl = np.full((2, 3), 4, dtype="uint8")
    reflectance_valid = np.array([[True, False, True], [True, True, True]])
    aoi = np.array([[True, True, False], [True, True, False]])
    valid, stats = build_valid_mask(
        scl, _policy(dilation_radius_pixels=0),
        reflectance_valid=reflectance_valid, aoi_mask=aoi,
    )
    np.testing.assert_array_equal(
        valid, [[True, False, False], [True, True, False]]
    )
    assert stats["considered_pixels"] == 4
    assert stats["valid_pixels"] == 3


def test_unknown_class_is_invalid_and_reported():
    valid, stats = build_valid_mask(
        np.array([[4, 255]], dtype="uint8"), _policy(dilation_radius_pixels=0)
    )
    np.testing.assert_array_equal(valid, [[True, False]])
    assert stats["unknown_pixels"] == 1


def test_policy_rejects_gaps_and_overlaps():
    with pytest.raises(ValueError, match="cover"):
        _policy(invalid_classes=[0, 1, 3, 8, 9, 10])
    with pytest.raises(ValueError, match="subset"):
        _policy(dilate_classes=[4])


def test_qc_policy_records_roof_limitation_and_choices():
    report = mask_policy_markdown(_policy())
    assert "Class 2" in report
    assert "2 pixels" in report
    assert "dark or bright roofs" in report
