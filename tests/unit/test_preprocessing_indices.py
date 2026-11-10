import numpy as np
import pytest

from src.preprocessing.indices import BAND_NAMES, INDEX_FORMULAS, IndexPolicy, compute_indices
from src.utils.io import load_config


def stack(blue=.1, green=.18, red=.2, nir=.3, swir=.35, swir2=.25):
    return np.array([blue, green, red, nir, swir, swir2], dtype="float32")[:, None, None]


def test_index_divide_by_zero_guarded_and_range_plausible():
    outputs, stats = compute_indices(stack())
    expected = {"ndvi": .2, "ndbi": .05/.65, "ndwi": -.12/.48,
                "mndwi": -.17/.53, "bsi": .15/.95}
    for name, value in expected.items():
        assert outputs[name].dtype == np.float32
        assert outputs[name][0, 0] == pytest.approx(value, abs=1e-6)
        assert stats[name]["out_of_range_pixels"] == 0
    zero_outputs, zero_stats = compute_indices(stack(blue=0, green=0, red=0, nir=0, swir=0))
    for name in INDEX_FORMULAS:
        assert zero_outputs[name][0, 0] == -9999
        assert zero_stats[name]["guarded_denominator_pixels"] == 1


@pytest.mark.parametrize("bad", [-9999.0, np.nan, np.inf, -np.inf])
def test_invalid_source_band_propagates_to_every_index(bad):
    values = stack()
    values[5] = bad  # Even unused B12 belongs to the all-band composite-validity contract.
    outputs, stats = compute_indices(values)
    for name in INDEX_FORMULAS:
        assert outputs[name][0, 0] == -9999
        assert np.isfinite(outputs[name]).all()
        assert stats[name]["source_invalid_pixels"] == 1


def test_near_zero_and_cancellation_are_guarded_per_index():
    outputs, stats = compute_indices(stack(red=-.3, nir=.3000001))
    assert outputs["ndvi"][0, 0] == -9999
    assert stats["ndvi"]["guarded_denominator_pixels"] == 1
    assert stats["ndbi"]["valid_pixels"] == 1


def test_negative_reflectance_out_of_range_is_preserved_not_clipped():
    outputs, stats = compute_indices(stack(red=-.1, nir=.3))
    assert outputs["ndvi"][0, 0] == pytest.approx(2.0)
    assert stats["ndvi"]["out_of_range_pixels"] == 1


def test_negative_denominator_is_retained_and_reported():
    outputs, stats = compute_indices(stack(red=-.2, nir=-.1))
    assert outputs["ndvi"][0, 0] == pytest.approx(-1/3)
    assert stats["ndvi"]["negative_denominator_pixels"] == 1


def test_chunk_results_match_full_array_without_spatial_halos():
    values = np.tile(stack(), (1, 3, 4))
    values[:, 1, 2] = -9999
    complete, _ = compute_indices(values)
    for x0, x1 in ((0, 2), (2, 4)):
        partial, _ = compute_indices(values[:, :, x0:x1])
        for name in INDEX_FORMULAS:
            np.testing.assert_array_equal(partial[name], complete[name][:, x0:x1])


def test_indices_reject_unscaled_dn_wrong_bands_and_wrong_shapes():
    with pytest.raises(TypeError, match="floating"):
        compute_indices(stack().astype("uint16"))
    with pytest.raises(ValueError, match="band order"):
        compute_indices(stack(), band_names=tuple(reversed(BAND_NAMES)))
    with pytest.raises(ValueError, match="shape"):
        compute_indices(stack()[0])


def test_index_policy_matches_configured_formulas_and_rejects_clipping():
    config = load_config("preprocessing")["indices"]
    assert IndexPolicy.from_mapping(config).denominator_epsilon == 1e-6
    with pytest.raises(ValueError, match="preserve"):
        IndexPolicy.from_mapping({**config, "preserve_out_of_range_for_qc": False})
    with pytest.raises(ValueError, match="formulas"):
        IndexPolicy.from_mapping({**config, "formulas": {}})


@pytest.mark.parametrize("kwargs", [{"denominator_epsilon": 0}, {"range_tolerance": -1},
                                  {"output_nodata": np.nan}, {"nominal_min": 2}])
def test_invalid_policy_fails_closed(kwargs):
    with pytest.raises(ValueError):
        IndexPolicy(**kwargs)
