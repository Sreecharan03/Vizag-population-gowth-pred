import numpy as np
import pytest

from src.preprocessing.nodata import compare_dn_zero_to_scl_zero


def test_identical_nodata_masks_have_zero_mismatch():
    dn = np.array([[0, 100], [200, 0]], dtype="uint16")
    scl = np.array([[0, 4], [5, 0]], dtype="uint8")
    inside = np.ones((2, 2), dtype=bool)
    result = compare_dn_zero_to_scl_zero(dn, scl, inside)
    assert result["both_zero_pixels"] == 2
    assert result["mismatch_pixels"] == 0


def test_boundary_exterior_is_excluded_from_measurement():
    dn = np.array([[0, 100], [0, 100]], dtype="uint16")
    scl = np.array([[4, 4], [0, 4]], dtype="uint8")
    inside = np.array([[False, True], [True, True]])
    result = compare_dn_zero_to_scl_zero(dn, scl, inside)
    assert result["inside_pixels"] == 3
    assert result["both_zero_pixels"] == 1
    assert result["mismatch_pixels"] == 0


def test_mismatch_directions_are_reported_separately():
    dn = np.array([[0, 1]], dtype="uint16")
    scl = np.array([[4, 0]], dtype="uint8")
    result = compare_dn_zero_to_scl_zero(dn, scl, np.ones((1, 2), dtype=bool))
    assert result["dn_zero_scl_valid_pixels"] == 1
    assert result["scl_zero_dn_nonzero_pixels"] == 1
    assert result["mismatch_fraction_of_union"] == 1.0


def test_shape_mismatch_fails():
    with pytest.raises(ValueError, match="identical shapes"):
        compare_dn_zero_to_scl_zero(
            np.zeros((2, 2)), np.zeros((2, 3)), np.ones((2, 2), dtype=bool)
        )

