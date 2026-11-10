import dask.array as da
import numpy as np
import pytest

from src.preprocessing.composite import (
    CoverageGate,
    CoverageInsufficientError,
    assess_coverage,
    chunked_median_composite,
    estimate_chunk_working_bytes,
)


def test_composite_median_correct_on_known_synthetic_stack():
    values = np.array(
        [
            [[[1, 10], [100, 4]]],
            [[[3, 20], [200, 8]]],
            [[[5, 30], [300, 12]]],
        ],
        dtype="float32",
    )
    masks = np.array(
        [
            [[True, True], [False, False]],
            [[True, False], [False, False]],
            [[True, True], [False, False]],
        ]
    )
    median, count = chunked_median_composite(
        da.from_array(values, chunks=(1, 1, 1, 1)),
        da.from_array(masks, chunks=(1, 1, 1)),
    )
    np.testing.assert_array_equal(count.compute(), [[3, 2], [0, 0]])
    np.testing.assert_array_equal(
        median.compute(), [[[3, 20], [-9999, -9999]]]
    )


def test_composite_chunked_memory_bounded():
    estimated = estimate_chunk_working_bytes(
        scene_count=8, band_count=6, chunk_size_pixels=512
    )
    assert estimated < 128 * 1024 * 1024


def test_valid_obs_count_raster_written_and_correct():
    values = da.ones((3, 2, 2, 2), chunks=(1, 1, 2, 2), dtype="float32")
    masks = da.from_array(
        np.array(
            [
                [[True, True], [False, True]],
                [[True, False], [False, True]],
                [[False, False], [False, True]],
            ]
        ),
        chunks=(1, 2, 2),
    )
    _, count = chunked_median_composite(values, masks)
    np.testing.assert_array_equal(count.compute(), [[2, 1], [0, 3]])


def test_composite_masks_pixels_below_approved_observation_minimum():
    values = da.from_array(
        np.array([[[[2, 4]]], [[[6, 8]]], [[[10, 12]]]], dtype="float32"),
        chunks=(1, 1, 1, 2),
    )
    masks = da.from_array(
        np.array([[[True, True]], [[True, False]], [[True, False]]]),
        chunks=(1, 1, 2),
    )
    median, count = chunked_median_composite(
        values, masks, min_valid_observations=2
    )

    np.testing.assert_array_equal(count.compute(), [[3, 1]])
    np.testing.assert_array_equal(median.compute(), [[[6, -9999]]])


def test_all_cloud_epoch_halts_and_reports():
    with pytest.raises(CoverageInsufficientError, match="coverage gate failed"):
        assess_coverage(
            np.zeros((4, 4), dtype="uint8"),
            np.ones((4, 4), dtype=bool),
            CoverageGate(min_valid_observations=2, min_aoi_coverage_fraction=0.95),
        )


def test_coverage_gate_requires_approved_non_null_values():
    with pytest.raises(ValueError, match="must be approved"):
        CoverageGate.from_mapping(
            {"min_valid_observations": None, "min_aoi_coverage_fraction": None}
        )
