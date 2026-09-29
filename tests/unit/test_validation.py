import math

import numpy as np
import pytest

from src.utils.validation import (
    ValidationError,
    assert_bounds_within,
    assert_crs,
    assert_no_nan,
    assert_nodata_consistent,
)


# --- assert_crs -----------------------------------------------------------

def test_assert_crs_matching_strings_pass():
    assert_crs("EPSG:32644", "EPSG:32644")


def test_assert_crs_int_and_string_equivalent():
    assert_crs(32644, "EPSG:32644")


def test_assert_crs_case_insensitive():
    assert_crs("epsg:32644", "EPSG:32644")


def test_assert_crs_mismatch_raises():
    with pytest.raises(ValidationError, match="CRS mismatch"):
        assert_crs("EPSG:4326", "EPSG:32644")


def test_assert_crs_none_raises():
    with pytest.raises(ValidationError, match="CRS is None"):
        assert_crs(None, "EPSG:32644")


def test_assert_crs_object_with_to_epsg():
    class FakeCRS:
        def to_epsg(self):
            return 32644

    assert_crs(FakeCRS(), "EPSG:32644")


# --- assert_bounds_within ---------------------------------------------------

def test_assert_bounds_within_passes_when_inside():
    assert_bounds_within((1, 1, 2, 2), (0, 0, 3, 3))


def test_assert_bounds_within_raises_when_outside():
    with pytest.raises(ValidationError, match="not within allowed bounds"):
        assert_bounds_within((-1, 1, 2, 2), (0, 0, 3, 3))


def test_assert_bounds_within_raises_on_inverted_bounds():
    with pytest.raises(ValidationError, match="degenerate/inverted"):
        assert_bounds_within((2, 2, 1, 1), (0, 0, 3, 3))


def test_assert_bounds_within_raises_on_wrong_length():
    with pytest.raises(ValidationError, match="minx, miny, maxx, maxy"):
        assert_bounds_within((1, 1, 2), (0, 0, 3, 3))


# --- assert_no_nan -----------------------------------------------------------

def test_assert_no_nan_passes_on_clean_array():
    assert_no_nan(np.array([1.0, 2.0, 3.0]))


def test_assert_no_nan_raises_on_nan():
    with pytest.raises(ValidationError, match="1 NaN value"):
        assert_no_nan(np.array([1.0, math.nan, 3.0]))


def test_assert_no_nan_raises_on_empty():
    with pytest.raises(ValidationError, match="empty"):
        assert_no_nan(np.array([]))


# --- assert_nodata_consistent -------------------------------------------------

def test_assert_nodata_consistent_passes_when_aligned():
    array = np.array([1.0, math.nan, 3.0])
    mask = np.array([False, True, False])
    assert_nodata_consistent(array, mask)


def test_assert_nodata_consistent_raises_when_flagged_pixel_not_nan():
    array = np.array([1.0, 0.0, 3.0])  # index 1 flagged nodata but holds 0.0, not NaN
    mask = np.array([False, True, False])
    with pytest.raises(ValidationError, match="flagged nodata but not set"):
        assert_nodata_consistent(array, mask)


def test_assert_nodata_consistent_raises_when_valid_pixel_is_sentinel():
    array = np.array([1.0, math.nan, 3.0])  # index 1 holds NaN but isn't flagged nodata
    mask = np.array([False, False, False])
    with pytest.raises(ValidationError, match="unexpectedly hold the nodata sentinel"):
        assert_nodata_consistent(array, mask)


def test_assert_nodata_consistent_with_non_nan_sentinel_value():
    array = np.array([1.0, -9999.0, 3.0])
    mask = np.array([False, True, False])
    assert_nodata_consistent(array, mask, nodata_value=-9999.0)


def test_assert_nodata_consistent_raises_on_shape_mismatch():
    with pytest.raises(ValidationError, match="shape"):
        assert_nodata_consistent(np.array([1.0, 2.0]), np.array([True, False, False]))
